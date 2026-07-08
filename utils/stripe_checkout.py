"""
Static Stripe Payment Link URL builder.
"""

from __future__ import annotations

from utils.stripe_config import get_stripe_payment_link


def build_payment_link_url(draft_id: str) -> str:
    """Append the session draft id as Stripe ``client_reference_id`` pass-through."""
    base_link = get_stripe_payment_link()
    if not base_link:
        return "#"
    separator = "&" if "?" in base_link else "?"
    return f"{base_link}{separator}client_reference_id={draft_id}"
