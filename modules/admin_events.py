
from typing import Dict, Any, List, Optional
import datetime

import pandas as pd
import streamlit as st

import db


def show(user: Dict[str, Any]) -> None:
    st.title("🗓️ Event Scheduler")

    properties = db.get_all_properties()
    if not properties:
        st.info("No properties configured.")
        return

    persons = db.get_all_service_persons()

    # Schedule new activity
    with st.expander("➕ Schedule New Activity", expanded=False):
        with st.form("new_event_form"):
            colp, cols = st.columns(2)
            with colp:
                prop_options = {p["name"]: p["id"] for p in properties}
                prop_name = st.selectbox("Property", list(prop_options.keys()))
                property_id = prop_options[prop_name]
            with cols:
                services = db.get_services_for_property(property_id)
                svc_options = ["(Ad-hoc)"] + [f"{s['id']} - {s['category']}" for s in services]
                svc_sel = st.selectbox("Service", svc_options)
                service_id: Optional[int] = None
            if svc_sel != "(Ad-hoc)":
                service_id = int(svc_sel.split(" - ")[0])
                service_category = [s for s in services if s["id"] == service_id][0]["category"]
            else:
                service_category = st.text_input("Ad-hoc Service Category", value="Ad-hoc Service")

            cold, colt = st.columns(2)
            with cold:
                date = st.date_input("Scheduled Date", value=datetime.date.today())
            with colt:
                time = st.time_input("Scheduled Time", value=datetime.time(9, 0))

            colsp, colfollow = st.columns(2)
            with colsp:
                if persons:
                    person_map = {p["full_name"]: p["id"] for p in persons}
                    provider_name = st.selectbox("(Optional) Service Person", ["(Unassigned)"] + list(person_map.keys()))
                    provider_id = None
                    if provider_name != "(Unassigned)":
                        provider_id = person_map[provider_name]
                else:
                    st.caption("No service personnel available.")
                    provider_id = None

            with colfollow:
                followup_required = st.checkbox("Follow-up required?", value=False)
                followup_notes = st.text_area("Follow-up notes", value="", height=60)

            submit = st.form_submit_button("Create Event")

        if submit:
            if not service_category.strip():
                st.error("Service category is required.")
            else:
                db.add_service_event(
                    property_id=property_id,
                    service_id=service_id,
                    provider_id=provider_id,
                    service_category=service_category.strip(),
                    scheduled_date=date.isoformat(),
                    scheduled_time=time.strftime("%H:%M"),
                    followup_required=followup_required,
                    followup_notes=followup_notes.strip(),
                )
                st.success("Event scheduled.")
                st.rerun()

    st.markdown("### Upcoming & Recent Events")

    today = datetime.date.today()
    default_start = today - datetime.timedelta(days=7)
    default_end = today + datetime.timedelta(days=30)

    col_from, col_to = st.columns(2)
    with col_from:
        from_date = st.date_input("From Date", value=default_start)
    with col_to:
        to_date = st.date_input("To Date", value=default_end)

    events = db.get_scheduled_events(from_date.isoformat(), to_date.isoformat())
    if not events:
        st.info("No events in this range.")
        return

    df = pd.DataFrame(
        [
            {
                "ID": e["id"],
                "Date": e["scheduled_date"],
                "Time": e.get("scheduled_time") or "",
                "Property": e["property_name"],
                "Service": e["service_category"],
                "Status": e["status"],
                "Provider": e.get("provider_name") or "",
            }
            for e in events
        ]
    )
    st.dataframe(df, use_container_width=True)

    st.markdown("### Manage Individual Events")
    for e in events:
        with st.expander(
            f"[#{e['id']}] {e['scheduled_date']} {e.get('scheduled_time') or ''} — {e['property_name']} — {e['service_category']}",
            expanded=False,
        ):
            st.write(f"**Property:** {e['property_name']}")
            st.write(f"**Service:** {e['service_category']}")
            st.write(f"**Status:** {e['status']}")
            st.write(f"**Provider:** {e.get('provider_name') or '(Unassigned)'}")
            if e.get("followup_required"):
                st.write("**Follow-up required** ✅")
                if e.get("followup_notes"):
                    st.write(f"Notes: {e['followup_notes']}")

            with st.form(f"event_form_{e['id']}"):
                col1, col2 = st.columns(2)
                with col1:
                    status = st.selectbox(
                        "Status",
                        ["Scheduled", "Completed", "Cancelled"],
                        index=["Scheduled", "Completed", "Cancelled"].index(e["status"])
                        if e["status"] in ["Scheduled", "Completed", "Cancelled"]
                        else 0,
                    )
                with col2:
                    followup_required = st.checkbox(
                        "Follow-up required",
                        value=bool(e.get("followup_required")),
                    )
                followup_notes = st.text_area(
                    "Follow-up notes",
                    value=e.get("followup_notes") or "",
                )
                colu, cold = st.columns(2)
                with colu:
                    save_btn = st.form_submit_button("Save Changes")
                with cold:
                    delete_btn = st.form_submit_button("Delete Event")

            if save_btn:
                db.update_service_event_status(
                    event_id=e["id"],
                    status=status,
                    followup_required=followup_required,
                    followup_notes=followup_notes,
                )
                st.success("Event updated.")
                st.rerun()

            if delete_btn:
                db.delete_service_event(e["id"])
                st.success("Event deleted.")
                st.rerun()

            if st.button("Send Reminder (mark only)", key=f"rem_{e['id']}"):
                db.touch_service_event_reminder(e["id"])
                st.info("Reminder timestamp updated (you can hook email/SMS here).")
