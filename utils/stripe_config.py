"""
Stripe credential resolution — Streamlit Cloud secrets first, local ``.env`` fallback.
"""

from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

DEFAULT_ONE_TIME_REPORT_PAYMENT_LINK = (
    "https://buy.stripe.com/fZu3cw4GQceVahGaF687K01"
)


def sanitize_env_string(value: str | None) -> str:
    """Strip whitespace, newlines, and stray quotation marks from env values."""
    if not value:
        return ""
    cleaned = str(value).strip().replace('"', "").replace("'", "")
    cleaned = cleaned.replace("\n", "").replace("\r", "")
    return cleaned.strip()


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


def get_stripe_price_id() -> str:
    """
    Resolve ``STRIPE_PRICE_ID`` for local and Streamlit Cloud runtimes.

    1. ``st.secrets.get("STRIPE_PRICE_ID")`` (Cloud)
    2. ``os.getenv("STRIPE_PRICE_ID")`` after ``load_dotenv()`` (local)
    """
    price_id = None
    try:
        price_id = st.secrets.get("STRIPE_PRICE_ID")
    except Exception:
        price_id = None
    if not price_id:
        price_id = os.getenv("STRIPE_PRICE_ID", "")
    return (price_id or "").strip()


def get_stripe_payment_link() -> str:
    """
    Resolve and sanitize the static Stripe Payment Link URL.

    1. ``st.secrets.get("STRIPE_PAYMENT_LINK")`` (Streamlit Cloud)
    2. ``os.getenv("STRIPE_PAYMENT_LINK")`` after ``load_dotenv()`` (local)
    """
    base_link = ""
    try:
        base_link = sanitize_env_string(st.secrets.get("STRIPE_PAYMENT_LINK"))
    except Exception:
        base_link = ""
    if not base_link:
        base_link = sanitize_env_string(os.getenv("STRIPE_PAYMENT_LINK", ""))
    return base_link


def get_stripe_growth_payment_link() -> str:
    """
    Resolve the Growth Monitor subscription Payment Link URL.

    1. ``st.secrets.get("STRIPE_GROWTH_PAYMENT_LINK")`` (Streamlit Cloud)
    2. ``os.getenv("STRIPE_GROWTH_PAYMENT_LINK")`` (local)
    """
    growth_link = ""
    try:
        growth_link = sanitize_env_string(st.secrets.get("STRIPE_GROWTH_PAYMENT_LINK"))
    except Exception:
        growth_link = ""
    if not growth_link:
        growth_link = sanitize_env_string(os.getenv("STRIPE_GROWTH_PAYMENT_LINK", ""))
    return growth_link


def get_stripe_one_time_payment_link() -> str:
    """
    Resolve the single-report one-time Payment Link URL (€149).

    1. ``st.secrets.get("STRIPE_ONE_TIME_PAYMENT_LINK")`` (Streamlit Cloud)
    2. ``os.getenv("STRIPE_ONE_TIME_PAYMENT_LINK")`` (local)
    3. Built-in €149 report link (never the legacy ``STRIPE_PAYMENT_LINK``)
    """
    one_time_link = ""
    try:
        one_time_link = sanitize_env_string(
            st.secrets.get("STRIPE_ONE_TIME_PAYMENT_LINK")
        )
    except Exception:
        one_time_link = ""
    if not one_time_link:
        one_time_link = sanitize_env_string(
            os.getenv("STRIPE_ONE_TIME_PAYMENT_LINK", "")
        )
    if not one_time_link:
        one_time_link = DEFAULT_ONE_TIME_REPORT_PAYMENT_LINK
    return one_time_link


def get_stripe_payment_link_url() -> str:
    """Back-compat alias for :func:`get_stripe_payment_link`."""
    return get_stripe_payment_link()
