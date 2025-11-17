
from io import BytesIO
from typing import Dict, Any, List

import pandas as pd
import streamlit as st

import db


def show(user: Dict[str, Any]) -> None:
    st.title("📈 Admin Reports")

    st.subheader("Service Fulfilment Overview")

    current_year = pd.Timestamp.today().year
    year = st.selectbox(
        "Year",
        options=list(range(current_year - 2, current_year + 1)),
        index=2,
    )

    fulfil = db.get_portfolio_fulfilment(year)
    if not fulfil:
        st.info("No fulfilment data available.")
        return

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
            for r in fulfil
        ]
    )

    def status_color(s: str) -> str:
        if s == "On Track":
            return "#d4f4dd"
        if s == "In Progress":
            return "#fff4ce"
        if s == "Not Started":
            return "#fddede"
        return "#ffffff"

    def highlight_row(row):
        c = status_color(row["Status"])
        return [f"background-color: {c}"] * len(row)

    st.dataframe(df.style.apply(highlight_row, axis=1), use_container_width=True)

    # Excel download
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Portfolio Fulfilment")
    st.download_button(
        "⬇️ Download Portfolio Fulfilment (Excel)",
        data=buf.getvalue(),
        file_name=f"portfolio_fulfilment_{year}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.markdown("#### Pending Visits by Property")
    chart_df = df.set_index("Property")[["Pending Visits (YTD)"]]
    st.bar_chart(chart_df)
