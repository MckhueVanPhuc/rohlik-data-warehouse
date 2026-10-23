"""Reusable UI components for Rohlik Decision Hub modern commerce analytics."""

from __future__ import annotations

from html import escape
from typing import Sequence
import streamlit as st


def render_header(
    title: str,
    description: str,
    *,
    status_badge_html: str | None = None,
    as_of: str | None = "15/03/2024",
) -> None:
    """Render a modern SaaS analytics page header."""
    badge_content = ""
    if as_of:
        badge_content += (
            f'<span class="rdh-status rdh-status--neutral" title="Thời điểm chốt dữ liệu mô phỏng">'
            f'AS OF {escape(as_of)}</span>'
        )
    if status_badge_html:
        badge_content += f" {status_badge_html}"

    st.markdown(
        f"""
        <div class="rdh-heading-box">
          <div class="rdh-heading-box__top">
            <div>
              <h1 class="rdh-heading-box__title">{escape(title)}</h1>
              <p class="rdh-heading-box__description">{escape(description)}</p>
            </div>
            <div class="rdh-heading-box__meta">
              {badge_content}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpi(
    label: str,
    value: str,
    *,
    unit: str = "",
    subtitle: str | None = None,
    badge_text: str | None = None,
    badge_variant: str = "neutral",
) -> None:
    """Render a polished Modern Commerce Analytics KPI card."""
    unit_html = f' <span style="font-size: 0.95rem; font-weight: 500; color: var(--rdh-secondary-text);">{escape(unit)}</span>' if unit else ""
    badge_html = (
        f'<span class="rdh-status rdh-status--{escape(badge_variant)}">{escape(badge_text)}</span>'
        if badge_text else ""
    )
    sub_html = f'<div class="rdh-kpi-card__meta">{escape(subtitle)}</div>' if subtitle else ""

    st.markdown(
        f"""
        <div class="rdh-kpi-card">
          <div class="rdh-kpi-card__header">
            <span class="rdh-kpi-card__label">{escape(label)}</span>
            {badge_html}
          </div>
          <div class="rdh-kpi-card__value">
            {escape(value)}{unit_html}
          </div>
          {sub_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_chart_header(title: str, subtitle: str | None = None, *, right_badge: str | None = None) -> None:
    """Render a container header for analytical charts."""
    sub_html = f'<div class="rdh-chart-card__subtitle">{escape(subtitle)}</div>' if subtitle else ""
    badge_html = f'<div>{right_badge}</div>' if right_badge else ""
    st.markdown(
        f"""
        <div class="rdh-chart-card__header">
          <div>
            <h3 class="rdh-chart-card__title">{escape(title)}</h3>
            {sub_html}
          </div>
          {badge_html}
        </div>
        """,
        unsafe_allow_html=True,
    )
