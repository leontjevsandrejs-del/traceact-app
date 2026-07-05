"""
TraceAct central engine router.

app.py is the core control center: it boots the content database
(content.json → st.session_state.content), applies the corporate dashboard
chrome, and dispatches to the functional views in ui_layouts.py through
Streamlit's native st.navigation framework.
"""

import json
import os

import streamlit as st
from dotenv import load_dotenv

from ui_layouts import render_workspace_engine, render_legal_hub

load_dotenv()

# ── Dashboard settings (must be the first Streamlit call) ─────────────────────
st.set_page_config(
    page_title="TraceAct — EU AI Act Compliance Workspace",
    page_icon="🛡️",
    layout="centered",
    initial_sidebar_state="expanded",
)


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

/* ── Sidebar (navigation) ──────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #0F172A;
    border-right: 1px solid #1E293B;
}
[data-testid="stSidebar"] * { color: #CBD5E1 !important; }
[data-testid="stSidebar"] .stSuccess { background: #064E3B; border: 1px solid #059669; border-radius: 6px; }
[data-testid="stSidebar"] .stError   { background: #7F1D1D; border: 1px solid #DC2626; border-radius: 6px; }

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

# ── Dynamic navigation routes ─────────────────────────────────────────────────
pages = [
    st.Page(
        render_workspace_engine,
        title="Compliance Workspace",
        icon=":material/dashboard:",
        default=True,
    ),
    st.Page(
        render_legal_hub,
        title="Legal & Imprint",
        icon=":material/gavel:",
    ),
]

pg = st.navigation(pages)
pg.run()
