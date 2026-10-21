r"""Rohlik Decision Hub — admin-only, read-only multipage dashboard.

Run with:
    .\.venv\Scripts\python.exe -m streamlit run app/main.py

The shell authenticates the configured local admin before building navigation.
"""

from __future__ import annotations

import streamlit as st

from app.auth import render_logout_control, require_admin
from app.common import apply_app_styles, render_sidebar_context
from app.navigation import build_navigation
from app.services.reporting import ReportingError, ReportingService, WarehouseInfo


st.set_page_config(
    page_title="Rohlik Decision Hub",
    page_icon=":material/space_dashboard:",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    """Render the shared shell and execute the selected registered page."""

    apply_app_styles()
    user = require_admin()
    service = ReportingService()
    try:
        warehouse = service.warehouse_info()
    except ReportingError:
        warehouse = WarehouseInfo(service.database, False, ())
    render_sidebar_context(user.username, warehouse)
    render_logout_control()
    selected_page = st.navigation(
        build_navigation(), position="sidebar", expanded=True
    )
    selected_page.run()


if __name__ == "__main__":
    main()
