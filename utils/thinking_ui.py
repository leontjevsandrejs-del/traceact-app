"""
Animated “thinking mode” status for long-running agent pipeline steps.

Uses pure CSS animations so the spinner and progress bar keep moving even while
Python is blocked on synchronous Gemini API calls.
"""

from __future__ import annotations

import html
from contextlib import contextmanager

import streamlit as st

THINKING_CSS = """
@keyframes traceact-spin {
  to { transform: rotate(360deg); }
}
@keyframes traceact-bar-slide {
  0% { transform: translateX(-120%); }
  100% { transform: translateX(320%); }
}
.traceact-thinking {
  background: linear-gradient(180deg, #EFF6FF 0%, #F8FAFC 100%);
  border: 1px solid #BFDBFE;
  border-left: 4px solid #2563EB;
  border-radius: 10px;
  padding: 0.95rem 1.1rem;
  margin: 0.75rem 0 1rem;
}
.traceact-thinking-row {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  font-size: 0.92rem;
  color: #1E3A8A;
  line-height: 1.45;
}
.traceact-thinking-spinner {
  flex: 0 0 22px;
  width: 22px;
  height: 22px;
  border: 3px solid #DBEAFE;
  border-top-color: #2563EB;
  border-radius: 50%;
  animation: traceact-spin 0.75s linear infinite;
}
.traceact-thinking-bar-track {
  height: 5px;
  background: #DBEAFE;
  border-radius: 999px;
  overflow: hidden;
  margin-top: 0.7rem;
}
.traceact-thinking-bar-fill {
  width: 35%;
  height: 100%;
  background: linear-gradient(90deg, #2563EB, #60A5FA, #2563EB);
  border-radius: 999px;
  animation: traceact-bar-slide 1.35s ease-in-out infinite;
}
"""


def inject_thinking_styles() -> None:
    """Inject animation CSS once per session."""
    if st.session_state.get("_traceact_thinking_css"):
        return
    st.markdown(f"<style>{THINKING_CSS}</style>", unsafe_allow_html=True)
    st.session_state["_traceact_thinking_css"] = True


def _thinking_html(message: str) -> str:
    safe = html.escape(message)
    return f"""
<div class="traceact-thinking">
  <div class="traceact-thinking-row">
    <div class="traceact-thinking-spinner"></div>
    <div><strong>{safe}</strong></div>
  </div>
  <div class="traceact-thinking-bar-track">
    <div class="traceact-thinking-bar-fill"></div>
  </div>
</div>
"""


@contextmanager
def thinking_mode(message: str):
    """Show a live animated thinking panel for blocking pipeline work."""
    inject_thinking_styles()
    slot = st.empty()
    slot.markdown(_thinking_html(message), unsafe_allow_html=True)
    try:
        yield slot
    finally:
        slot.empty()


def show_thinking_status(message: str):
    """Update an existing thinking panel message (e.g. during API retries)."""
    inject_thinking_styles()
    return st.markdown(_thinking_html(message), unsafe_allow_html=True)
