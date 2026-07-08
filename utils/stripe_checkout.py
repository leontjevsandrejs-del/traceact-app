"""
Static Stripe Payment Link URL builder.
"""

from __future__ import annotations

from utils.stripe_config import get_stripe_payment_link_url


def build_payment_link_url(draft_id: str) -> str:
    """Append the session draft id as Stripe ``client_reference_id`` pass-through."""
    base = get_stripe_payment_link_url()
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}client_reference_id={draft_id}"
