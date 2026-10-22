"""Modern Commerce Analytics design system tokens and CSS styles."""

from __future__ import annotations

APP_CSS = """
<style>
/* --- Design System CSS Variables --- */
:root {
    --rdh-bg: #F6F8FC;
    --rdh-surface: #FFFFFF;
    --rdh-surface-secondary: #F1F5F9;
    --rdh-surface-subtle: #F8FAFC;
    --rdh-heading: #172B4D;
    --rdh-primary: #2563EB;
    --rdh-primary-hover: #1D4ED8;
    --rdh-teal: #0F766E;
    --rdh-ink: #0F172A;
    --rdh-secondary-text: #475569;
    --rdh-muted: #64748B;
    --rdh-border: #E2E8F0;
    --rdh-border-subtle: #EDF2F7;
    
    /* Semantic Status Tokens */
    --rdh-success-text: #166534;
    --rdh-success-bg: #F0FDF4;
    --rdh-success-border: #BBF7D0;
    
    --rdh-warning-text: #92400E;
    --rdh-warning-bg: #FFFBEB;
    --rdh-warning-border: #FDE68A;
    
    --rdh-danger-text: #B91C1C;
    --rdh-danger-bg: #FEF2F2;
    --rdh-danger-border: #FECACA;
    
    --rdh-info-text: #1D4ED8;
    --rdh-info-bg: #EFF6FF;
    --rdh-info-border: #BFDBFE;
    
    --rdh-neutral-text: #475569;
    --rdh-neutral-bg: #F1F5F9;
    --rdh-neutral-border: #CBD5E1;
    
    /* Typography & Radius */
    --rdh-font: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    --rdh-radius-card: 12px;
    --rdh-radius-badge: 9999px;
    --rdh-radius-control: 8px;
    --rdh-shadow-sm: 0 1px 3px rgba(15, 23, 42, 0.05);
    --rdh-shadow-card: 0 3px 18px rgba(15, 23, 42, 0.04);
}

/* --- Global Container & Typography --- */
html, body, [class*="css"] {
    font-family: var(--rdh-font);
    color: var(--rdh-ink);
}

.stApp {
    background-color: var(--rdh-bg);
}

.block-container {
    max-width: 1360px !important;
    padding-top: 2rem !important;
    padding-bottom: 3.5rem !important;
    padding-left: 2rem !important;
    padding-right: 2rem !important;
}

/* Headings */
h1 {
    color: var(--rdh-heading) !important;
    font-size: 2rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.025em !important;
    line-height: 1.2 !important;
    margin-bottom: 0.25rem !important;
}

h2 {
    color: var(--rdh-heading) !important;
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
    margin-top: 1.5rem !important;
    margin-bottom: 0.75rem !important;
}

h3 {
    color: var(--rdh-heading) !important;
    font-size: 1.15rem !important;
    font-weight: 600 !important;
    letter-spacing: -0.015em !important;
    margin-top: 1.25rem !important;
    margin-bottom: 0.5rem !important;
}

/* --- Sidebar Styling --- */
[data-testid="stSidebar"] {
    background-color: #FFFFFF !important;
    border-right: 1px solid var(--rdh-border) !important;
    box-shadow: 1px 0 3px rgba(15, 23, 42, 0.02);
}

[data-testid="stSidebarNav"] {
    padding-top: 0.5rem !important;
}

[data-testid="stSidebarNav"] ul {
    gap: 2px;
}

[data-testid="stSidebarNav"] li a {
    border-radius: var(--rdh-radius-control) !important;
    margin: 1px 8px !important;
    padding: 0.45rem 0.75rem !important;
    transition: all 0.15s ease-in-out;
    color: var(--rdh-secondary-text) !important;
}

[data-testid="stSidebarNav"] li a:hover {
    background-color: var(--rdh-surface-secondary) !important;
    color: var(--rdh-heading) !important;
}

[data-testid="stSidebarNav"] li a[aria-current="page"] {
    background-color: #EFF6FF !important;
    color: var(--rdh-primary) !important;
    font-weight: 600 !important;
    border-left: 3px solid var(--rdh-primary) !important;
}

/* Sidebar Brand Block */
.rdh-brand {
    padding: 0.5rem 0.25rem 0.75rem;
    border-bottom: 1px solid var(--rdh-border);
    margin-bottom: 0.75rem;
}

.rdh-brand__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.25rem;
}

.rdh-brand__name {
    color: var(--rdh-heading);
    font-size: 1.05rem;
    font-weight: 750;
    letter-spacing: -0.02em;
    display: flex;
    align-items: center;
    gap: 0.4rem;
}

.rdh-brand__meta {
    color: var(--rdh-muted);
    font-size: 0.78rem;
    line-height: 1.4;
    margin-top: 0.2rem;
}

.rdh-mode {
    align-items: center;
    background: #EFF6FF;
    border: 1px solid #BFDBFE;
    border-radius: var(--rdh-radius-badge);
    color: var(--rdh-primary);
    display: inline-flex;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    padding: 0.2rem 0.55rem;
    text-transform: uppercase;
}

.rdh-mode::before {
    background: var(--rdh-teal);
    border-radius: 50%;
    content: "";
    height: 0.38rem;
    margin-right: 0.38rem;
    width: 0.38rem;
}

.rdh-sidebar-card {
    background: var(--rdh-surface-subtle);
    border: 1px solid var(--rdh-border);
    border-radius: var(--rdh-radius-control);
    padding: 0.75rem;
    margin: 0.5rem 0;
}

.rdh-sidebar-card__title {
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--rdh-muted);
    margin-bottom: 0.4rem;
}

.rdh-sidebar-card__item {
    font-size: 0.8rem;
    color: var(--rdh-secondary-text);
    margin: 0.2rem 0;
    display: flex;
    align-items: center;
    gap: 0.35rem;
}

/* --- Page Heading Banner --- */
.rdh-heading-box {
    background: var(--rdh-surface);
    border: 1px solid var(--rdh-border);
    border-radius: var(--rdh-radius-card);
    padding: 1.25rem 1.5rem;
    margin-bottom: 1.25rem;
    box-shadow: var(--rdh-shadow-card);
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.rdh-heading-box__top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    flex-wrap: wrap;
    gap: 0.75rem;
}

.rdh-heading-box__title {
    color: var(--rdh-heading);
    font-size: 1.75rem;
    font-weight: 700;
    letter-spacing: -0.025em;
    margin: 0;
    line-height: 1.2;
}

.rdh-heading-box__description {
    color: var(--rdh-secondary-text);
    font-size: 0.92rem;
    line-height: 1.55;
    margin: 0;
    max-width: 85ch;
}

.rdh-heading-box__meta {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
}

/* Preserving legacy heading copy wrapper for existing views */
.rdh-heading-copy {
    border-bottom: 1px solid var(--rdh-border);
    padding-bottom: 1rem;
    margin-bottom: 1.25rem;
}

.rdh-heading-copy p {
    color: var(--rdh-secondary-text);
    font-size: 0.95rem;
    line-height: 1.6;
    margin: 0.4rem 0 0;
    max-width: 75ch;
}

/* --- Status Badges & Readiness Banner --- */
.rdh-status {
    border-radius: var(--rdh-radius-badge);
    display: inline-flex;
    align-items: center;
    flex: 0 0 auto;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    line-height: 1;
    padding: 0.3rem 0.65rem;
    text-transform: uppercase;
    border: 1px solid currentColor;
}

.rdh-status--success {
    color: var(--rdh-success-text);
    background-color: var(--rdh-success-bg);
    border-color: var(--rdh-success-border);
}

.rdh-status--warning {
    color: var(--rdh-warning-text);
    background-color: var(--rdh-warning-bg);
    border-color: var(--rdh-warning-border);
}

.rdh-status--danger {
    color: var(--rdh-danger-text);
    background-color: var(--rdh-danger-bg);
    border-color: var(--rdh-danger-border);
}

.rdh-status--model, .rdh-status--info {
    color: var(--rdh-info-text);
    background-color: var(--rdh-info-bg);
    border-color: var(--rdh-info-border);
}

.rdh-status--neutral {
    color: var(--rdh-neutral-text);
    background-color: var(--rdh-neutral-bg);
    border-color: var(--rdh-neutral-border);
}

.rdh-readiness {
    align-items: flex-start;
    background: var(--rdh-surface);
    border: 1px solid var(--rdh-border);
    border-left: 4px solid var(--rdh-primary);
    border-radius: var(--rdh-radius-control);
    box-shadow: var(--rdh-shadow-sm);
    display: flex;
    gap: 0.85rem;
    margin: 1rem 0 1.5rem;
    padding: 0.85rem 1.15rem;
}

.rdh-readiness__copy {
    color: var(--rdh-secondary-text);
    font-size: 0.88rem;
    line-height: 1.5;
}

/* --- Modern KPI Cards --- */
div[data-testid="stMetric"] {
    background: var(--rdh-surface) !important;
    border: 1px solid var(--rdh-border) !important;
    border-radius: var(--rdh-radius-card) !important;
    padding: 1.1rem 1.25rem !important;
    box-shadow: var(--rdh-shadow-card) !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}

div[data-testid="stMetric"]:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 20px rgba(15, 23, 42, 0.06) !important;
}

div[data-testid="stMetric"] label[data-testid="stMetricLabel"] {
    color: var(--rdh-secondary-text) !important;
    font-size: 0.84rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.03em !important;
}

div[data-testid="stMetricValue"] {
    color: var(--rdh-heading) !important;
    font-size: 1.95rem !important;
    font-weight: 700 !important;
    font-variant-numeric: tabular-nums !important;
    letter-spacing: -0.03em !important;
}

/* Custom Rich KPI Card HTML block */
.rdh-kpi-card {
    background: var(--rdh-surface);
    border: 1px solid var(--rdh-border);
    border-radius: var(--rdh-radius-card);
    padding: 1.15rem 1.25rem;
    box-shadow: var(--rdh-shadow-card);
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    height: 100%;
}

.rdh-kpi-card__header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
}

.rdh-kpi-card__label {
    color: var(--rdh-secondary-text);
    font-size: 0.82rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
}

.rdh-kpi-card__value {
    color: var(--rdh-heading);
    font-size: 1.9rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.03em;
    line-height: 1.15;
    margin: 0.2rem 0;
}

.rdh-kpi-card__meta {
    color: var(--rdh-muted);
    font-size: 0.78rem;
    display: flex;
    align-items: center;
    gap: 0.35rem;
    margin-top: 0.4rem;
}

/* --- Filter Container --- */
.rdh-filter-panel {
    background: var(--rdh-surface);
    border: 1px solid var(--rdh-border);
    border-radius: var(--rdh-radius-card);
    padding: 1rem 1.25rem 0.5rem;
    margin-bottom: 1.25rem;
    box-shadow: var(--rdh-shadow-card);
}

.rdh-filter-panel__title {
    font-size: 0.8rem;
    font-weight: 700;
    color: var(--rdh-heading);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.4rem;
}

/* --- Chart Card Container --- */
.rdh-chart-card {
    background: var(--rdh-surface);
    border: 1px solid var(--rdh-border);
    border-radius: var(--rdh-radius-card);
    padding: 1.25rem 1.5rem;
    margin-bottom: 1.5rem;
    box-shadow: var(--rdh-shadow-card);
}

.rdh-chart-card__header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 1rem;
    flex-wrap: wrap;
    gap: 0.5rem;
}

.rdh-chart-card__title {
    color: var(--rdh-heading);
    font-size: 1.15rem;
    font-weight: 700;
    letter-spacing: -0.015em;
    margin: 0;
}

.rdh-chart-card__subtitle {
    color: var(--rdh-secondary-text);
    font-size: 0.82rem;
    margin-top: 0.2rem;
}

.rdh-chart-card__legend {
    display: flex;
    align-items: center;
    gap: 1rem;
    font-size: 0.78rem;
    color: var(--rdh-secondary-text);
}

.rdh-legend-dot {
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    margin-right: 0.3rem;
}

/* --- Model States Section --- */
.rdh-model-section {
    background: var(--rdh-surface);
    border: 1px solid var(--rdh-border);
    border-radius: var(--rdh-radius-card);
    padding: 1.25rem 1.5rem;
    margin-bottom: 1.5rem;
    box-shadow: var(--rdh-shadow-card);
}

.rdh-model {
    border-top: 1px solid var(--rdh-border);
    display: grid;
    gap: 1rem;
    grid-template-columns: minmax(13rem, 0.8fr) minmax(16rem, 1.4fr) auto;
    padding: 0.9rem 0;
    align-items: center;
}

.rdh-model:first-of-type {
    border-top: none;
}

.rdh-model__title {
    color: var(--rdh-heading);
    font-weight: 650;
    font-size: 0.92rem;
}

.rdh-model__copy {
    color: var(--rdh-secondary-text);
    font-size: 0.85rem;
    line-height: 1.5;
}

/* --- Empty and Alert States --- */
.rdh-empty {
    background: var(--rdh-surface);
    border: 1px dashed var(--rdh-border);
    border-radius: var(--rdh-radius-card);
    padding: 2.5rem 2rem;
    text-align: center;
    max-width: 650px;
    margin: 1.5rem auto;
}

.rdh-empty h2, .rdh-empty h3 {
    color: var(--rdh-heading);
    font-size: 1.3rem !important;
    margin-bottom: 0.5rem !important;
}

.rdh-empty p {
    color: var(--rdh-secondary-text);
    font-size: 0.92rem;
    line-height: 1.6;
    margin: 0.5rem 0 1rem;
}

/* --- Dataframe & Tables --- */
div[data-testid="stDataFrame"] {
    background: var(--rdh-surface) !important;
    border: 1px solid var(--rdh-border) !important;
    border-radius: var(--rdh-radius-control) !important;
    box-shadow: var(--rdh-shadow-sm) !important;
    overflow: hidden;
}

/* Interactive Controls Focus States */
div.stButton > button:focus-visible,
input:focus-visible,
[role="combobox"]:focus-visible,
[data-baseweb="select"]:focus-within {
    outline: 2px solid var(--rdh-primary) !important;
    outline-offset: 2px !important;
}

div.stButton > button {
    border-radius: var(--rdh-radius-control) !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    transition: all 0.15s ease-in-out !important;
}

div.stButton > button[kind="primary"] {
    background-color: var(--rdh-primary) !important;
    color: #FFFFFF !important;
    border: none !important;
}

div.stButton > button[kind="primary"]:hover {
    background-color: var(--rdh-primary-hover) !important;
}

/* Text Selection & Scrollbars */
::selection {
    background: #BFDBFE;
    color: #1E3A8A;
}

* {
    scrollbar-color: #CBD5E1 #F1F5F9;
    scrollbar-width: thin;
}

/* Media Queries for Responsive Design */
@media (max-width: 900px) {
    .block-container {
        padding-top: 1.25rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
    .rdh-model {
        grid-template-columns: 1fr;
        gap: 0.5rem;
    }
    .rdh-readiness {
        flex-direction: column;
    }
    .rdh-heading-box__top {
        flex-direction: column;
    }
}
</style>
"""
