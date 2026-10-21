"""Rohlik Decision Hub — Streamlit 2.0 backend services package.

Services act as adapters between the UI layer and the DE backend
(src/db, src/ingestion, src/config). They must NOT duplicate DE
logic — only wrap it for Streamlit consumption.
"""
