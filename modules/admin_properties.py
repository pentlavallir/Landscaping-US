
from io import BytesIO
from typing import Dict, Any, List, Optional

import pandas as pd
import streamlit as st

import db


def show(user: Dict[str, Any]) -> None:
    st.title("🏢 Manage Properties & Services")

    properties = db.get_all_properties()
    if not properties:
        st.info("No properties found.")
        return

    prop_names = [p["name"] for p in properties]
    name_to_id = {p["name"]: p["id"] for p in properties}

    selected_name = st.selectbox("Select Property", options=prop_names)
    property_id = name_to_id[selected_name]
    prop = db.get_property_by_id(property_id)

    st.markdown(f"### {prop['name']}")
    st.caption(f"{prop.get('address') or ''}, {prop.get('city') or ''}, {prop.get('state') or ''} {prop.get('zip') or ''}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Annual Quote", f"${prop.get('annual_quote', 0):,.0f}")
    col2.metric("Annual Credited", f"${prop.get('annual_credited', 0):,.0f}")
    col3.metric("Annual Cost", f"${prop.get('annual_cost', 0):,.0f}")

    # Edit property details in expander
    with st.expander("✏️ Edit Property Details", expanded=False):
        with st.form("edit_property_form"):
            name = st.text_input("Property Name", value=prop.get("name", ""))
            addr = st.text_input("Address", value=prop.get("address", ""))
            city = st.text_input("City", value=prop.get("city", ""))
            state = st.text_input("State", value=prop.get("state", ""))
            zip_code = st.text_input("ZIP", value=prop.get("zip", ""))

            colq, colcr, colc = st.columns(3)
            with colq:
                annual_quote = st.number_input(
                    "Annual Quoted Revenue",
                    min_value=0.0,
                    value=float(prop.get("annual_quote") or 0.0),
                    step=100.0,
                )
            with colcr:
                annual_credited = st.number_input(
                    "Annual Credited Revenue",
                    min_value=0.0,
                    value=float(prop.get("annual_credited") or 0.0),
                    step=100.0,
                )
            with colc:
                annual_cost = st.number_input(
                    "Annual Cost (Services)",
                    min_value=0.0,
                    value=float(prop.get("annual_cost") or 0.0),
                    step=100.0,
                )

            submitted = st.form_submit_button("Save Property")
        if submitted:
            db.update_property(
                property_id,
                name=name,
                address=addr,
                city=city,
                state=state,
                zip_code=zip_code,
                annual_quote=annual_quote,
                annual_credited=annual_credited,
                annual_cost=annual_cost,
            )
            st.success("Property updated.")
            st.rerun()

    st.markdown("### Services for this Property")

    services = db.get_services_for_property(property_id)
    if services:
        df = pd.DataFrame(services)
        df_view = df[["id", "category", "frequency", "times_per_year", "each_time_cost", "notes"]]
        st.dataframe(df_view, use_container_width=True)
    else:
        st.info("No services configured for this property.")

    # Add / edit service in expander
    with st.expander("➕ Add / Edit Service", expanded=False):
        service_ids = [s["id"] for s in services]
        service_lookup = {s["id"]: s for s in services}
        service_options = ["(New service)"] + [
            f"{s['id']} - {s['category']}" for s in services
        ]
        selection = st.selectbox("Select existing service or choose new", service_options)
        editing_existing: Optional[Dict[str, Any]] = None
        if selection != "(New service)":
            sid = int(selection.split(" - ")[0])
            editing_existing = service_lookup[sid]

        with st.form("service_form"):
            category = st.text_input(
                "Category",
                value=editing_existing["category"] if editing_existing else "",
                placeholder="e.g. Mowing, Weed Control Spraying",
            )
            frequency = st.text_input(
                "Frequency",
                value=editing_existing["frequency"] if editing_existing else "",
                placeholder="e.g. Weekly (22 Visits), 3 Times / Year",
            )
            times_per_year = st.number_input(
                "Times per Year",
                min_value=0,
                value=int(editing_existing["times_per_year"]) if editing_existing else 0,
                step=1,
            )
            each_time_cost = st.number_input(
                "Cost per Visit",
                min_value=0.0,
                value=float(editing_existing["each_time_cost"]) if editing_existing else 0.0,
                step=10.0,
            )
            notes = st.text_area(
                "Notes",
                value=editing_existing.get("notes", "") if editing_existing else "",
            )

            col_sa, col_del = st.columns(2)
            with col_sa:
                save_btn = st.form_submit_button("Save Service")
            with col_del:
                delete_btn = st.form_submit_button("Delete Service")

        if save_btn:
            if not category.strip():
                st.error("Category is required.")
            else:
                if editing_existing:
                    db.update_property_service(
                        editing_existing["id"],
                        category=category.strip(),
                        frequency=frequency.strip(),
                        times_per_year=int(times_per_year),
                        each_time_cost=float(each_time_cost),
                        notes=notes.strip(),
                    )
                    st.success("Service updated.")
                else:
                    db.add_property_service(
                        property_id,
                        category=category.strip(),
                        frequency=frequency.strip(),
                        times_per_year=int(times_per_year),
                        each_time_cost=float(each_time_cost),
                        notes=notes.strip(),
                    )
                    st.success("Service added.")
                st.rerun()

        if delete_btn and editing_existing:
            db.delete_property_service(editing_existing["id"])
            st.success("Service deleted.")
            st.rerun()

    st.markdown("### 📊 Service Fulfilment")

    current_year = pd.Timestamp.today().year
    year = st.selectbox(
        "Fulfilment Year",
        options=list(range(current_year - 2, current_year + 1)),
        index=2,
        key="prop_fulfil_year",
    )

    fulfil = db.get_service_fulfilment_for_property(property_id, year)
    if not fulfil:
        st.info("No fulfilment data available yet.")
    else:
        df_f = pd.DataFrame(
            [
                {
                    "Service": r["category"],
                    "Frequency": r["frequency"],
                    "Planned Times / Year": r["times_per_year"],
                    "Completed (YTD)": r["completed_count"],
                    "Pending (YTD)": r["pending_count"],
                    "Completion %": round(r["completion_pct"], 1) if r["completion_pct"] is not None else None,
                }
                for r in fulfil
            ]
        )

        def status_for_row(row):
            if row["Planned Times / Year"] == 0:
                return "Not configured"
            if row["Pending (YTD)"] == 0:
                return "On Track"
            if row["Completed (YTD)"] == 0:
                return "Not Started"
            return "In Progress"

        df_f["Status"] = df_f.apply(status_for_row, axis=1)

        def highlight_row(r):
            status = r["Status"]
            if status == "On Track":
                color = "#d4f4dd"
            elif status == "In Progress":
                color = "#fff4ce"
            elif status == "Not Started":
                color = "#fddede"
            else:
                color = "#ffffff"
            return [f"background-color: {color}"] * len(r)

        st.dataframe(df_f.style.apply(highlight_row, axis=1), use_container_width=True)

        # Excel download
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df_f.to_excel(writer, index=False, sheet_name="Fulfilment")
        st.download_button(
            "⬇️ Download Service Fulfilment (Excel)",
            data=buf.getvalue(),
            file_name=f"property_{property_id}_fulfilment_{year}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    st.markdown("---")

    # Add new property in expander
    with st.expander("➕ Add New Property", expanded=False):
        with st.form("add_property_form"):
            name = st.text_input("Property Name")
            addr = st.text_input("Address")
            city = st.text_input("City")
            state = st.text_input("State", value="TX")
            zip_code = st.text_input("ZIP")

            colq, colcr, colc = st.columns(3)
            with colq:
                annual_quote = st.number_input("Annual Quoted Revenue", min_value=0.0, step=100.0)
            with colcr:
                annual_credited = st.number_input("Annual Credited Revenue", min_value=0.0, step=100.0)
            with colc:
                annual_cost = st.number_input("Annual Cost (Services)", min_value=0.0, step=100.0)

            add_btn = st.form_submit_button("Add Property")

        if add_btn:
            if not name.strip():
                st.error("Property name is required.")
            else:
                pid = db.add_property(
                    name=name.strip(),
                    address=addr.strip(),
                    city=city.strip(),
                    state=state.strip(),
                    zip_code=zip_code.strip(),
                    annual_quote=annual_quote,
                    annual_credited=annual_credited,
                    annual_cost=annual_cost,
                )
                st.success(f"Property '{name}' added (ID={pid}).")
                st.rerun()
