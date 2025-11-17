
from pathlib import Path
from typing import Dict, Any, List

import pandas as pd
import streamlit as st

import db


def show(user: Dict[str, Any]) -> None:
    st.title("🎫 Tickets – Owner Communication")

    tickets = db.get_all_tickets()
    if not tickets:
        st.info("No tickets yet.")
        return

    df = pd.DataFrame(
        [
            {
                "ID": t["id"],
                "Property": t["property_name"],
                "Owner": t.get("owner_name") or "",
                "Subject": t["subject"],
                "Status": t["status"],
                "Priority": t["priority"],
                "Created At": t["created_at"],
                "Updated At": t["updated_at"],
            }
            for t in tickets
        ]
    )
    st.dataframe(df, use_container_width=True)

    st.markdown("---")
    st.markdown("### Manage Individual Tickets")

    upload_root = Path("uploads")
    upload_root.mkdir(exist_ok=True)

    for t in tickets:
        with st.expander(f"[#{t['id']}] {t['subject']} — {t['property_name']}", expanded=False):
            st.write(f"**Property:** {t['property_name']}")
            st.write(f"**Owner:** {t.get('owner_name') or '(Unknown owner)'}")
            st.write(f"**Status:** {t['status']}")
            st.write(f"**Priority:** {t['priority']}")
            st.write("**Description:**")
            st.write(t["description"])

            with st.form(f"ticket_admin_form_{t['id']}"):
                col1, col2 = st.columns(2)
                with col1:
                    new_status = st.selectbox(
                        "Status",
                        ["Open", "In Progress", "Closed"],
                        index=["Open", "In Progress", "Closed"].index(t["status"])
                        if t["status"] in ["Open", "In Progress", "Closed"]
                        else 0,
                    )
                with col2:
                    new_priority = st.selectbox(
                        "Priority",
                        ["Low", "Medium", "High"],
                        index=["Low", "Medium", "High"].index(t["priority"])
                        if t["priority"] in ["Low", "Medium", "High"]
                        else 1,
                    )
                new_description = st.text_area(
                    "Description / latest update",
                    value=t["description"],
                )
                save_ticket = st.form_submit_button("Save Ticket Changes")

            if save_ticket:
                db.update_ticket_status(
                    ticket_id=t["id"],
                    status=new_status,
                    priority=new_priority,
                    description=new_description,
                )
                st.success("Ticket updated.")
                st.rerun()

            # Attachments
            st.markdown("#### Attachments")
            attachments = db.get_attachments_for_ticket(t["id"])
            if attachments:
                for a in attachments:
                    st.write(
                        f"- {a['filename']} "
                        f"({a.get('mime_type') or ''}, {a.get('size_bytes') or 0} bytes)"
                    )
            else:
                st.caption("No attachments yet.")

            uploaded_files = st.file_uploader(
                f"Upload attachment(s) for ticket #{t['id']}",
                type=["png", "jpg", "jpeg", "pdf"],
                accept_multiple_files=True,
                key=f"ticket_upload_{t['id']}",
            )
            if uploaded_files:
                for uf in uploaded_files:
                    if uf.size > 5 * 1024 * 1024:
                        st.error(f"{uf.name}: file is larger than 5 MB, skipping.")
                        continue
                    ticket_dir = upload_root / f"ticket_{t['id']}"
                    ticket_dir.mkdir(exist_ok=True)
                    stored_path = ticket_dir / uf.name
                    with open(stored_path, "wb") as f:
                        f.write(uf.getbuffer())
                    db.add_ticket_attachment(
                        ticket_id=t["id"],
                        filename=uf.name,
                        stored_path=str(stored_path),
                        mime_type=getattr(uf, "type", "") or "",
                        size_bytes=uf.size,
                    )
                st.success("Attachment(s) uploaded.")
                st.rerun()
