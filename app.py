
import datetime

import streamlit as st

import db
from modules import (
    admin_dashboard,
    admin_properties,
    admin_price_master,
    admin_personnel,
    admin_events,
    admin_reports,
    admin_tickets,
    owner_dashboard,
    owner_tickets,
    admin_quote_builder,
)


def main():
    st.set_page_config(
        page_title="Landscaping & Mowing Manager",
        page_icon="🌳",
        layout="wide",
    )

    db.init_db()

    if "user" not in st.session_state:
        st.session_state.user = None

    user = st.session_state.user

    if user is None:
        login_page()
    else:
        if user["role"] == "admin":
            admin_app(user)
        else:
            owner_app(user)


def login_page():
    st.title("🌳 Landscaping & Mowing Portal")
    st.subheader("Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        if not username or not password:
            st.error("Please enter username and password.")
            return

        user = db.get_user_by_username(username.strip())
        if not user or user["password"] != password:
            st.error("Invalid credentials.")
            return

        st.session_state.user = user
        st.success(f"Welcome, {user.get('full_name') or user['username']}!")
        st.rerun()


def admin_app(user):
    st.sidebar.title("Admin Navigation")
    choice = st.sidebar.radio(
        "Go to",
        [
            "Dashboard",
            "Quote Builder",
            "Manage Properties & Services",
            "Price Master",
            "Service Personnel",
            "Event Scheduler",
            "Reports",
            "Tickets",
        ],
    )

    st.sidebar.markdown("---")
    st.sidebar.write(f"Logged in as **{user.get('full_name') or user['username']}** (Admin)")
    if st.sidebar.button("Logout"):
        st.session_state.user = None
        st.rerun()

    if choice == "Dashboard":
        admin_dashboard.show(user)
    elif choice == "Quote Builder":
        admin_quote_builder.show(user)
    elif choice == "Manage Properties & Services":
        admin_properties.show(user)
    elif choice == "Price Master":
        admin_price_master.show(user)
    elif choice == "Service Personnel":
        admin_personnel.show(user)
    elif choice == "Event Scheduler":
        admin_events.show(user)
    elif choice == "Reports":
        admin_reports.show(user)
    elif choice == "Tickets":
        admin_tickets.show(user)


def owner_app(user):
    st.sidebar.title("Owner Navigation")
    choice = st.sidebar.radio(
        "Go to",
        [
            "My Dashboard",
            "My Tickets",
        ],
    )

    st.sidebar.markdown("---")
    st.sidebar.write(f"Logged in as **{user.get('full_name') or user['username']}** (Owner)")
    if st.sidebar.button("Logout"):
        st.session_state.user = None
        st.rerun()

    if choice == "My Dashboard":
        owner_dashboard.show(user)
    elif choice == "My Tickets":
        owner_tickets.show(user)


if __name__ == "__main__":
    main()
