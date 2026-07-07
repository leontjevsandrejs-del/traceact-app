"""
TraceAct central engine router.

app.py boots the content database, applies corporate dashboard chrome,
renders the sidebar vault, and dispatches to the assessment wizard in
ui_layouts.py.
"""

import json
import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ── Dashboard settings (must be the first Streamlit call) ─────────────────────
st.set_page_config(
    page_title="TraceAct — EU AI Act Compliance Workspace",
    page_icon="🛡️",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ── Stripe post-payment activation gate ───────────────────────────────────────
def _payment_gate_open() -> bool:
    from utils.payment_return import handle_stripe_return_or_continue
    return handle_stripe_return_or_continue()


if not _payment_gate_open():
    st.stop()

def _restore_secure_session() -> None:
    from utils.secure_session import current_secure_session
    from utils.user_session import activate_workspace_user
    session = current_secure_session()
    if session:
        activate_workspace_user(session["user_id"], session["email"])


_restore_secure_session()

from utils.billing_ui import sync_credit_count
from utils.sidebar_ui import render_enterprise_sidebar
from ui_layouts import render_workspace_engine, render_legal_hub

sync_credit_count()


def initialize_content() -> None:
    """Read content.json safely into st.session_state.content on boot."""
    if "content" in st.session_state and st.session_state.content:
        return
    content_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "content.json"
    )
    try:
        with open(content_path, "r", encoding="utf-8") as f:
            st.session_state.content = json.load(f)
    except (OSError, json.JSONDecodeError) as err:
        st.session_state.content = {}
        st.error(
            "Content database `content.json` could not be loaded — the "
            f"interface will render without copy blocks. Detail: `{err}`"
        )


initialize_content()
_content = st.session_state.content

# ── Global corporate CSS (dark/light professional palette) ────────────────────
st.markdown("""
<style>
/* ── Base & typography ─────────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', 'Segoe UI', Arial, sans-serif;
    background-color: #F8FAFC;
    color: #1E293B;
}

/* ── Hide default Streamlit chrome ─────────────────────────────────────────── */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1200px; }

/* ── Top navigation (st.navigation position=top) ───────────────────────────── */
[data-testid="stNavigation"] {
    margin-bottom: 0.75rem;
}
[data-testid="stNavigation"] a {
    font-family: 'Inter', sans-serif;
    font-size: 0.825rem;
    font-weight: 500;
}

/* ── Sidebar (navigation) ──────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #0F172A;
    border-right: 1px solid #1E293B;
}
[data-testid="stSidebar"] * { color: #CBD5E1 !important; }
[data-testid="stSidebar"] .stSuccess { background: #064E3B; border: 1px solid #059669; border-radius: 6px; }
[data-testid="stSidebar"] .stError   { background: #7F1D1D; border: 1px solid #DC2626; border-radius: 6px; }
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
    display: flex;
    flex-direction: column;
    min-height: calc(100vh - 2rem);
}
.sidebar-account-card {
    background: #1E293B;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 1rem 1.1rem;
    margin-bottom: 1.25rem;
}
.sidebar-account-icon { font-size: 1.1rem; margin-bottom: 0.35rem; }
.sidebar-account-company {
    font-size: 1rem;
    font-weight: 700;
    color: #F8FAFC !important;
    line-height: 1.35;
    margin-bottom: 0.25rem;
}
.sidebar-account-email {
    font-size: 0.78rem;
    color: #94A3B8 !important;
    line-height: 1.45;
}
.sidebar-library-heading {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #93C5FD !important;
    margin-bottom: 0.65rem;
}
.sidebar-library-empty {
    font-size: 0.8rem;
    color: #94A3B8 !important;
    line-height: 1.55;
    padding: 0.65rem 0.1rem 1rem;
}
.sidebar-logout-spacer {
    flex: 1 1 auto;
    min-height: 1.5rem;
}
[data-testid="stSidebar"] [data-testid="stExpander"] {
    background: #1E293B;
    border: 1px solid #334155;
    border-radius: 8px;
    margin-bottom: 0.45rem;
}

/* ── Tab navigation bar ─────────────────────────────────────────────────────── */
[data-testid="stTabs"] [role="tablist"] {
    border-bottom: 2px solid #E2E8F0;
    gap: 0;
    padding: 0;
    background: transparent;
}
[data-testid="stTabs"] button[role="tab"] {
    font-family: 'Inter', sans-serif;
    font-size: 0.825rem;
    font-weight: 500;
    color: #64748B;
    padding: 0.65rem 1.4rem;
    border: none;
    border-bottom: 3px solid transparent;
    background: transparent;
    border-radius: 0;
    letter-spacing: 0.01em;
    transition: color 0.2s, border-color 0.2s;
}
[data-testid="stTabs"] button[role="tab"]:hover { color: #2563EB; }
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    color: #2563EB;
    border-bottom: 3px solid #2563EB;
    font-weight: 600;
}

/* ── Wizard section headers ─────────────────────────────────────────────────── */
.section-label {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #2563EB;
    margin-bottom: 2px;
}
.section-title {
    font-size: 1.05rem;
    font-weight: 600;
    color: #0F172A;
    margin-bottom: 0.1rem;
}
.section-sub {
    font-size: 0.82rem;
    color: #64748B;
    margin-bottom: 1rem;
}
.section-divider {
    height: 1px;
    background: linear-gradient(90deg, #2563EB 0%, #E2E8F0 60%);
    margin: 1.25rem 0 1.5rem 0;
    border: none;
}

/* ── Question labels ────────────────────────────────────────────────────────── */
.question-label {
    font-size: 0.85rem;
    font-weight: 600;
    color: #0F172A;
    margin-bottom: 0.5rem;
    display: block;
}
.question-hint {
    font-size: 0.76rem;
    color: #94A3B8;
    margin-bottom: 0.75rem;
}

/* ── Radio → card style ─────────────────────────────────────────────────────── */
div[data-testid="stRadio"] > div { gap: 0.5rem; }
div[data-testid="stRadio"] label {
    display: flex;
    align-items: flex-start;
    gap: 0.6rem;
    background: #FFFFFF;
    border: 1.5px solid #E2E8F0;
    border-radius: 10px;
    padding: 0.7rem 0.9rem;
    cursor: pointer;
    font-size: 0.825rem;
    font-weight: 500;
    color: #334155;
    transition: border-color 0.18s, background 0.18s, box-shadow 0.18s;
    line-height: 1.45;
    width: 100%;
}
div[data-testid="stRadio"] label:hover {
    border-color: #93C5FD;
    background: #EFF6FF;
    box-shadow: 0 0 0 3px rgba(37,99,235,0.08);
}
div[data-testid="stRadio"] label:has(input:checked) {
    border-color: #2563EB;
    background: #EFF6FF;
    box-shadow: 0 0 0 3px rgba(37,99,235,0.12);
    color: #1D4ED8;
    font-weight: 600;
}
/* Hide the native radio dot */
div[data-testid="stRadio"] input[type="radio"] { display: none; }
div[data-testid="stRadio"] > label:first-child { margin-bottom: 0; }

/* ── Info / alert banner ────────────────────────────────────────────────────── */
.custom-alert {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    background: #F0F7FF;
    border-left: 4px solid #2563EB;
    border-radius: 0 8px 8px 0;
    padding: 0.85rem 1rem;
    margin-top: 1rem;
}
.custom-alert-icon { font-size: 1.05rem; margin-top: 1px; }
.custom-alert-text { font-size: 0.82rem; color: #1E3A5F; line-height: 1.55; }
.custom-alert-text strong { color: #1D4ED8; }

/* ── Upload / paste area cards ──────────────────────────────────────────────── */
.upload-card {
    background: #FFFFFF;
    border: 1.5px dashed #CBD5E1;
    border-radius: 10px;
    padding: 1.1rem 1.25rem 0.75rem;
    transition: border-color 0.2s;
}
.upload-card:hover { border-color: #93C5FD; }

/* ── Primary button ─────────────────────────────────────────────────────────── */
div[data-testid="stButton"] > button[kind="primary"] {
    background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%);
    border: none;
    border-radius: 8px;
    padding: 0.6rem 1.75rem;
    font-size: 0.875rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    color: #FFFFFF;
    box-shadow: 0 2px 8px rgba(37,99,235,0.28);
    transition: box-shadow 0.2s, transform 0.15s;
}
div[data-testid="stButton"] > button[kind="primary"]:hover {
    box-shadow: 0 4px 16px rgba(37,99,235,0.38);
    transform: translateY(-1px);
}

/* ── Metric cards ───────────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 0.9rem 1.1rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}
[data-testid="stMetricLabel"] { font-size: 0.72rem; color: #64748B; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; }
[data-testid="stMetricValue"] { font-size: 1.1rem; font-weight: 700; color: #0F172A; }

/* ── Download button ────────────────────────────────────────────────────────── */
[data-testid="stDownloadButton"] button {
    background: #FFFFFF;
    border: 1.5px solid #2563EB;
    border-radius: 8px;
    color: #2563EB;
    font-weight: 600;
    font-size: 0.85rem;
    padding: 0.55rem 1.4rem;
    transition: background 0.18s, color 0.18s;
}
[data-testid="stDownloadButton"] button:hover {
    background: #EFF6FF;
    color: #1D4ED8;
}

/* ── Spinner text ───────────────────────────────────────────────────────────── */
[data-testid="stSpinner"] p { color: #2563EB; font-weight: 500; font-size: 0.85rem; }

/* ── File uploader ──────────────────────────────────────────────────────────── */
[data-testid="stFileUploader"] section {
    border: 1.5px dashed #CBD5E1;
    border-radius: 10px;
    background: #F8FAFC;
}
[data-testid="stFileUploader"] section:hover { border-color: #93C5FD; background: #F0F7FF; }

/* ── Text area ──────────────────────────────────────────────────────────────── */
[data-testid="stTextArea"] textarea {
    border: 1.5px solid #E2E8F0;
    border-radius: 10px;
    font-size: 0.83rem;
    color: #334155;
    background: #FFFFFF;
    padding: 0.75rem;
}
[data-testid="stTextArea"] textarea:focus {
    border-color: #2563EB;
    box-shadow: 0 0 0 3px rgba(37,99,235,0.1);
    outline: none;
}

/* ── Step 4 intake workspace (premium B2B tiles) ─────────────────────────── */
.intake-tip-banner {
    margin-bottom: 1rem;
}
.intake-section-label {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #64748B;
    margin: 0.5rem 0 0.65rem;
}
.stripe-section-label {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #2563EB;
    padding: 0.75rem 0.9rem 0.25rem;
}
.intake-card-shell {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 14px;
    padding: 1.15rem 1.25rem 0.35rem;
    margin: 0.75rem 0 1rem;
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
}
.intake-mode-shell {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 0.85rem 1rem;
    margin-bottom: 0.85rem;
}
.intake-mode-heading {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #2563EB;
    margin-bottom: 0.35rem;
}
.intake-mode-copy {
    font-size: 0.82rem;
    color: #64748B;
    line-height: 1.5;
    margin-bottom: 0.55rem;
}
.intake-col-tile {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 0.95rem 1rem 0.15rem;
    min-height: 300px;
}
.intake-workspace-tile {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 0.95rem 1rem 0.35rem;
    min-height: 280px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.8);
}
.intake-tile-label {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #2563EB;
    margin-bottom: 0.2rem;
}
.intake-tile-sub {
    font-size: 0.8rem;
    color: #64748B;
    margin-bottom: 0.75rem;
    line-height: 1.45;
}
.intake-tip {
    background: #EFF6FF;
    border-left: 3px solid #2563EB;
    border-radius: 0 8px 8px 0;
    padding: 0.65rem 0.8rem;
    font-size: 0.8rem;
    color: #1E3A5F;
    line-height: 1.5;
    margin-bottom: 0.65rem;
}
.intake-status-card {
    border-radius: 10px;
    padding: 0.85rem 1rem;
    margin: 0.75rem 0 1rem;
    border: 1px solid transparent;
}
.intake-status-warning {
    background: #FFFBEB;
    border-color: #FDE68A;
}
.intake-status-success {
    background: #ECFDF5;
    border-color: #A7F3D0;
}
.intake-status-paywall {
    background: #F8FAFC;
    border-color: #CBD5E1;
}
.intake-status-title {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 0.35rem;
}
.intake-status-warning .intake-status-title { color: #B45309; }
.intake-status-success .intake-status-title { color: #047857; }
.intake-status-paywall .intake-status-title { color: #334155; }
.intake-status-body {
    font-size: 0.84rem;
    color: #334155;
    line-height: 1.55;
}
.stripe-dashboard-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 0.25rem 0.25rem 0.75rem;
    margin: 1rem 0 0.5rem;
    box-shadow: 0 4px 14px rgba(15, 23, 42, 0.06);
    overflow: hidden;
}
.stripe-dashboard-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.84rem;
    color: #334155;
}
.stripe-dashboard-table th {
    text-align: left;
    font-size: 0.68rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #64748B;
    background: #F8FAFC;
    padding: 0.65rem 0.9rem;
    border-bottom: 1px solid #E2E8F0;
}
.stripe-dashboard-table td {
    padding: 0.85rem 0.9rem;
    border-bottom: 1px solid #E2E8F0;
    vertical-align: top;
}
.stripe-muted { color: #64748B; font-size: 0.78rem; }
.stripe-action-cell { color: #2563EB; font-weight: 600; }
.stripe-card-foot {
    font-size: 0.76rem;
    color: #64748B;
    padding: 0.55rem 0.9rem 0;
}
.certified-report-lock {
    background: #F8FAFC;
    border: 1px solid #CBD5E1;
    border-left: 4px solid #2563EB;
    border-radius: 10px;
    padding: 1rem 1.15rem;
    margin: 1rem 0;
    font-size: 0.92rem;
    color: #334155;
    line-height: 1.55;
}
.sandbox-preview-banner {
    background: #FEF2F2;
    border: 1px solid #FECACA;
    color: #B91C1C;
    border-radius: 10px;
    padding: 0.75rem 1rem;
    margin-bottom: 0.85rem;
    text-align: center;
    letter-spacing: 0.04em;
    font-size: 0.82rem;
}
</style>
""", unsafe_allow_html=True)

# ── Corporate dashboard header (copy pulled from the content database) ────────
_app_copy = _content.get("app", {})
st.markdown(f"""
<div style="display:flex;align-items:center;gap:14px;padding:1rem 0 0.25rem;">
  <svg width="36" height="36" viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M18 2L4 8V18C4 25.18 10.08 31.84 18 34C25.92 31.84 32 25.18 32 18V8L18 2Z"
          fill="#2563EB" opacity="0.15"/>
    <path d="M18 2L4 8V18C4 25.18 10.08 31.84 18 34C25.92 31.84 32 25.18 32 18V8L18 2Z"
          stroke="#2563EB" stroke-width="2" stroke-linejoin="round" fill="none"/>
    <path d="M12 18L16 22L24 14" stroke="#2563EB" stroke-width="2.2"
          stroke-linecap="round" stroke-linejoin="round"/>
  </svg>
  <div>
    <div style="font-size:1.55rem;font-weight:700;color:#0F172A;line-height:1.2;letter-spacing:-0.02em;">
      {_app_copy.get("header_title", "")}
    </div>
    <div style="font-size:0.8rem;color:#64748B;font-weight:400;margin-top:1px;">
      {_app_copy.get("header_tagline", "")}
    </div>
  </div>
</div>
<div style="height:1px;background:linear-gradient(90deg,#2563EB 0%,#E2E8F0 55%);margin:1rem 0 1.25rem;"></div>
""", unsafe_allow_html=True)

render_enterprise_sidebar()
render_workspace_engine()

with st.expander("Legal & Imprint", expanded=False):
    render_legal_hub()
