"""
Stripe Checkout session creation — reads ``STRIPE_SECRET_KEY`` from root ``.env``.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_SUCCESS_URL = (
    "https://traceact-app.streamlit.app/?payment=success&draft_id={draft_id}"
)
DEFAULT_CANCEL_URL = "https://traceact-app.streamlit.app/"
ASSESSMENT_PRICE_CENTS = 1  # 0.01 EUR


def _stripe_secret_key() -> str:
    return os.getenv("STRIPE_SECRET_KEY", "").strip()


def create_checkout_session(draft_id: str) -> str | None:
    """
    Create a Stripe Checkout Session and return its hosted payment URL.

    Returns ``None`` when the secret key is missing or Stripe rejects the call.
    """
    secret = _stripe_secret_key()
    if not secret:
        return None

    try:
        import stripe  # type: ignore[import-untyped]
    except ImportError:
        return None

    stripe.api_key = secret
    success_url = os.getenv("STRIPE_SUCCESS_URL", DEFAULT_SUCCESS_URL).format(
        draft_id=draft_id,
    )
    cancel_url = os.getenv("STRIPE_CANCEL_URL", DEFAULT_CANCEL_URL)

    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "eur",
                    "unit_amount": ASSESSMENT_PRICE_CENTS,
                    "product_data": {
                        "name": "TraceAct Certified Assessment",
                        "description": (
                            "Multi-agent EU AI Act conformity evaluation "
                            "and certified PDF report."
                        ),
                    },
                },
                "quantity": 1,
            },
        ],
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=draft_id,
        metadata={"draft_id": draft_id},
    )
    return session.url
