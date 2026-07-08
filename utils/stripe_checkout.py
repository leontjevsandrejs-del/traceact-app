"""
Stripe Checkout session creation — dual-environment key loading via ``stripe_config``.
"""

from __future__ import annotations

import os

import streamlit as st

from utils.stripe_config import (
    configure_stripe_api_key,
    get_stripe_price_id,
)

DEFAULT_SUCCESS_URL = (
    "https://traceact-app.streamlit.app/?payment=success&draft_id={draft_id}"
)
DEFAULT_CANCEL_URL = "https://traceact-app.streamlit.app/"


def _resolve_checkout_mode(stripe, price_id: str) -> str:
    """
    Match Checkout ``mode`` to the Stripe Price object type.

    Uses ``STRIPE_CHECKOUT_MODE`` when set; otherwise inspects the Price via API.
    """
    override = os.getenv("STRIPE_CHECKOUT_MODE", "").strip().lower()
    if override in ("subscription", "payment"):
        return override
    try:
        price = stripe.Price.retrieve(price_id)
        if getattr(price, "recurring", None):
            return "subscription"
    except Exception:
        pass
    return "payment"


def create_checkout_session(draft_id: str) -> str | None:
    """
    Create a Stripe Checkout Session and return its hosted payment URL.

    Returns ``None`` when configuration is missing or Stripe rejects the call.
    Stripe API errors are surfaced via ``st.error`` instead of crashing the app.
    """
    secret = configure_stripe_api_key()
    if not secret:
        st.error(
            "Stripe checkout could not be started. "
            "Add STRIPE_SECRET_KEY to Streamlit secrets (Cloud) "
            "or the root .env file (local)."
        )
        return None

    price_id = get_stripe_price_id()
    if not price_id:
        st.error(
            "Stripe checkout could not be started. "
            "Add STRIPE_PRICE_ID to Streamlit secrets (Cloud) "
            "or the root .env file (local)."
        )
        return None

    try:
        import stripe  # type: ignore[import-untyped]
    except ImportError:
        st.error("Stripe Python package is not installed.")
        return None

    success_url = os.getenv("STRIPE_SUCCESS_URL", DEFAULT_SUCCESS_URL).format(
        draft_id=draft_id,
    )
    cancel_url = os.getenv("STRIPE_CANCEL_URL", DEFAULT_CANCEL_URL)
    checkout_mode = _resolve_checkout_mode(stripe, price_id)

    line_items = [
        {
            "price": price_id,
            "quantity": 1,
        },
    ]

    try:
        session = stripe.checkout.Session.create(
            mode=checkout_mode,
            line_items=line_items,
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=draft_id,
            metadata={"draft_id": draft_id},
        )
    except stripe.error.StripeError as err:
        st.error(f"Stripe Error: {err.user_message or err}")
        return None

    return session.url
