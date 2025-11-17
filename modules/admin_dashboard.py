
import datetime
from typing import Dict, Any, List

import pandas as pd
import streamlit as st

import db
from utils import gemini_chat


def _status_color(status: str) -> str:
    if status == "On Track":
        return "#d4f4dd"  # green
    if status == "In Progress":
        return "#fff4ce"  # yellow
    if status == "Not Started":
        return "#fddede"  # red
    return "#ffffff"


def show(user: Dict[str, Any]) -> None:
    st.title("🏡 Admin Dashboard")

    props = db.get_all_properties()
    total_props = len(props)
    total_quote = sum(p.get("annual_quote") or 0.0 for p in props)
    total_credited = sum(p.get("annual_credited") or 0.0 for p in props)
    total_cost = sum(p.get("annual_cost") or 0.0 for p in props)
    total_margin = total_credited - total_cost
    margin_pct = (total_margin / total_credited * 100.0) if total_credited else 0.0

    # Top-level metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Properties", total_props)
    col2.metric("Annual Quoted Revenue", f"${total_quote:,.0f}")
    col3.metric("Annual Credited Revenue", f"${total_credited:,.0f}")
    col4.metric("Portfolio Margin", f"${total_margin:,.0f}", f"{margin_pct:,.1f}%")

    st.markdown("---")

    # Module health overview
    st.subheader("Module Health Overview")

    open_tickets = db.count_open_tickets()
    today_str = datetime.date.today().isoformat()
    overdue_events = db.count_overdue_events(today_str)
    active_persons = db.count_active_service_persons()
    price_entries = db.count_price_master_entries()

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.caption("Tickets")
        status = "OK" if open_tickets == 0 else "Attention"
        st.metric("Open Tickets", open_tickets, status)

    with c2:
        st.caption("Scheduled Events")
        status_e = "OK" if overdue_events == 0 else "Overdue"
        st.metric("Overdue Events", overdue_events, status_e)

    with c3:
        st.caption("Service Personnel")
        status_p = "OK" if active_persons > 0 else "No active staff"
        st.metric("Active Staff", active_persons, status_p)

    with c4:
        st.caption("Price Master")
        status_pm = "OK" if price_entries > 0 else "Empty"
        st.metric("Rate Entries", price_entries, status_pm)

    st.markdown("---")

    # Service fulfilment overview
    st.subheader("Service Fulfilment Overview")

    current_year = datetime.date.today().year
    year = st.selectbox("Year", options=list(range(current_year - 2, current_year + 1)), index=2)

    fulfilment: List[Dict[str, Any]] = db.get_portfolio_fulfilment(year)
    if not fulfilment:
        st.info("No fulfilment data available yet.")
    else:
        df = pd.DataFrame(
            [
                {
                    "Property": r["property_name"],
                    "Planned Visits (Year)": r["planned"],
                    "Completed Visits (YTD)": r["completed"],
                    "Pending Visits (YTD)": r["pending"],
                    "Completion %": round(r["completion_pct"], 1) if r["completion_pct"] is not None else None,
                    "Status": r["status"],
                }
                for r in fulfilment
            ]
        )

        def highlight_row(row):
            color = _status_color(row["Status"])
            return ["background-color: %s" % color] * len(row)

        st.dataframe(
            df.style.apply(highlight_row, axis=1),
            use_container_width=True,
        )

        # Bar chart: Planned vs Completed
        st.markdown("#### Planned vs Completed Visits by Property")
        chart_df = df.set_index("Property")[["Planned Visits (Year)", "Completed Visits (YTD)"]]
        st.bar_chart(chart_df)

    st.markdown("---")

    # AI Chat section
    with st.expander("🤖 Ask AI about your portfolio (Gemini)", expanded=False):
        q = st.text_area(
            "Ask a question about your landscaping portfolio, costs, or fulfilment.",
            placeholder="Example: Which properties have the lowest service completion and may need attention?",
        )
        if st.button("Ask Gemini"):
            if not q.strip():
                st.warning("Please enter a question.")
            else:
                with st.spinner("Asking Gemini..."):
                    # Provide some context like number of properties / margin
                    ctx = (
                        f"Total properties: {total_props}, "
                        f"Total quoted: {total_quote:.2f}, "
                        f"Total credited: {total_credited:.2f}, "
                        f"Total cost: {total_cost:.2f}, "
                        f"Margin pct: {margin_pct:.1f}%."
                    )
                    answer = gemini_chat.get_gemini_answer(q.strip(), context=ctx)
                st.markdown("**Gemini response:**")
                st.write(answer)
