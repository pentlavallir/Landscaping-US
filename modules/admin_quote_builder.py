
from io import BytesIO
from typing import Dict, Any, List, Optional

import pandas as pd
import streamlit as st

import db
from utils.email_utils import send_quote_email


def show(user: Dict[str, Any]) -> None:
    st.title("📋 Quote Builder – Region-based Pricing")

    st.write(
        "Use this tool to build a standard service quote for a property based on "
        "state / city / property type. Currently optimised for Texas → Frisco → Small Industrial."
    )

    regions = db.get_regions()
    if not regions:
        st.error("No regions configured. Please check DB seeding.")
        return

    # Build region display labels
    options = {f"{r['state']} - {r['city']} - {r['property_type']}": r["id"] for r in regions}
    default_label: Optional[str] = None
    for label in options.keys():
        if "TX - Frisco" in label:
            default_label = label
            break
    labels = list(options.keys())
    default_index = labels.index(default_label) if default_label in labels else 0

    region_label = st.selectbox("Region / Property Type", labels, index=default_index)
    region_id = options[region_label]
    region = db.get_region_by_id(region_id)

    # Property & customer details
    with st.expander("🏭 Property & Customer Details", expanded=False):
        customer_name = st.text_input("Customer Name")
        customer_email = st.text_input("Customer Email (for sending quote)")
        property_name = st.text_input("Property Name / Site Label")

        col1, col2 = st.columns(2)
        with col1:
            size_band = st.selectbox(
                "Property Size Band",
                ["0–5,000 sqft", "5,001–10,000 sqft", "10,001–20,000 sqft", ">20,000 sqft"],
                index=1,
            )
        with col2:
            est_sqft = st.number_input(
                "Estimated Square Footage", min_value=0, step=500, value=8000
            )
        notes = st.text_area("Internal Notes (optional)")
        st.caption(
            "These fields are stored when you save a quote and can be reused in follow-ups or future versions."
        )

    st.markdown("### 📦 Standard Service Package for this Region")

    rates = db.get_region_service_rates(region_id)
    if not rates:
        st.warning(
            f"No region-specific service rates configured for {region_label}. "

            "Please configure region_service_rates in the database."
        )
        return

    st.caption(
        "You can tweak times/year and price per visit for this specific customer. "
        "Uncheck *Include* to remove a service from this quote."
    )

    line_items: List[Dict[str, Any]] = []
    total_annual = 0.0

    for r in rates:
        code = r["service_code"]
        display = r["display_name"]
        default_times = int(r.get("default_times_per_year") or 0)
        base_price = float(r.get("base_price_per_visit") or 0.0)

        with st.container():
            col_svc, col_times, col_price, col_include = st.columns([3, 1, 1, 1])
            with col_svc:
                st.markdown(f"**{display}**")
                st.caption(f"Code: {code}")
            with col_times:
                times_per_year = st.number_input(
                    "Times / Year",
                    min_value=0,
                    step=1,
                    value=default_times,
                    key=f"qt_times_{code}",
                )
            with col_price:
                price_per_visit = st.number_input(
                    "Price / Visit ($)",
                    min_value=0.0,
                    step=5.0,
                    value=base_price,
                    key=f"qt_price_{code}",
                )
            with col_include:
                include = st.checkbox(
                    "Include",
                    value=True,
                    key=f"qt_include_{code}",
                )

        annual = float(times_per_year) * float(price_per_visit) if include else 0.0
        total_annual += annual

        line_items.append(
            {
                "service_code": code,
                "service_name": display,
                "times_per_year": int(times_per_year),
                "price_per_visit": float(price_per_visit),
                "annual_total": annual,
                "included": bool(include),
            }
        )

    st.markdown("---")
    st.subheader("💰 Quote Summary")

    df_quote = pd.DataFrame(
        [
            {
                "Service": li["service_name"],
                "Service Code": li["service_code"],
                "Times / Year": li["times_per_year"],
                "Price / Visit ($)": li["price_per_visit"],
                "Annual Line Total ($)": li["annual_total"],
                "Included": "Yes" if li.get("included", True) else "No",
            }
            for li in line_items
        ]
    )
    st.dataframe(
        df_quote[
            ["Service", "Times / Year", "Price / Visit ($)", "Annual Line Total ($)", "Included"]
        ],
        use_container_width=True,
    )

    monthly = total_annual / 12.0 if total_annual else 0.0
    est_cost = total_annual * 0.6
    est_margin = total_annual - est_cost
    est_margin_pct = (est_margin / total_annual * 100.0) if total_annual else 0.0

    col_a, col_m, col_c = st.columns(3)
    col_a.metric("Annual Quote (before tax)", f"${total_annual:,.0f}")
    col_m.metric("Approx. Monthly", f"${monthly:,.0f}")
    col_c.metric("Est. Margin", f"${est_margin:,.0f}", f"{est_margin_pct:,.1f}%")

    st.caption(
        "Margin is estimated using a simple assumption that 60% of revenue goes to direct costs. "
        "You can refine this by plugging real labour and material costs into the system."
    )

    # -------- Save Quote, Download, Email, Convert --------
    st.markdown("---")
    st.subheader("💾 Save & Share Quote")

    # We'll keep region_label visible in UI
    st.write(f"**Selected Region:** {region_label}")

    # Use a form so we don't accidentally trigger on every keystroke
    with st.form("quote_save_form"):
        submit_save = st.form_submit_button("💾 Save Quote", type="primary")

    quote_id: Optional[int] = None
    if submit_save:
        if total_annual <= 0:
            st.error("Annual quote must be greater than 0 to save.")
        else:
            quote_id = db.add_quote(
                region_label=region_label,
                customer_name=customer_name or None,
                customer_email=customer_email or None,
                property_name=property_name or None,
                property_size_band=size_band or None,
                sqft_estimate=int(est_sqft) if est_sqft else None,
                notes=notes or None,
                annual_quote=float(total_annual),
                line_items=line_items,
            )
            st.success(f"Quote #{quote_id} saved successfully.")

    # Always allow download of the current configuration (even if unsaved)
    from io import BytesIO

    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        df_quote.to_excel(writer, index=False, sheet_name="Quote")

        summary_df = pd.DataFrame(
            {
                "Metric": ["Region", "Customer", "Property", "Annual Quote", "Monthly (approx)"],
                "Value": [
                    region_label,
                    customer_name or "",
                    property_name or "",
                    f"${total_annual:,.2f}",
                    f"${monthly:,.2f}",
                ],
            }
        )
        summary_df.to_excel(writer, index=False, sheet_name="Summary")
    excel_buffer.seek(0)

    st.download_button(
        label="⬇️ Download Quote (Excel)",
        data=excel_buffer,
        file_name=f"quote_{quote_id or 'draft'}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.markdown("### 📧 Email Quote to Customer")

    if not customer_email:
        st.info("Enter a customer email above to enable sending the quote.")
    else:
        if st.button("📧 Send Quote via Email"):
            try:
                subject = f"Landscaping Quote for {property_name or 'your property'}"
                body = (
                    f"Hello {customer_name or ''},\n\n"
                    "Attached is your landscaping quote based on the agreed service package.\n"
                    f"Region: {region_label}\n"
                    f"Annual total: ${total_annual:,.2f}\n\n"
                    "Please review and let us know if you have any questions.\n\n"
                    "Thank you,\nYour Landscaping Team"
                )

                send_quote_email(
                    to_email=customer_email,
                    subject=subject,
                    body=body,
                    attachment_bytes=excel_buffer.getvalue(),
                    attachment_filename=f"quote_{quote_id or 'draft'}.xlsx",
                )
                st.success(f"Quote emailed to {customer_email}.")
            except Exception as e:
                st.error(f"Failed to send email: {e}")

    st.markdown("### 🏢 Convert Quote to Property")

    st.caption(
        "Once a customer accepts this quote, you can convert it into an active property. "
        "This will create a new property record and seed its services using the line items above."
    )

    # Only allow conversion if quote has been saved in this run
    if quote_id is None:
        st.info("Save the quote first to enable conversion to a property.")
    else:
        if st.button("🏢 Convert Saved Quote to Property"):
            new_prop_id = db.convert_quote_to_property(quote_id)
            if not new_prop_id:
                st.error("Could not convert quote to property.")
            else:
                st.success(
                    f"Quote #{quote_id} converted to Property ID={new_prop_id}. "
                    "You can review it under 'Manage Properties & Services'."
                )
