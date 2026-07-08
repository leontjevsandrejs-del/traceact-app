"""
Stripe credential resolution — Streamlit Cloud secrets first, local ``.env`` fallback.
"""

from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def get_stripe_secret_key() -> str:
    """
    Resolve ``STRIPE_SECRET_KEY`` for local and Streamlit Cloud runtimes.

    1. ``st.secrets.get("STRIPE_SECRET_KEY")`` (Cloud)
    2. ``os.getenv("STRIPE_SECRET_KEY")`` after ``load_dotenv()`` (local)
    """
    key = None
    try:
        key = st.secrets.get("STRIPE_SECRET_KEY")
    except Exception:
        key = None
    if not key:
        key = os.getenv("STRIPE_SECRET_KEY", "")
    return (key or "").strip()


def configure_stripe_api_key() -> str:
    """Set ``stripe.api_key`` when a secret is available. Returns the key."""
    secret = get_stripe_secret_key()
    if not secret:
        return ""
    try:
        import stripe  # type: ignore[import-untyped]

        stripe.api_key = secret
    except ImportError:
        return ""
    return secret
