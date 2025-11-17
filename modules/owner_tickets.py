
from pathlib import Path
from typing import Dict, Any

import pandas as pd
import streamlit as st

import db


def show(user: Dict[str, Any]) -> None:
    st.title("🎫 My Tickets")

    owner_id = user.get("id")
    property_id = user.get("property_id")
    if not owner_id or not property_id:
        st.error("Your user is not correctly linked to a property. Please contact admin.")
        return

    tickets = db.get_tickets_for_owner(owner_id)
    if tickets:
        df = pd.DataFrame(
            [
                {
                    "ID": t["id"],
                    "Property": t["property_name"],
                    "Subject": t["subject"],
                    "Status": t["status"],
                    "Priority": t["priority"],
                    "Created At": t["created_at"],
                }
                for t in tickets
            ]
        )
        st.dataframe(df, use_container_width=True)
    else:
        st.info("You have not created any tickets yet.")

    upload_root = Path("uploads")
    upload_root.mkdir(exist_ok=True)

    with st.expander("➕ New Ticket", expanded=False):
        with st.form("new_ticket_form"):
            subject = st.text_input("Subject")
            description = st.text_area("Description")
            priority = st.selectbox("Priority", ["Low", "Medium", "High"], index=1)
            submit = st.form_submit_button("Submit Ticket")

        if submit:
            if not subject.strip() or not description.strip():
                st.error("Subject and description are required.")
            else:
                tid = db.add_ticket(
                    property_id=property_id,
                    owner_id=owner_id,
                    created_by_user_id=owner_id,
                    subject=subject.strip(),
                    description=description.strip(),
                    priority=priority,
                )
                st.success(f"Ticket #{tid} created.")
                st.rerun()

    # Allow viewing each ticket with attachments
    if tickets:
        st.markdown("---")
        st.markdown("### Ticket Details")
        for t in tickets:
            with st.expander(f"[#{t['id']}] {t['subject']}", expanded=False):
                st.write(f"**Status:** {t['status']}")
                st.write(f"**Priority:** {t['priority']}")
                st.write("**Description:**")
                st.write(t["description"])

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
                    key=f"owner_ticket_upload_{t['id']}",
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
