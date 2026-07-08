"""
Centralised Gemini client and retry lane for TraceAct.

All model calls use ``gemini-3.5-flash`` exclusively — no legacy fallbacks.
"""

from __future__ import annotations

import os
import time

from google import genai
from google.genai.errors import APIError, ClientError

GEMINI_MODEL = "gemini-3.5-flash"
MAX_GEMINI_RETRIES = 3


def get_gemini_api_key() -> str | None:
    key = os.getenv("GEMINI_API_KEY", "").strip().strip("\"'")
    if not key or key == "YOUR_ACTUAL_API_KEY_HERE":
        return None
    return key


def get_gemini_client() -> genai.Client | None:
    api_key = get_gemini_api_key()
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


def _is_transient_error(err: Exception) -> bool:
    """Return True for retryable 503 / ResourceExhausted / overload conditions."""
    if isinstance(err, (ClientError, APIError)):
        status = getattr(err, "status_code", None) or getattr(err, "code", None)
        if status in (429, 503, 504):
            return True
    err_upper = str(err).upper()
    return any(
        token in err_upper
        for token in ("503", "429", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "OVERLOADED")
    )


def _display_pipeline_error(err: Exception) -> None:
    try:
        import streamlit as st

        st.error(f"Multi-Agent Pipeline Failure: {err}")
    except Exception:
        pass


def call_gemini_with_retry(client, prompt, model_name: str | None = None) -> str:
    """
    Execute a Gemini generate_content call with exponential backoff retries.

    Retries up to ``MAX_GEMINI_RETRIES`` times on transient 503 / overload
    errors. Uses only ``gemini-3.5-flash`` — no model fallback.
    """
    model = model_name or GEMINI_MODEL

    for attempt in range(MAX_GEMINI_RETRIES):
        try:
            result = client.models.generate_content(model=model, contents=prompt)
            return result.text
        except Exception as err:
            if not _is_transient_error(err):
                _display_pipeline_error(err)
                raise err from err

            if attempt < MAX_GEMINI_RETRIES - 1:
                time.sleep(2 ** (attempt + 1))
                continue

            _display_pipeline_error(err)
            raise err from err

    raise RuntimeError("Gemini API call failed without a captured exception.")
