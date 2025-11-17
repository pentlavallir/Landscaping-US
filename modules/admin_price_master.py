
from typing import Dict, Any

import pandas as pd
import streamlit as st

import db


def show(user: Dict[str, Any]) -> None:
    st.title("💲 Price Master")

    entries = db.get_price_master_all()
    if entries:
        df = pd.DataFrame(entries)
        df_view = df[["id", "category", "frequency", "default_cost", "notes"]]
        st.dataframe(df_view, use_container_width=True)
    else:
        st.info("No price master entries yet.")

    with st.expander("✏️ Add / Edit Entry", expanded=False):
        entry_ids = [e["id"] for e in entries]
        id_to_entry = {e["id"]: e for e in entries}
        options = ["(New entry)"] + [f"{e['id']} - {e['category']} ({e['frequency']})" for e in entries]
        selection = st.selectbox("Select an entry to edit or choose new", options)

        editing = None
        if selection != "(New entry)":
            eid = int(selection.split(" - ")[0])
            editing = id_to_entry[eid]

        with st.form("price_form"):
            category = st.text_input("Category", value=editing["category"] if editing else "")
            frequency = st.text_input("Frequency", value=editing["frequency"] if editing else "")
            default_cost = st.number_input(
                "Default Cost per Visit",
                min_value=0.0,
                value=float(editing["default_cost"]) if editing else 0.0,
                step=10.0,
            )
            notes = st.text_area("Notes", value=editing.get("notes", "") if editing else "")

            col1, col2 = st.columns(2)
            with col1:
                save_btn = st.form_submit_button("Save")
            with col2:
                delete_btn = st.form_submit_button("Delete")

        if save_btn:
            if not category.strip():
                st.error("Category is required.")
            else:
                if editing:
                    db.update_price_master_entry(
                        editing["id"],
                        category=category.strip(),
                        frequency=frequency.strip(),
                        default_cost=default_cost,
                        notes=notes.strip(),
                    )
                    st.success("Entry updated.")
                else:
                    db.add_price_master_entry(
                        category=category.strip(),
                        frequency=frequency.strip(),
                        default_cost=default_cost,
                        notes=notes.strip(),
                    )
                    st.success("Entry added.")
                st.rerun()

        if delete_btn and editing:
            db.delete_price_master_entry(editing["id"])
            st.success("Entry deleted.")
            st.rerun()
