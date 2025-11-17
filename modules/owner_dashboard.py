
from typing import Dict, Any

import pandas as pd
import streamlit as st

import db
from utils import gemini_chat


def show(user: Dict[str, Any]) -> None:
    st.title("🏠 My Property Dashboard")

    property_id = user.get("property_id")
    if not property_id:
        st.error("Your user is not linked to any property. Please contact admin.")
        return

    prop = db.get_property_by_id(property_id)
    if not prop:
        st.error("Property not found.")
        return

    st.markdown(f"### {prop['name']}")
    st.caption(f"{prop.get('address') or ''}, {prop.get('city') or ''}, {prop.get('state') or ''} {prop.get('zip') or ''}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Annual Quote", f"${prop.get('annual_quote', 0):,.0f}")
    col2.metric("Annual Credited", f"${prop.get('annual_credited', 0):,.0f}")
    col3.metric("Annual Cost", f"${prop.get('annual_cost', 0):,.0f}")

    st.markdown("### Service Fulfilment")

    current_year = pd.Timestamp.today().year
    fulfil = db.get_service_fulfilment_for_property(property_id, current_year)
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

    st.markdown("### Upcoming Events")

    events = db.get_events_for_property(property_id)
    if events:
        df_e = pd.DataFrame(
            [
                {
                    "Date": e["scheduled_date"],
                    "Time": e.get("scheduled_time") or "",
                    "Service": e["service_category"],
                    "Status": e["status"],
                }
                for e in events
            ]
        )
        st.dataframe(df_e, use_container_width=True)
    else:
        st.caption("No events scheduled yet for this property.")

    st.markdown("---")

    with st.expander("🤖 Ask AI about my property (Gemini)", expanded=False):
        q = st.text_area(
            "Ask a question about your property's landscaping, services, or schedule.",
            placeholder="Example: Are we on track with mowing and weed control for my property?",
        )
        if st.button("Ask Gemini (Owner)"):
            if not q.strip():
                st.warning("Please enter a question.")
            else:
                ctx = (
                    f"Property: {prop['name']}, City: {prop.get('city')}, "
                    f"Annual Quote: {prop.get('annual_quote',0):.2f}, "
                    f"Annual Credited: {prop.get('annual_credited',0):.2f}."
                )
                with st.spinner("Asking Gemini..."):
                    answer = gemini_chat.get_gemini_answer(q.strip(), context=ctx)
                st.markdown("**Gemini response:**")
                st.write(answer)
