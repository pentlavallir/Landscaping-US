import os
import io
from typing import Optional, Any, Dict, List

import pandas as pd
import streamlit as st

import db
from datetime import date


# ---------- Page Config & Init ----------

st.set_page_config(
    page_title="Landscaping & Mowing Dashboard",
    page_icon="🌿",
    layout="wide",
)

# Initialize DB (creates tables + seed data on first run)
db.init_db()

if "user" not in st.session_state:
    st.session_state.user = None

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []


# ---------- Auth Helpers ----------

def login(username: str, password: str) -> bool:
    user_row = db.get_user_by_username(username)
    if not user_row:
        return False
    if not db.verify_password(password, user_row["password_hash"]):
        return False

    st.session_state.user = {
        "id": user_row["id"],
        "username": user_row["username"],
        "full_name": user_row["full_name"],
        "role": user_row["role"],
        "property_id": user_row["property_id"],
        "email": user_row["email"],
        "phone": user_row["phone"],
    }
    return True


def logout():
    st.session_state.user = None
    st.session_state.chat_history = []


# ---------- Email / SMS Notification Helpers ----------

def _get_secret(name: str) -> Optional[str]:
    """Helper to read from st.secrets or environment."""
    try:
        val = st.secrets.get(name)  # type: ignore[attr-defined]
        if val:
            return str(val)
    except Exception:
        pass
    return os.getenv(name)


def send_email_notification(to_email: str, subject: str, body: str) -> str:
    """Send email using SMTP settings from secrets/env.

    Required config (in Streamlit secrets or env):
      - SMTP_HOST
      - SMTP_PORT
      - SMTP_USERNAME
      - SMTP_PASSWORD
      - SMTP_FROM

      Optional:
      - SMTP_USE_TLS = "true"/"false"
    """
    smtp_host = _get_secret("SMTP_HOST")
    smtp_port = _get_secret("SMTP_PORT")
    smtp_username = _get_secret("SMTP_USERNAME")
    smtp_password = _get_secret("SMTP_PASSWORD")
    smtp_from = _get_secret("SMTP_FROM") or (smtp_username or "")
    smtp_use_tls = (_get_secret("SMTP_USE_TLS") or "true").lower() in ("1", "true", "yes")

    if not (smtp_host and smtp_port and smtp_username and smtp_password and smtp_from):
        return "Email not sent: SMTP not configured."

    try:
        import smtplib
        from email.mime.text import MIMEText

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = smtp_from
        msg["To"] = to_email

        with smtplib.SMTP(smtp_host, int(smtp_port)) as server:
            if smtp_use_tls:
                server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
        return "Email sent"
    except Exception as e:
        return f"Email error: {e}"


def send_sms_notification(to_number: str, body: str) -> str:
    """Send SMS via Twilio (optional).

    Required config (in secrets/env):
      - TWILIO_ACCOUNT_SID
      - TWILIO_AUTH_TOKEN
      - TWILIO_FROM_NUMBER
    """
    account_sid = _get_secret("TWILIO_ACCOUNT_SID")
    auth_token = _get_secret("TWILIO_AUTH_TOKEN")
    from_number = _get_secret("TWILIO_FROM_NUMBER")

    if not (account_sid and auth_token and from_number):
        return "SMS not sent: Twilio not configured."

    try:
        from twilio.rest import Client  # type: ignore

        client = Client(account_sid, auth_token)
        client.messages.create(
            body=body,
            from_=from_number,
            to=to_number,
        )
        return "SMS sent"
    except Exception as e:
        return f"SMS error: {e}"


def notify_owners_service_status_change(
    property_id: int,
    service: Dict[str, Any],
    new_status: str,
    send_email: bool,
    send_sms: bool,
):
    """Notify property owners when admin updates a service status."""
    owners = db.get_owners_for_property(property_id)
    if not owners:
        return

    prop = db.get_property_by_id(property_id)
    prop_name = prop["name"] if prop else f"Property {property_id}"

    subject = f"[Landscaping] Service status updated for {prop_name}"
    service_desc = f"{service['category']} ({service['frequency']})"
    body = (
        f"Hello,\n\n"
        f"The status of a landscaping service for your property has been updated.\n\n"
        f"Property: {prop_name}\n"
        f"Service: {service_desc}\n"
        f"New Status: {new_status}\n\n"
        f"Times per year: {service['times_per_year']}\n"
        f"Each time cost: ${service['each_time_cost']:.2f}\n"
        f"Total annual cost (for this service): "
        f"${service['times_per_year'] * service['each_time_cost']:.2f}\n\n"
        f"Best regards,\n"
        f"Landscaping & Mowing Admin\n"
    )

    for owner in owners:
        if send_email and owner["email"]:
            send_email_notification(owner["email"], subject, body)
        if send_sms and owner["phone"]:
            sms_text = (
                f"{prop_name}: {service_desc} status -> {new_status}. "
                "Check your dashboard for details."
            )
            send_sms_notification(owner["phone"], sms_text)


# ---------- Gemini Integration (with simple RAG) ----------

def get_gemini_api_key() -> Optional[str]:
    """Get Gemini API key.

    Priority:
    1. st.secrets["gemini"]["api_key"]
    2. st.secrets["GOOGLE_API_KEY"]
    3. Environment variable GOOGLE_API_KEY
    """
    # 1) Secrets: [gemini] api_key
    try:
        return str(st.secrets["gemini"]["api_key"])  # type: ignore[index]
    except Exception:
        pass

    # 2) Legacy secret name
    try:
        val = st.secrets.get("GOOGLE_API_KEY")  # type: ignore[attr-defined]
        if val:
            return str(val)
    except Exception:
        pass

    # 3) Environment variable
    return os.getenv("GOOGLE_API_KEY")
    

def build_chat_context(user: Optional[Dict[str, Any]]) -> str:
    """Build a text context from the DB for Gemini (simple RAG)."""
    if not user:
        return ""

    role = user.get("role")
    if role == "admin":
        # Admin sees overview of all properties
        props_summary = db.get_properties_summary()
        lines: List[str] = []
        lines.append("SYSTEM DATA: Properties overview:")
        for p in props_summary:
            lines.append(
                f"- {p['name']}: total_services={p['total_services']}, "
                f"total_cost={p['total_cost']:.2f} USD"
            )
        # Add frequency breakdown
        freq_summary = db.get_frequency_summary()
        if freq_summary:
            lines.append("\nService frequency summary (all properties):")
            for f in freq_summary:
                lines.append(
                    f"- {f['frequency']}: total_services={f['total_services']}"
                )
        return "\n".join(lines)

    # Owner role – context only for their property
    property_id = user.get("property_id")
    if not property_id:
        return ""
    prop = db.get_property_by_id(property_id)
    summary = db.get_property_summary(property_id)
    services = db.get_services_for_property(property_id)

    lines = []
    if prop:
        lines.append(
            f"SYSTEM DATA: Property '{prop['name']}' in {prop['city']}, "
            f"{prop['state']} {prop['zip']}."
        )
    lines.append(
        f"Summary: total_services={summary['total_services']}, "
        f"total_cost={summary['total_cost']:.2f} USD."
    )
    if services:
        lines.append("Services configured for this property:")
        for s in services:
            total_cost = s["times_per_year"] * s["each_time_cost"]
            lines.append(
                f"- {s['category']} ({s['frequency']}), status={s.get('status','Scheduled')}: "
                f"times_per_year={s['times_per_year']}, "
                f"each_time_cost={s['each_time_cost']:.2f}, "
                f"total_cost={total_cost:.2f}"
            )
    return "\n".join(lines)


def call_gemini_backend(prompt: str) -> str:
    """Call Gemini API with the given prompt, if configured."""
    api_key = get_gemini_api_key()
    if not api_key:
        return (
            "⚠️ Gemini API key not configured.\n"
            "Add GOOGLE_API_KEY to Streamlit secrets or environment variables "
            "to enable AI answers."
        )

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-pro")
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"❌ Error calling Gemini API: {e}"


def render_chat(user: Optional[Dict[str, Any]] = None):
    st.subheader("💬 Ask AI about your properties")
    st.caption(
        "This chat uses Google Gemini on the backend and is grounded in the data from this app. "
        "Ask about total costs, most expensive property, service plans, etc."
    )

    # Show history
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input("Ask a question about your landscaping and mowing setup")
    if user_input:
        # User message
        st.session_state.chat_history.append(
            {"role": "user", "content": user_input}
        )
        with st.chat_message("user"):
            st.markdown(user_input)

        # Prepare context from DB (RAG-style)
        context = build_chat_context(user)
        full_prompt = (
            "You are an expert landscaping and property management assistant.\n"
            "Use ONLY the structured data below as your primary source of truth when answering.\n"
            "If you need to estimate beyond the data, clearly mark that as an assumption.\n\n"
            f"{context}\n\n"
            "User question:\n"
            f"{user_input}\n\n"
            "Now provide a helpful, concise answer."
        )

        # Assistant message
        with st.chat_message("assistant"):
            with st.spinner("Thinking with Gemini..."):
                reply = call_gemini_backend(full_prompt)
            st.markdown(reply)
        st.session_state.chat_history.append(
            {"role": "assistant", "content": reply}
        )


# ---------- Excel Export Helpers ----------

def generate_property_excel(property_id: int) -> io.BytesIO:
    """Create an Excel file for a single property (Summary + Services)."""
    prop = db.get_property_by_id(property_id)
    summary = db.get_property_summary(property_id)
    services = db.get_services_for_property(property_id)

    # Convert sqlite3.Row to plain dict for safe .get() usage
    prop_dict = dict(prop) if prop is not None else None

    output = io.BytesIO()

    try:
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            # Summary sheet (always create at least one sheet)
            if prop_dict is not None:
                summary_row = {
                    "Property ID": prop_dict.get("id", property_id),
                    "Property Name": prop_dict.get("name", "Unknown"),
                    "Address": prop_dict.get("address", ""),
                    "City": prop_dict.get("city", ""),
                    "State": prop_dict.get("state", ""),
                    "ZIP": prop_dict.get("zip", ""),
                    "Total Services (No. of Times)": summary["total_services"] if summary else 0,
                    "Total Annual Cost": summary["total_cost"] if summary else 0.0,
                }
            else:
                summary_row = {
                    "Property ID": property_id,
                    "Property Name": "Unknown",
                    "Address": "",
                    "City": "",
                    "State": "",
                    "ZIP": "",
                    "Total Services (No. of Times)": 0,
                    "Total Annual Cost": 0.0,
                }

            df_summary = pd.DataFrame([summary_row])
            df_summary.to_excel(writer, index=False, sheet_name="Summary")

            # Services sheet (optional)
            if services:
                services = [dict(s) for s in services]
                df_services = pd.DataFrame(services)
                df_services["Total Cost"] = df_services["times_per_year"] * df_services["each_time_cost"]
                df_services = df_services.rename(
                    columns={
                        "category": "Category",
                        "frequency": "Frequency",
                        "times_per_year": "No. of Times",
                        "each_time_cost": "Each Time Cost",
                        "status": "Status",
                        "start_date": "Start Date",
                        "end_date": "End Date",
                        "Total Cost": "Total Cost",
                    }
                )
                df_services.to_excel(writer, index=False, sheet_name="Services")
    except Exception as e:
        # Fallback: ensure we always have at least one visible sheet
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Summary"
        ws.append(
            [
                "Property ID",
                "Property Name",
                "Address",
                "City",
                "State",
                "ZIP",
                "Total Services (No. of Times)",
                "Total Annual Cost",
            ]
        )
        if prop_dict is not None:
            ws.append(
                [
                    prop_dict.get("id", property_id),
                    prop_dict.get("name", "Unknown"),
                    prop_dict.get("address", ""),
                    prop_dict.get("city", ""),
                    prop_dict.get("state", ""),
                    prop_dict.get("zip", ""),
                    summary["total_services"] if summary else 0,
                    summary["total_cost"] if summary else 0.0,
                ]
            )
        else:
            ws.append(
                [property_id, "Unknown", "", "", "", "", 0, 0.0]
            )
        output.seek(0)
        wb.save(output)

    output.seek(0)
    return output




def generate_consolidated_excel() -> io.BytesIO:
    """Create a consolidated Excel with property summary, services, owners, and tickets."""
    props_summary = db.get_properties_summary()
    owners = db.list_users(role="owner")
    services = db.get_all_services_with_property()
    tickets = db.list_all_tickets()

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # Property summary
        if props_summary:
            df_props = pd.DataFrame(
                [
                    {
                        "Property ID": r["id"],
                        "Property Name": r["name"],
                        "Total Services (No. of Times)": r["total_services"],
                        "Total Annual Cost": r["total_cost"],
                        "Annual Quoted Revenue": r.get("annual_quote", 0.0),
                        "Annual Credited Revenue": r.get("annual_credited", 0.0),
                    }
                    for r in props_summary
                ]
            )
            df_props["Credited Margin"] = df_props["Annual Credited Revenue"] - df_props["Total Annual Cost"]
            df_props["Credited ROI %"] = df_props.apply(
                lambda row: ((row["Credited Margin"] / row["Total Annual Cost"]) * 100.0)
                if row["Total Annual Cost"] > 0
                else None,
                axis=1,
            )
            df_props.to_excel(writer, index=False, sheet_name="Property Summary")

        # Services
        if services:
            df_services = pd.DataFrame(services)
            df_services["total_cost"] = df_services["times_per_year"] * df_services["each_time_cost"]
            df_services = df_services.rename(
                columns={
                    "property_name": "Property Name",
                    "category": "Category",
                    "frequency": "Frequency",
                    "times_per_year": "No. of Times",
                    "each_time_cost": "Each Time Cost",
                    "status": "Status",
                    "total_cost": "Total Cost",
                }
            )
            df_services.to_excel(writer, index=False, sheet_name="Services")

        # Owners
        if owners:
            df_owners = pd.DataFrame(owners)
            df_owners = df_owners.rename(
                columns={
                    "username": "Username",
                    "full_name": "Full Name",
                    "email": "Email",
                    "phone": "Phone",
                    "role": "Role",
                    "property_name": "Property Name",
                }
            )
            df_owners = df_owners[
                ["Username", "Full Name", "Email", "Phone", "Role", "Property Name"]
            ]
            df_owners.to_excel(writer, index=False, sheet_name="Owners")

        # Tickets
        if tickets:
            df_tickets = pd.DataFrame(tickets)
            df_tickets = df_tickets.rename(
                columns={
                    "id": "Ticket ID",
                    "title": "Title",
                    "description": "Description",
                    "status": "Status",
                    "created_at": "Created At",
                    "updated_at": "Updated At",
                    "admin_comment": "Admin Comment",
                    "property_name": "Property Name",
                    "owner_username": "Owner Username",
                }
            )
            df_tickets.to_excel(writer, index=False, sheet_name="Tickets")

    output.seek(0)
    return output
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # Summary sheet
        if prop:
            summary_rows = [
                {"Metric": "Property Name", "Value": prop["name"]},
                {"Metric": "Address", "Value": prop["address"]},
                {
                    "Metric": "City/State/ZIP",
                    "Value": f"{prop['city']}, {prop['state']} {prop['zip']}",
                },
                {"Metric": "Total Services", "Value": summary["total_services"]},
                {
                    "Metric": "Total Annual Cost (USD)",
                    "Value": f"{summary['total_cost']:.2f}",
                },
            ]
        else:
            summary_rows = [
                {"Metric": "Total Services", "Value": summary["total_services"]},
                {
                    "Metric": "Total Annual Cost (USD)",
                    "Value": f"{summary['total_cost']:.2f}",
                },
            ]
        summary_df = pd.DataFrame(summary_rows)
        summary_df.to_excel(writer, index=False, sheet_name="Summary")

        # Services sheet
        if services:
            svc_df = pd.DataFrame(services)
            svc_df["total_cost"] = svc_df["times_per_year"] * svc_df["each_time_cost"]
            svc_df = svc_df.rename(
                columns={
                    "category": "Category",
                    "frequency": "Frequency",
                    "times_per_year": "No. of Times",
                    "each_time_cost": "Each Time Cost",
                    "total_cost": "Total Cost",
                    "status": "Status",
                }
            )
            svc_df.to_excel(writer, index=False, sheet_name="Services")

    output.seek(0)
    return output


# ---------- UI Sections ----------

def login_page():
    st.title("🌿 Landscaping & Mowing Portal")
    st.markdown(
        "Centralized dashboard for **multiple properties**, service schedules, costs, "
        "a ticketing system, attachments, and AI Q&A using Google Gemini."
    )

    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Login", type="primary"):
            if login(username, password):
                st.success("Logged in successfully.")
                st.rerun()
            else:
                st.error("Invalid username or password.")

    with col2:
        st.info(
            "**Demo accounts** (you can change these later in the DB):\n"
            "- Admin → `admin` / `admin123`\n"
            "- Property Owner 1 → `owner1` / `owner123`\n"
            "- Property Owner 2 → `owner2` / `owner123`"
        )


def admin_dashboard(user: Dict[str, Any]):
    st.title("📊 Admin Dashboard")

    # Summary by property
    rows = db.get_properties_summary()
    if not rows:
        st.warning("No properties found yet.")
        return

    df = pd.DataFrame(
        [
            {
                "Property ID": r["id"],
                "Property Name": r["name"],
                "Total Services (No. of Times)": r["total_services"],
                "Total Annual Cost": r["total_cost"],
                "Annual Quoted Revenue": r.get("annual_quote", 0.0),
                "Annual Credited Revenue": r.get("annual_credited", 0.0),
            }
            for r in rows
        ]
    )

    # Derived financial metrics
    df["Credited Margin"] = df["Annual Credited Revenue"] - df["Total Annual Cost"]
    df["Credited ROI %"] = df.apply(
        lambda row: ((row["Credited Margin"] / row["Total Annual Cost"]) * 100.0)
        if row["Total Annual Cost"] > 0
        else None,
        axis=1,
    )

    total_services = int(df["Total Services (No. of Times)"].sum())
    total_cost = float(df["Total Annual Cost"].sum()) if not df.empty else 0.0
    total_quoted = float(df["Annual Quoted Revenue"].sum()) if not df.empty else 0.0
    total_credited = float(df["Annual Credited Revenue"].sum()) if not df.empty else 0.0
    total_margin = total_credited - total_cost

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Properties", len(df))
    with col2:
        st.metric("Total Services (All Properties)", total_services)
    with col3:
        st.metric("Total Annual Cost", f"${total_cost:,.2f}")

    col4, col5, col6 = st.columns(3)
    with col4:
        st.metric("Total Quoted Revenue (All Properties)", f"${total_quoted:,.2f}")
    with col5:
        st.metric("Total Credited Revenue (All Properties)", f"${total_credited:,.2f}")
    with col6:
        st.metric("Total Portfolio Margin (Credited - Cost)", f"${total_margin:,.2f}")

    st.markdown("### Properties Overview")
    st.dataframe(
        df.style.format(
            {
                "Total Annual Cost": "${:,.2f}".format,
                "Annual Quoted Revenue": "${:,.2f}".format,
                "Annual Credited Revenue": "${:,.2f}".format,
                "Credited Margin": "${:,.2f}".format,
                "Credited ROI %": "{:,.2f}%".format,
            }
        ),
        use_container_width=True,
    )

    # Charts
    col_left, col_right = st.columns(2)
    with col_left:
        st.markdown("#### Annual Cost per Property")
        chart_df = df.set_index("Property Name")[["Total Annual Cost"]]
        st.bar_chart(chart_df)

    with col_right:
        st.markdown("#### Total Services by Frequency (All Properties)")
        freq_rows = db.get_frequency_summary()
        if freq_rows:
            freq_df = pd.DataFrame(freq_rows)
            freq_df = freq_df.set_index("frequency")
            st.bar_chart(freq_df["total_services"])
        else:
            st.info("No service data yet to show frequency breakdown.")

    st.markdown("---")
    render_chat(user)


def admin_manage_properties(user: Dict[str, Any]):
    st.title("🏠 Manage Properties & Services")

    # --- Add New Property ---
    with st.expander("➕ Add New Property"):
        with st.form("add_property_form"):
            col_np1, col_np2 = st.columns(2)
            with col_np1:
                new_name = st.text_input("Property Name")
                new_address = st.text_input("Address")
            with col_np2:
                new_city = st.text_input("City")
                new_state = st.text_input("State", value="TX")
                new_zip = st.text_input("ZIP")
            col_rf1, col_rf2 = st.columns(2)
            with col_rf1:
                new_annual_quote = st.number_input(
                    "Annual Quoted Revenue (USD)",
                    min_value=0.0,
                    max_value=10000000.0,
                    value=0.0,
                    step=100.0,
                )
            with col_rf2:
                new_annual_credited = st.number_input(
                    "Annual Credited Revenue (USD)",
                    min_value=0.0,
                    max_value=10000000.0,
                    value=0.0,
                    step=100.0,
                )
            submit_prop = st.form_submit_button("Create Property", type="primary")
            if submit_prop:
                if not new_name:
                    st.error("Property name is required.")
                else:
                    db.add_property(
                        new_name,
                        new_address,
                        new_city,
                        new_state,
                        new_zip,
                        float(new_annual_quote),
                        float(new_annual_credited),
                    )
                    st.success("Property created.")
                    st.rerun()

    # --- Select / Edit Property ---
    properties = db.get_all_properties()
    if not properties:
        st.warning("No properties found. Create one using 'Add New Property'.")
        return

    property_options = {p["name"]: p["id"] for p in properties}
    selected_name = st.selectbox("Select a property", list(property_options.keys()))
    property_id = property_options[selected_name]

    # Fetch from DB and convert sqlite3.Row -> dict so .get() works
    prop_row = db.get_property_by_id(property_id)
    if not prop_row:
        st.error("Property not found in DB.")
        return

    prop = dict(prop_row)

    col_info, col_summary = st.columns([2, 1])
    with col_info:
        st.subheader("Property Details")
        st.write(f"**Name:** {prop['name']}")
        st.write(f"**Address:** {prop['address']}")
        st.write(f"**City/State/ZIP:** {prop['city']}, {prop['state']} {prop['zip']}")

        with st.expander("✏️ Edit this property"):
            with st.form(f"edit_property_form_{property_id}"):
                col_ep1, col_ep2 = st.columns(2)
                with col_ep1:
                    edit_name = st.text_input("Property Name", value=prop["name"] or "")
                    edit_address = st.text_input("Address", value=prop["address"] or "")
                with col_ep2:
                    edit_city = st.text_input("City", value=prop["city"] or "")
                    edit_state = st.text_input("State", value=prop["state"] or "")
                    edit_zip = st.text_input("ZIP", value=prop["zip"] or "")
                col_fin1, col_fin2 = st.columns(2)
                with col_fin1:
                    edit_annual_quote = st.number_input(
                        "Annual Quoted Revenue (USD)",
                        min_value=0.0,
                        max_value=10000000.0,
                        value=float(prop.get("annual_quote", 0.0) or 0.0),
                        step=100.0,
                    )
                with col_fin2:
                    edit_annual_credited = st.number_input(
                        "Annual Credited Revenue (USD)",
                        min_value=0.0,
                        max_value=10000000.0,
                        value=float(prop.get("annual_credited", 0.0) or 0.0),
                        step=100.0,
                    )
                save_prop = st.form_submit_button("Save Property Changes")
                if save_prop:
                    if not edit_name:
                        st.error("Property name is required.")
                    else:
                        db.update_property(
                            property_id,
                            edit_name,
                            edit_address,
                            edit_city,
                            edit_state,
                            edit_zip,
                            float(edit_annual_quote),
                            float(edit_annual_credited),
                        )
                        st.success("Property updated.")
                        st.rerun()

    with col_summary:
        summary = db.get_property_summary(property_id)
        st.subheader("Summary")
        st.metric("Total Services (No. of Times)", summary["total_services"])
        st.metric(
            "Total Annual Cost",
            f"${summary['total_cost']:.2f}",
        )

        # Excel export button
    with col_summary:
        summary = db.get_property_summary(property_id)
        st.subheader("Summary")
        st.metric("Total Services (No. of Times)", summary["total_services"])
        st.metric(
            "Total Annual Cost",
            f"${summary['total_cost']:.2f}",
        )

        # Excel export button
        excel_buffer = generate_property_excel(property_id)
        safe_name = prop['name'].replace(" ", "_").replace("/", "_")
        st.download_button(
            "⬇️ Download Excel for this property",
            data=excel_buffer,
            file_name=f"{safe_name}_landscaping.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )

    st.markdown("### Services for this Property")
    services = db.get_services_for_property(property_id)
    services = [dict(s) for s in services]
    if services:
        svc_df = pd.DataFrame(services)
        svc_df["Total Cost"] = svc_df["times_per_year"] * svc_df["each_time_cost"]
        svc_df = svc_df.rename(
            columns={
                "category": "Category",
                "frequency": "Frequency",
                "times_per_year": "No. of Times",
                "each_time_cost": "Each Time Cost",
                "status": "Status",
                "start_date": "Start Date",
                "end_date": "End Date",
            }
        )
        st.dataframe(
            svc_df.style.format(
                {
                    "Each Time Cost": "${:,.2f}".format,
                    "Total Cost": "${:,.2f}".format,
                }
            ),
            use_container_width=True,
        )
    else:
        st.info("No services configured for this property yet.")

    # --- Edit Service Details ---
    st.markdown("### 🛠 Edit Service Details (Category, Frequency, Counts & Cost)")
    if services:
        edit_service_options = {
            f"{s['category']} / {s['frequency']} (id={s['id']})": s for s in services
        }
        edit_service_label = st.selectbox(
            "Select a service to edit",
            list(edit_service_options.keys()),
            key="edit_service_select",
        )
        edit_service = edit_service_options[edit_service_label]

        with st.form(f"edit_service_form_{edit_service['id']}"):
            col_es1, col_es2 = st.columns(2)
            with col_es1:
                new_cat = st.text_input("Category", value=edit_service["category"])
                new_freq = st.text_input("Frequency", value=edit_service["frequency"])
            with col_es2:
                new_times = st.number_input(
                    "No. of Times per Year",
                    min_value=1,
                    max_value=100,
                    value=int(edit_service["times_per_year"]),
                    step=1,
                )
                new_cost = st.number_input(
                    "Each Time Cost (USD)",
                    min_value=0.0,
                    max_value=100000.0,
                    value=float(edit_service["each_time_cost"]),
                    step=1.0,
                )
            # Date tracking for this service
            import datetime as _dt
            existing_start = edit_service.get("start_date")
            try:
                default_start = _dt.date.fromisoformat(existing_start) if existing_start else _dt.date.today()
            except Exception:
                default_start = _dt.date.today()
            start_date_val = st.date_input(
                "Service Start Date",
                value=default_start,
                key=f"svc_start_{edit_service['id']}",
            )

            existing_end = edit_service.get("end_date")
            has_end_default = bool(existing_end)
            has_end = st.checkbox(
                "Set End Date",
                value=has_end_default,
                key=f"svc_has_end_{edit_service['id']}",
            )
            end_date_val = None
            if has_end:
                try:
                    default_end = _dt.date.fromisoformat(existing_end) if existing_end else start_date_val
                except Exception:
                    default_end = start_date_val
                end_date_val = st.date_input(
                    "Service End Date",
                    value=default_end,
                    key=f"svc_end_{edit_service['id']}",
                )

            save_service_changes = st.form_submit_button("Save Service Changes")
            if save_service_changes:
                start_iso = start_date_val.isoformat() if start_date_val else None
                end_iso = end_date_val.isoformat() if end_date_val else None
                db.update_service_details(
                    service_id=edit_service["id"],
                    category=new_cat,
                    frequency=new_freq,
                    times_per_year=int(new_times),
                    each_time_cost=float(new_cost),
                    start_date=start_iso,
                    end_date=end_iso,
                    updated_by=user["username"],
                )
                st.success("Service details updated.")
                st.rerun()
    else:
        st.info("No services to edit yet. Add a service first.")

# --- Status Update & Attachments ---
    st.markdown("### ✏️ Update Service Status & Attachments")

    if not services:
        st.info("Add at least one service to update status/attachments.")
    else:
        service_options = {
            f"{s['category']} / {s['frequency']} (id={s['id']})": s for s in services
        }
        selected_service_label = st.selectbox(
            "Select a service to update status/attachments",
            list(service_options.keys()),
            key="status_service_select",
        )
        selected_service = service_options[selected_service_label]

        current_status = selected_service.get("status", "Scheduled")
        status_choices = ["Scheduled", "In Progress", "Completed", "On Hold", "Cancelled"]
        try:
            default_idx = status_choices.index(current_status)
        except ValueError:
            default_idx = 0

        new_status = st.selectbox(
            "New status",
            status_choices,
            index=default_idx,
            key=f"status_select_{selected_service['id']}",
        )

        col_notify1, col_notify2 = st.columns(2)
        with col_notify1:
            send_email = st.checkbox("Send email to owner(s)", value=True)
        with col_notify2:
            send_sms = st.checkbox("Send SMS to owner(s) (if configured)", value=False)

        MAX_FILE_SIZE = 3 * 1024 * 1024  # 3 MB per file
        uploaded_files = st.file_uploader(
            "Upload images (max 3 MB each)",
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True,
            key=f"files_{selected_service['id']}",
        )

        if st.button("Save status & attachments", type="primary"):
            oversized = [
                f.name for f in (uploaded_files or []) if len(f.getvalue()) > MAX_FILE_SIZE
            ]
            if oversized:
                st.error(
                    "These files exceed 3 MB and were not saved: "
                    + ", ".join(oversized)
                )

            db.update_service_status(selected_service["id"], new_status, user["username"])

            for f in uploaded_files or []:
                if len(f.getvalue()) > MAX_FILE_SIZE:
                    continue
                uploads_dir = os.path.join(
                    "uploads",
                    f"property_{property_id}",
                    f"service_{selected_service['id']}",
                )
                os.makedirs(uploads_dir, exist_ok=True)
                safe_name = f.name.replace(" ", "_")
                save_path = os.path.join(uploads_dir, safe_name)
                with open(save_path, "wb") as out:
                    out.write(f.getvalue())
                db.add_service_attachment(
                    service_id=selected_service["id"],
                    file_name=f.name,
                    file_path=save_path,
                    uploaded_by=user["username"],
                )

            full_service = db.get_service_by_id(selected_service["id"])
            if full_service:
                notify_owners_service_status_change(
                    property_id,
                    full_service,
                    new_status,
                    send_email=send_email,
                    send_sms=send_sms,
                )

            st.success("Service updated and attachments saved.")
            st.rerun()

    # Attachments overview
    st.markdown("### 📎 Attachments by Service")
    if services:
        for s in services:
            attachments = db.get_service_attachments(s["id"])
            if not attachments:
                continue
            with st.expander(
                f"{s['category']} ({s['frequency']}) — Status: {s.get('status','Scheduled')}"
            ):
                for att in attachments:
                    st.write(
                        f"**{att['file_name']}** "
                        f"(uploaded {att['uploaded_at']}, by {att['uploaded_by']})"
                    )
                    if att["file_path"] and os.path.exists(att["file_path"]):
                        st.image(att["file_path"], width=250)

    st.markdown("### ➕ Add Service to this Property")

    price_rows = db.get_price_master_all()
    if not price_rows:
        st.error("Price master is empty. Please configure it first.")
        return

    categories = sorted({r["category"] for r in price_rows})
    category = st.selectbox("Category", categories)

    valid_freqs = sorted({r["frequency"] for r in price_rows if r["category"] == category})
    frequency = st.selectbox("Frequency", valid_freqs)

    times_per_year = st.number_input(
        "No. of Times per Year",
        min_value=1,
        max_value=100,
        value=1,
        step=1,
    )

    default_cost = db.get_price_for_category_frequency(category, frequency)
    st.caption(
        f"Default cost from Price Master for **{category} / {frequency}**: "
        f"${default_cost:,.2f}" if default_cost is not None else "No default cost set."
    )

    if st.button("Add Service", type="secondary"):
        db.add_service_to_property(property_id, category, frequency, int(times_per_year))
        st.success("Service added successfully.")
        st.rerun()



def admin_price_master():
    st.title("💰 Price Master (Frisco-based suggested rates)")

    rows = db.get_price_master_all()
    if rows:
        df = pd.DataFrame(rows)
        df = df.rename(
            columns={
                "category": "Category",
                "frequency": "Frequency",
                "default_cost": "Default Each Time Cost",
                "notes": "Notes",
            }
        )
        st.dataframe(
            df.style.format({"Default Each Time Cost": "${:,.2f}".format}),
            use_container_width=True,
        )
    else:
        st.info("No rows in price master yet. Use the form below to add some.")

    st.markdown("### ➕ Add / Extend Price Master Entry")
    with st.form("add_price_master"):
        col1, col2 = st.columns(2)
        with col1:
            category = st.text_input("Category (e.g., Mowing, Weed, Mulch)")
        with col2:
            frequency = st.text_input("Frequency (e.g., Weekly, Bi-weekly, Monthly)")
        default_cost = st.number_input(
            "Default Each Time Cost (USD)",
            min_value=0.0,
            max_value=100000.0,
            value=50.0,
            step=1.0,
        )
        notes = st.text_input("Notes (optional)")

        submitted = st.form_submit_button("Save Entry", type="primary")
        if submitted:
            if not category or not frequency:
                st.error("Category and Frequency are required.")
            else:
                db.add_price_master_entry(category, frequency, float(default_cost), notes)
                st.success("Price master entry added.")
                st.rerun()


def admin_tickets():
    st.title("🎫 Tickets (Owner Requests / Issues)")

    tickets = db.list_all_tickets()
    if not tickets:
        st.info("No tickets yet.")
        return

    status_filter = st.selectbox(
        "Filter by Status",
        options=["All", "Open", "In Progress", "Resolved", "Closed"],
        index=0,
    )

    filtered = []
    for t in tickets:
        if status_filter == "All" or t["status"] == status_filter:
            filtered.append(t)

    for t in filtered:
        with st.expander(f"[{t['status']}] #{t['id']} - {t['property_name']} - {t['title']}"):
            st.write(f"**Property:** {t['property_name']}")
            st.write(f"**Owner:** {t['owner_username']}")
            st.write(f"**Created:** {t['created_at']}")
            st.write("---")
            st.write("**Description:**")
            st.write(t["description"])
            st.write("---")
            st.write("**Admin Comment:**")
            st.write(t["admin_comment"] or "_No comments yet._")

            new_status = st.selectbox(
                "Update Status",
                options=["Open", "In Progress", "Resolved", "Closed"],
                index=["Open", "In Progress", "Resolved", "Closed"].index(t["status"]),
                key=f"status_{t['id']}",
            )
            new_comment = st.text_area(
                "Add / Update Admin Comment",
                value=t["admin_comment"] or "",
                key=f"comment_{t['id']}",
            )
            if st.button("Save Changes", key=f"save_{t['id']}"):
                db.update_ticket(t["id"], new_status, new_comment)
                st.success("Ticket updated.")
                st.rerun()


def admin_service_personnel(user: Dict[str, Any]):
    st.title("🧑‍🔧 Service Personnel Management")
    st.markdown(
        "Maintain your landscaping crew/service person contact details and send reminders "
        "via email or SMS."
    )

    # --- Add New Service Person ---
    with st.expander("➕ Add New Service Person"):
        with st.form("add_service_person_form"):
            col_sp1, col_sp2 = st.columns(2)
            with col_sp1:
                full_name = st.text_input("Full Name")
                role = st.text_input("Role / Specialization", help="e.g., Mowing crew, Tree specialist, Irrigation tech")
            with col_sp2:
                email = st.text_input("Email")
                phone = st.text_input("Mobile Number (E.164, e.g. +15551234567)")
            notes = st.text_area("Notes (optional)", help="Service area, preferred days, certifications, etc.")
            is_active = st.checkbox("Active", value=True)
            submit_person = st.form_submit_button("Save Service Person", type="primary")
            if submit_person:
                if not full_name:
                    st.error("Full Name is required.")
                else:
                    db.add_service_person(full_name, email, phone, role, notes, is_active)
                    st.success("Service person saved.")
                    st.rerun()

    # --- List & Edit Service Persons ---
    persons = db.list_service_persons(active_only=False)
    if not persons:
        st.info("No service persons added yet.")
        return

    st.markdown("### Current Service Persons")
    df = pd.DataFrame(persons)
    if not df.empty:
        df_display = df.rename(
            columns={
                "full_name": "Full Name",
                "email": "Email",
                "phone": "Phone",
                "role": "Role",
                "notes": "Notes",
                "is_active": "Active",
            }
        )[["Full Name", "Email", "Phone", "Role", "Active"]]
        st.dataframe(df_display, use_container_width=True)
    else:
        st.info("No data to display.")

    st.markdown("### ✏️ Edit Service Person Details")
    for p in persons:
        header = p["full_name"]
        if p.get("role"):
            header += f" — {p['role']}"
        with st.expander(header):
            with st.form(f"edit_service_person_form_{p['id']}"):
                col_ep1, col_ep2 = st.columns(2)
                with col_ep1:
                    full_name_edit = st.text_input("Full Name", value=p["full_name"] or "")
                    role_edit = st.text_input("Role / Specialization", value=p["role"] or "")
                with col_ep2:
                    email_edit = st.text_input("Email", value=p["email"] or "")
                    phone_edit = st.text_input("Mobile Number (E.164)", value=p["phone"] or "")
                notes_edit = st.text_area("Notes", value=p["notes"] or "")
                is_active_edit = st.checkbox("Active", value=bool(p["is_active"]), key=f"active_{p['id']}")
                save_edit = st.form_submit_button("Save Changes")
                if save_edit:
                    if not full_name_edit:
                        st.error("Full Name is required.")
                    else:
                        db.update_service_person(
                            person_id=p["id"],
                            full_name=full_name_edit,
                            email=email_edit,
                            phone=phone_edit,
                            role=role_edit,
                            notes=notes_edit,
                            is_active=is_active_edit,
                        )
                        st.success("Service person updated.")
                        st.rerun()

    # --- Send Reminder to Service Persons ---
    st.markdown("### 📣 Send Reminder to Service Persons")
    active_persons = [p for p in persons if p.get("is_active")]
    if not active_persons:
        st.info("No active service persons to notify.")
        return

    label_map = {
        f"{p['full_name']} ({p.get('role','')})".strip().rstrip("()"): p
        for p in active_persons
    }
    selected_labels = st.multiselect(
        "Select recipients",
        options=list(label_map.keys()),
        help="Choose one or more crew members to notify.",
    )

    col_notif1, col_notif2 = st.columns(2)
    with col_notif1:
        send_email = st.checkbox("Send Email", value=True)
    with col_notif2:
        send_sms = st.checkbox("Send SMS (if configured)", value=False)

    default_subject = "Service schedule / work reminder"
    subject = st.text_input("Email Subject", value=default_subject)
    default_body = (
        "Hi,\n\n"
        "This is a reminder about your upcoming landscaping work. "
        "Please review your schedule and ensure you are prepared with the required tools and materials.\n\n"
        "Thank you."
    )
    body = st.text_area("Message Body", value=default_body, height=180)

    if st.button("Send Reminder", type="primary"):
        if not selected_labels:
            st.error("Please select at least one recipient.")
        else:
            email_count = 0
            sms_count = 0
            for label in selected_labels:
                p = label_map[label]
                if send_email and p.get("email"):
                    resp = send_email_notification(p["email"], subject, body)
                    if resp.startswith("Email sent"):
                        email_count += 1
                if send_sms and p.get("phone"):
                    resp = send_sms_notification(p["phone"], body)
                    if resp.startswith("SMS sent"):
                        sms_count += 1
            st.success(
                f"Reminder sent. Emails attempted to {email_count} contact(s), "
                f"SMS attempted to {sms_count} contact(s) (where contact info was available)."
            )






def admin_event_scheduler(user: Dict[str, Any]) -> None:
    """Admin module to schedule activities and send reminders to service providers."""
    st.title("📆 Event Scheduler & Activity Reminders")

    # Load basic lookup data
    properties = db.get_all_properties()
    service_persons = db.get_all_service_persons()

    if not properties:
        st.info("No properties available yet. Please add a property first.")
        return

    # --- Schedule New Activity ---
    st.markdown("### 📌 Schedule New Activity")
    with st.form("schedule_activity_form"):
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            prop_option_map = {f"{p['name']} (ID {p['id']})": p["id"] for p in properties}
            prop_label = st.selectbox("Property", list(prop_option_map.keys()))
            sel_property_id = prop_option_map[prop_label]

            # Load services for this property to allow linking
            services = db.get_services_for_property(sel_property_id)
            services = [dict(s) for s in services]

        with col_p2:
            service_options = {}
            for s in services:
                label = f"{s['category']} — {s['frequency']} (service #{s['id']})"
                service_options[label] = s
            service_labels = list(service_options.keys())
            service_labels.append("Ad-hoc / Custom activity")
            sel_service_label = st.selectbox(
                "Service / Activity",
                service_labels,
            )

        # Determine category & service_id
        sel_service_id: Optional[int] = None
        sel_category: str
        if sel_service_label == "Ad-hoc / Custom activity":
            sel_category = st.text_input("Custom Category / Activity Name", value="One-time visit")
        else:
            chosen = service_options[sel_service_label]
            sel_service_id = int(chosen["id"])
            sel_category = str(chosen["category"])

        # Assign provider (optional)
        provider_option_map = {"(Unassigned)": None}
        for sp in service_persons:
            if not sp.get("is_active", 1):
                continue
            label = f"{sp['full_name']} (ID {sp['id']})"
            provider_option_map[label] = sp["id"]
        provider_label = st.selectbox("Assign Service Person (optional)", list(provider_option_map.keys()))
        sel_provider_id = provider_option_map[provider_label]

        # Date & follow-up details
        today = date.today()
        scheduled_date = st.date_input("Scheduled Date", value=today)

        followup_required = st.checkbox(
            "Track this activity for follow-up (e.g., photo confirmation, QA check)",
            value=True,
        )
        followup_notes = st.text_area("Internal notes (visible only to admin)", "")

        create_evt = st.form_submit_button("Create Scheduled Activity", type="primary")

    if create_evt:
        if not sel_category:
            st.error("Activity category/name is required.")
        else:
            db.add_service_event(
                property_id=sel_property_id,
                service_id=sel_service_id,
                provider_id=sel_provider_id,
                service_category=sel_category,
                scheduled_date=scheduled_date.isoformat(),
                followup_required=followup_required,
                followup_notes=followup_notes,
            )
            st.success("Scheduled activity created.")
            st.rerun()

    st.markdown("---")
    st.markdown("### 📅 Upcoming, Due & Follow-up Activities")

    # Date range filter
    col_f1, col_f2 = st.columns(2)
    today = date.today()
    with col_f1:
        from_date = st.date_input("From date", value=today, key="evt_from")
    with col_f2:
        to_date = st.date_input("To date", value=today.replace(day=min(today.day + 7, 28)), key="evt_to")

    if from_date > to_date:
        st.error("From date cannot be after To date.")
        return

    events = db.get_scheduled_events(from_date.isoformat(), to_date.isoformat())

    if not events:
        st.info("No scheduled activities in this date range.")
        return

    # Compute due state
    today_str = today.isoformat()
    for e in events:
        if e["status"] != "Scheduled":
            e["due_state"] = e["status"]
        else:
            if e["scheduled_date"] < today_str:
                e["due_state"] = "Overdue"
            elif e["scheduled_date"] == today_str:
                e["due_state"] = "Due today"
            else:
                e["due_state"] = "Upcoming"

    # Summary table
    df_evt = pd.DataFrame(
        [
            {
                "ID": e["id"],
                "Date": e["scheduled_date"],
                "Property": e["property_name"],
                "Service / Activity": e["service_category"],
                "Provider": e.get("provider_name") or "(Unassigned)",
                "Status": e["status"],
                "Due / Follow-up State": e["due_state"],
                "Follow-up Required": bool(e["followup_required"]),
                "Last Reminder At": e.get("last_reminder_at"),
            }
            for e in events
        ]
    )

    st.dataframe(df_evt, use_container_width=True)

    st.markdown("---")
    st.markdown("### 🔁 Manage Individual Activities, Reminders & Follow-ups")

    for e in events:
        with st.expander(
            f"[# {e['id']}] {e['scheduled_date']} — {e['property_name']} — {e['service_category']}"
        ):
            st.write(f"**Property:** {e['property_name']}")
            st.write(f"**Service / Activity:** {e['service_category']}")
            st.write(f"**Scheduled Date:** {e['scheduled_date']}")
            st.write(f"**Current Status:** {e['status']} ({e['due_state']})")

            # Status & follow-up form
            with st.form(f"evt_status_form_{e['id']}"):
                col_s1, col_s2 = st.columns(2)
                with col_s1:
                    new_status = st.selectbox(
                        "Status",
                        ["Scheduled", "Completed", "Cancelled"],
                        index=["Scheduled", "Completed", "Cancelled"].index(e["status"]),
                    )
                with col_s2:
                    new_followup_required = st.checkbox(
                        "Follow-up required",
                        value=bool(e["followup_required"]),
                        key=f"evt_fu_{e['id']}",
                    )
                new_followup_notes = st.text_area(
                    "Follow-up notes",
                    value=e.get("followup_notes") or "",
                    key=f"evt_notes_{e['id']}",
                )
                save_evt = st.form_submit_button("Save Status / Follow-up")

            if save_evt:
                db.update_service_event_status(
                    event_id=e["id"],
                    status=new_status,
                    followup_required=new_followup_required,
                    followup_notes=new_followup_notes,
                )
                st.success("Event updated.")
                st.rerun()

            # Reminder section
            st.markdown("#### 📬 Send Reminder to Assigned Provider")
            if e.get("provider_id") and (e.get("provider_email") or e.get("provider_phone")):
                st.write(
                    f"Assigned to: **{e.get('provider_name')}** "
                    f"(Email: {e.get('provider_email') or 'N/A'}, Phone: {e.get('provider_phone') or 'N/A'})"
                )
                if e.get("last_reminder_at"):
                    st.caption(f"Last reminder sent at: {e['last_reminder_at']}")

                if st.button(
                    f"Send Reminder to Provider (Event #{e['id']})",
                    key=f"evt_rem_{e['id']}",
                ):
                    # Build simple reminder message
                    subject = f"Reminder: {e['service_category']} at {e['property_name']} on {e['scheduled_date']}"
                    body = (
                        f"Hello {e.get('provider_name') or ''},\n\n"
                        f"This is a friendly reminder to complete the following scheduled activity:\n\n"
                        f"- Property: {e['property_name']}\n"
                        f"- Activity: {e['service_category']}\n"
                        f"- Scheduled date: {e['scheduled_date']}\n\n"
                        f"Please update the status once completed.\n\n"
                        f"Regards,\nLandscaping Admin"
                    )

                    email_sent = False
                    sms_sent = False
                    if e.get("provider_email"):
                        try:
                            send_email_notification(e["provider_email"], subject, body)
                            email_sent = True
                        except Exception:
                            pass
                    if e.get("provider_phone"):
                        try:
                            send_sms_notification(e["provider_phone"], body)
                            sms_sent = True
                        except Exception:
                            pass

                    db.touch_service_event_reminder(e["id"])

                    st.success(
                        f"Reminder sent (email: {'yes' if email_sent else 'no'}, "
                        f"SMS: {'yes' if sms_sent else 'no'})."
                    )
            else:
                st.info(
                    "No assigned service person with contact info for this activity. "
                    "Assign a service person with email/phone in Service Personnel module first."
                )
def admin_reports(user: Dict[str, Any]):
    st.title("📑 Reports")

    mode = st.radio(
        "Report Type",
        ["Consolidated (All Properties)", "Per Property", "Per Owner"],
        horizontal=True,
    )

    if mode == "Consolidated (All Properties)":
        st.subheader("Consolidated Portfolio Overview")

        props_summary = db.get_properties_summary()
        owners = db.list_users(role="owner")
        services = db.get_all_services_with_property()
        tickets = db.list_all_tickets()

        total_props = len(props_summary)
        total_services = sum(p["total_services"] for p in props_summary) if props_summary else 0
        total_cost = sum(p["total_cost"] for p in props_summary) if props_summary else 0.0
        total_quoted = sum(p.get("annual_quote", 0.0) for p in props_summary) if props_summary else 0.0
        total_credited = sum(p.get("annual_credited", 0.0) for p in props_summary) if props_summary else 0.0
        total_margin = total_credited - total_cost
        total_owners = len(owners) if owners else 0
        total_tickets = len(tickets) if tickets else 0

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Total Properties", total_props)
        with c2:
            st.metric("Total Owners", total_owners)
        with c3:
            st.metric("Total Services (No. of Times)", int(total_services))
        with c4:
            st.metric("Total Annual Cost", f"${total_cost:,.2f}")

        c5, c6, c7 = st.columns(3)
        with c5:
            st.metric("Total Quoted Revenue", f"${total_quoted:,.2f}")
        with c6:
            st.metric("Total Credited Revenue", f"${total_credited:,.2f}")
        with c7:
            st.metric("Total Portfolio Margin", f"${total_margin:,.2f}")

        if props_summary:
            df_props = pd.DataFrame(
                [
                    {
                        "Property ID": r["id"],
                        "Property Name": r["name"],
                        "Total Services (No. of Times)": r["total_services"],
                        "Total Annual Cost": r["total_cost"],
                        "Annual Quoted Revenue": r.get("annual_quote", 0.0),
                        "Annual Credited Revenue": r.get("annual_credited", 0.0),
                    }
                    for r in props_summary
                ]
            )
            df_props["Credited Margin"] = df_props["Annual Credited Revenue"] - df_props["Total Annual Cost"]
            df_props["Credited ROI %"] = df_props.apply(
                lambda row: ((row["Credited Margin"] / row["Total Annual Cost"]) * 100.0)
                if row["Total Annual Cost"] > 0
                else None,
                axis=1,
            )
            st.markdown("#### Property Summary")
            st.dataframe(
                df_props.style.format(
                    {
                        "Total Annual Cost": "${:,.2f}".format,
                        "Annual Quoted Revenue": "${:,.2f}".format,
                        "Annual Credited Revenue": "${:,.2f}".format,
                        "Credited Margin": "${:,.2f}".format,
                        "Credited ROI %": "{:,.2f}%".format,
                    }
                ),
                use_container_width=True,
            )

            st.markdown("#### Annual Cost per Property")
            chart_df = df_props.set_index("Property Name")[["Total Annual Cost"]]
            st.bar_chart(chart_df)

        if services:
            st.markdown("#### Services Snapshot (All Properties)")
            df_services = pd.DataFrame(services)
            df_services["Total Cost"] = df_services["times_per_year"] * df_services["each_time_cost"]
            df_services = df_services.rename(
                columns={
                    "property_name": "Property Name",
                    "category": "Category",
                    "frequency": "Frequency",
                    "times_per_year": "No. of Times",
                    "each_time_cost": "Each Time Cost",
                    "status": "Status",
                    "start_date": "Start Date",
                    "end_date": "End Date",
                    "Total Cost": "Total Cost",
                }
            )
            st.dataframe(
                df_services[
                    ["Property Name", "Category", "Frequency", "No. of Times", "Each Time Cost", "Status"]
                ].style.format(
                    {
                        "Each Time Cost": "${:,.2f}".format,
                    }
                ),
                use_container_width=True,
            )

        # Consolidated Excel download
        st.markdown("#### Download Consolidated Excel Report")
        excel_buffer = generate_consolidated_excel()
        st.download_button(
            "⬇️ Download Consolidated Report",
            data=excel_buffer,
            file_name="landscaping_consolidated_report.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )

    elif mode == "Per Property":
        st.subheader("Per-Property Report")

        properties = db.get_all_properties()
        if not properties:
            st.warning("No properties found.")
            return

        property_options = {p["name"]: p["id"] for p in properties}
        selected_name = st.selectbox("Select a property", list(property_options.keys()))
        property_id = property_options[selected_name]

        prop = db.get_property_by_id(property_id)
        summary = db.get_property_summary(property_id)
        services = db.get_services_for_property(property_id)
        tickets = [t for t in db.list_all_tickets() if t["property_name"] == prop["name"]] if prop else []

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Total Services (No. of Times)", summary["total_services"])
        with c2:
            st.metric("Total Annual Cost", f"${summary['total_cost']:,.2f}")
        with c3:
            st.metric("Tickets (All Statuses)", len(tickets))

        if services:
            df = pd.DataFrame(services)
            df["Total Cost"] = df["times_per_year"] * df["each_time_cost"]
            df = df.rename(
                columns={
                    "category": "Category",
                    "frequency": "Frequency",
                    "times_per_year": "No. of Times",
                    "each_time_cost": "Each Time Cost",
                    "status": "Status",
                    "start_date": "Start Date",
                    "end_date": "End Date",
                }
            )
            st.markdown("#### Services for this Property")
            st.dataframe(
                df[["Category", "Frequency", "No. of Times", "Each Time Cost", "Status", "Start Date", "End Date", "Total Cost"]].style.format(
                    {
                        "Each Time Cost": "${:,.2f}".format,
                        "Total Cost": "${:,.2f}".format,
                    }
                ),
                use_container_width=True,
            )
        else:
            st.info("No services found for this property.")

        if tickets:
            df_t = pd.DataFrame(tickets)
            df_t = df_t.rename(
                columns={
                    "id": "Ticket ID",
                    "title": "Title",
                    "status": "Status",
                    "created_at": "Created At",
                    "updated_at": "Updated At",
                    "owner_username": "Owner Username",
                }
            )
            st.markdown("#### Tickets for this Property")
            st.dataframe(
                df_t[["Ticket ID", "Title", "Status", "Owner Username", "Created At", "Updated At"]],
                use_container_width=True,
            )
        else:
            st.info("No tickets for this property.")

        excel_buffer = generate_property_excel(property_id)
        safe_name = prop["name"].replace(" ", "_").replace("/", "_") if prop else f"property_{property_id}"
        st.markdown("#### Download Property Excel Report")
        st.download_button(
            "⬇️ Download Property Report",
            data=excel_buffer,
            file_name=f"{safe_name}_report.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )

    else:  # Per Owner
        st.subheader("Per-Owner Report")

        owners = db.list_users(role="owner")
        if not owners:
            st.info("No owners found.")
            return

        owner_label_map = {
            f"{o['full_name']} ({o['username']}) - {o.get('property_name') or 'No property'}": o
            for o in owners
        }
        selected_label = st.selectbox("Select an owner", list(owner_label_map.keys()))
        owner = owner_label_map[selected_label]

        property_id = owner.get("property_id")
        if not property_id:
            st.warning("This owner is not yet mapped to any property.")
            return

        prop = db.get_property_by_id(property_id)
        summary = db.get_property_summary(property_id)
        services = db.get_services_for_property(property_id)
        tickets = db.list_tickets_for_owner(owner["id"])

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Property", prop["name"] if prop else "N/A")
        with c2:
            st.metric("Total Services (No. of Times)", summary["total_services"])
        with c3:
            st.metric("Total Annual Cost", f"${summary['total_cost']:,.2f}")

        if services:
            df = pd.DataFrame(services)
            df["Total Cost"] = df["times_per_year"] * df["each_time_cost"]
            df = df.rename(
                columns={
                    "category": "Category",
                    "frequency": "Frequency",
                    "times_per_year": "No. of Times",
                    "each_time_cost": "Each Time Cost",
                    "status": "Status",
                    "start_date": "Start Date",
                    "end_date": "End Date",
                }
            )
            st.markdown("#### Services for Owner's Property")
            st.dataframe(
                df[["Category", "Frequency", "No. of Times", "Each Time Cost", "Status", "Start Date", "End Date", "Total Cost"]].style.format(
                    {
                        "Each Time Cost": "${:,.2f}".format,
                        "Total Cost": "${:,.2f}".format,
                    }
                ),
                use_container_width=True,
            )
        else:
            st.info("No services found for this property.")

        if tickets:
            df_t = pd.DataFrame(tickets)
            df_t = df_t.rename(
                columns={
                    "id": "Ticket ID",
                    "title": "Title",
                    "status": "Status",
                    "created_at": "Created At",
                    "updated_at": "Updated At",
                }
            )
            st.markdown("#### Tickets from this Owner")
            st.dataframe(
                df_t[["Ticket ID", "Title", "Status", "Created At", "Updated At"]],
                use_container_width=True,
            )
        else:
            st.info("No tickets raised by this owner.")

        excel_buffer = generate_property_excel(property_id)
        safe_name = (prop["name"] if prop else f"owner_{owner['username']}").replace(" ", "_").replace("/", "_")
        st.markdown("#### Download Owner Property Report")
        st.download_button(
            "⬇️ Download Owner's Property Report",
            data=excel_buffer,
            file_name=f"{safe_name}_owner_report.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )




def admin_user_management(user: Dict[str, Any]):
    st.title("👥 User & Login Management")
    st.markdown(
        "Create, edit, and delete user logins (primarily property owners). "
        "Passwords are stored as secure hashes in the database."
    )

    properties = db.get_all_properties()
    property_options = {"-- None --": None}
    for p in properties:
        property_options[f"{p['name']} (id={p['id']})"] = p["id"]

    # --- Add New User ---
    with st.expander("➕ Add New User"):
        with st.form("add_user_form"):
            col1, col2 = st.columns(2)
            with col1:
                username = st.text_input("Username")
                full_name = st.text_input("Full Name")
                role = st.selectbox("Role", ["owner", "admin"], index=0)
            with col2:
                email = st.text_input("Email")
                phone = st.text_input("Mobile Number")
            property_label = st.selectbox(
                "Property (for owners)",
                options=list(property_options.keys()),
                index=0,
                help="If role is 'owner', select the property this user owns.",
            )
            password = st.text_input("Initial Password", type="password")
            submitted = st.form_submit_button("Create User", type="primary")
            if submitted:
                if not username or not full_name or not password:
                    st.error("Username, Full Name, and Initial Password are required.")
                else:
                    prop_id = property_options[property_label]
                    if role == "owner" and prop_id is None:
                        st.error("Owners must be mapped to a property.")
                    else:
                        try:
                            db.add_user(
                                username=username,
                                full_name=full_name,
                                email=email,
                                role=role,
                                password=password,
                                property_id=prop_id,
                                phone=phone,
                            )
                            st.success("User created successfully.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error creating user: {e}")

    # --- Existing Users ---
    st.markdown("### Existing Users")
    users = db.list_users(role=None)
    if not users:
        st.info("No users found in the system.")
        return

    df_users = []
    for u in users:
        df_users.append(
            {
                "Username": u["username"],
                "Full Name": u["full_name"],
                "Role": u["role"],
                "Email": u["email"],
                "Phone": u["phone"],
                "Property": u.get("property_name") or "",
            }
        )
    st.dataframe(
        pd.DataFrame(df_users),
        use_container_width=True,
    )

    st.markdown("### ✏️ Edit / Delete Users")
    for u in users:
        header = f"{u['username']} — {u['role']}"
        if u.get("property_name"):
            header += f" ({u['property_name']})"
        with st.expander(header):
            with st.form(f"edit_user_form_{u['id']}"):
                col1, col2 = st.columns(2)
                with col1:
                    full_name_edit = st.text_input("Full Name", value=u["full_name"] or "")
                    role_edit = st.selectbox(
                        "Role",
                        ["owner", "admin"],
                        index=["owner", "admin"].index(u["role"]) if u["role"] in ["owner", "admin"] else 0,
                    )
                with col2:
                    email_edit = st.text_input("Email", value=u["email"] or "")
                    phone_edit = st.text_input("Mobile Number", value=u["phone"] or "")
                property_label_edit = st.selectbox(
                    "Property (for owners)",
                    options=list(property_options.keys()),
                    index=list(property_options.values()).index(u["property_id"]) if u["property_id"] in property_options.values() else 0,
                )
                new_password = st.text_input(
                    "New Password (leave blank to keep current)",
                    type="password",
                )
                col_btn1, col_btn2 = st.columns(2)
                save_btn = col_btn1.form_submit_button("Save Changes")
                delete_btn = col_btn2.form_submit_button("Delete User", type="secondary")

                if save_btn:
                    prop_id_edit = property_options[property_label_edit]
                    if role_edit == "owner" and prop_id_edit is None:
                        st.error("Owners must be mapped to a property.")
                    else:
                        try:
                            db.update_user(
                                user_id=u["id"],
                                full_name=full_name_edit,
                                email=email_edit,
                                role=role_edit,
                                property_id=prop_id_edit,
                                phone=phone_edit,
                                new_password=new_password or None,
                            )
                            st.success("User updated successfully.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error updating user: {e}")

                if delete_btn:
                    if u["username"] == user["username"]:
                        st.error("You cannot delete the currently logged-in user.")
                    elif u["username"] == "admin":
                        st.error("You cannot delete the default admin user.")
                    else:
                        try:
                            db.delete_user(u["id"])
                            st.success("User deleted successfully.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error deleting user: {e}")


def owner_dashboard(user: Dict[str, Any]):
    st.title("📊 My Property Dashboard")

    property_id = user["property_id"]
    if not property_id:
        st.warning("No property assigned to this user.")
        return

    prop = db.get_property_by_id(property_id)
    if not prop:
        st.error("Assigned property not found in DB.")
        return

    col_info, col_summary = st.columns([2, 1])
    with col_info:
        st.subheader("Property Details")
        st.write(f"**Name:** {prop['name']}")
        st.write(f"**Address:** {prop['address']}")
        st.write(f"**City/State/ZIP:** {prop['city']}, {prop['state']} {prop['zip']}")

    with col_summary:
        summary = db.get_property_summary(property_id)
        st.subheader("Summary")
        st.metric("Total Services (No. of Times)", summary["total_services"])
        st.metric(
            "Total Annual Cost",
            f"${summary['total_cost']:.2f}",
        )

        # Excel export
        excel_buffer = generate_property_excel(property_id)
        safe_name = prop['name'].replace(" ", "_").replace("/", "_")
        st.download_button(
            "⬇️ Download Excel for my property",
            data=excel_buffer,
            file_name=f"{safe_name}_landscaping.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )

    st.markdown("### Services for My Property")
    services = db.get_services_for_property(property_id)
    services = [dict(s) for s in services]
    if services:
        svc_df = pd.DataFrame(services)
        svc_df["Total Cost"] = svc_df["times_per_year"] * svc_df["each_time_cost"]
        svc_df = svc_df.rename(
            columns={
                "category": "Category",
                "frequency": "Frequency",
                "times_per_year": "No. of Times",
                "each_time_cost": "Each Time Cost",
                "status": "Status",
                "start_date": "Start Date",
                "end_date": "End Date",
            }
        )
        st.dataframe(
            svc_df.style.format(
                {
                    "Each Time Cost": "${:,.2f}".format,
                    "Total Cost": "${:,.2f}".format,
                }
            ),
            use_container_width=True,
        )
    else:
        st.info("No services configured yet for your property.")

    st.markdown("### 📎 Attachments by Service")
    if services:
        for s in services:
            attachments = db.get_service_attachments(s["id"])
            if not attachments:
                continue
            with st.expander(
                f"{s['category']} ({s['frequency']}) — Status: {s.get('status','Scheduled')}"
            ):
                for att in attachments:
                    st.write(
                        f"**{att['file_name']}** "
                        f"(uploaded {att['uploaded_at']}, by {att['uploaded_by']})"
                    )
                    if att["file_path"] and os.path.exists(att["file_path"]):
                        st.image(att["file_path"], width=250)

    st.markdown("---")
    render_chat(user)


def owner_tickets(user: Dict[str, Any]):
    st.title("🎫 My Tickets")

    property_id = user["property_id"]
    if not property_id:
        st.warning("No property assigned to this user.")
        return

    # Create ticket form
    st.markdown("### ➕ Raise a New Ticket / Request")
    with st.form("new_ticket_form"):
        title = st.text_input("Title")
        description = st.text_area(
            "Describe your request or issue",
            help="Example: Need to add extra weed control in the backyard, or question about last invoice.",
        )
        submitted = st.form_submit_button("Submit Ticket", type="primary")
        if submitted:
            if not title or not description:
                st.error("Title and description are required.")
            else:
                db.create_ticket(
                    property_id=property_id,
                    owner_id=user["id"],
                    title=title,
                    description=description,
                )
                st.success("Ticket submitted successfully.")
                st.rerun()

    st.markdown("### Existing Tickets")
    tickets = db.list_tickets_for_owner(user["id"])
    if not tickets:
        st.info("You have not created any tickets yet.")
        return

    for t in tickets:
        with st.expander(f"[{t['status']}] #{t['id']} - {t['title']}"):
            st.write(f"**Status:** {t['status']}")
            st.write(f"**Created:** {t['created_at']}")
            st.write("---")
            st.write("**Description:**")
            st.write(t["description"])
            st.write("---")
            st.write("**Admin Comment:**")
            st.write(t["admin_comment"] or "_No comments yet._")


# ---------- Main Router ----------

def main():
    user = st.session_state.user

    if not user:
        login_page()
        return

    # Sidebar nav
    with st.sidebar:
        st.markdown("### 👤 Logged in as")
        st.write(f"**{user['full_name']}**")
        st.write(f"Role: `{user['role']}`")

        st.markdown("---")

        if user["role"] == "admin":
            page = st.radio(
                "Navigation",
                [
                    "Admin Dashboard",
                    "Manage Properties & Services",
                    "Price Master",
                    "Service Personnel",
                    "Event Scheduler",
                    "Reports",
                    "User Management",
                    "Tickets",
                    "Logout",
                ],
            )
        else:
            page = st.radio(
                "Navigation",
                [
                    "My Property Dashboard",
                    "My Tickets",
                    "Logout",
                ],
            )

    if page == "Logout":
        logout()
        st.rerun()
        return

    if user["role"] == "admin":
        if page == "Admin Dashboard":
            admin_dashboard(user)
        elif page == "Manage Properties & Services":
            admin_manage_properties(user)
        elif page == "Price Master":
            admin_price_master()
        elif page == "Service Personnel":
            admin_service_personnel(user)
        elif page == "Event Scheduler":
            admin_event_scheduler(user)
        elif page == "Reports":
            admin_reports(user)
        elif page == "User Management":
            admin_user_management(user)
        elif page == "Tickets":
            admin_tickets()
    else:
        if page == "My Property Dashboard":
            owner_dashboard(user)
        elif page == "My Tickets":
            owner_tickets(user)


if __name__ == "__main__":
    main()
