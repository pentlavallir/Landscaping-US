
from typing import Dict, Any

import pandas as pd
import streamlit as st

import db


def show(user: Dict[str, Any]) -> None:
    st.title("👷 Service Personnel")

    persons = db.get_all_service_persons()
    if persons:
        df = pd.DataFrame(persons)
        df_view = df[["id", "full_name", "email", "phone", "role", "is_active", "notes"]]
        st.dataframe(df_view, use_container_width=True)
    else:
        st.info("No service personnel added yet.")

    with st.expander("➕ Add / Edit Service Person", expanded=False):
        id_to_person = {p["id"]: p for p in persons}
        options = ["(New person)"] + [f"{p['id']} - {p['full_name']}" for p in persons]
        selection = st.selectbox("Select person to edit or choose new", options)

        editing = None
        if selection != "(New person)":
            pid = int(selection.split(" - ")[0])
            editing = id_to_person[pid]

        with st.form("person_form"):
            full_name = st.text_input("Full Name", value=editing["full_name"] if editing else "")
            email = st.text_input("Email", value=editing.get("email", "") if editing else "")
            phone = st.text_input("Phone", value=editing.get("phone", "") if editing else "")
            role = st.text_input("Role", value=editing.get("role", "") if editing else "")
            notes = st.text_area("Notes", value=editing.get("notes", "") if editing else "")
            is_active = st.checkbox(
                "Active",
                value=(editing["is_active"] == 1) if editing else True,
            )

            col1, col2 = st.columns(2)
            with col1:
                save_btn = st.form_submit_button("Save")
            with col2:
                delete_btn = st.form_submit_button("Delete")

        if save_btn:
            if not full_name.strip():
                st.error("Full name is required.")
            else:
                if editing:
                    db.update_service_person(
                        editing["id"],
                        full_name=full_name.strip(),
                        email=email.strip(),
                        phone=phone.strip(),
                        role=role.strip(),
                        notes=notes.strip(),
                        is_active=is_active,
                    )
                    st.success("Person updated.")
                else:
                    db.add_service_person(
                        full_name=full_name.strip(),
                        email=email.strip(),
                        phone=phone.strip(),
                        role=role.strip(),
                        notes=notes.strip(),
                    )
                    st.success("Person added.")
                st.rerun()

        if delete_btn and editing:
            # Soft delete: mark as inactive rather than remove row
            db.update_service_person(
                editing["id"],
                full_name=editing["full_name"],
                email=editing.get("email", ""),
                phone=editing.get("phone", ""),
                role=editing.get("role", ""),
                notes=editing.get("notes", ""),
                is_active=False,
            )
            st.success("Person marked as inactive.")
            st.rerun()
