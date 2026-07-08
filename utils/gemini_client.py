"""
Centralised Gemini client and retry lane for TraceAct.

All model calls use ``gemini-2.5-flash`` exclusively — no legacy fallbacks.
"""

from __future__ import annotations

import os
import time

from google import genai

GEMINI_MODEL = "gemini-2.5-flash"
MAX_GEMINI_RETRIES = 3
RETRY_PAUSE_SECONDS = 2


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


def _display_pipeline_error(err: Exception) -> None:
    try:
        import streamlit as st

        st.error(f"Multi-Agent Pipeline Failure: {err}")
    except Exception:
        pass


def call_gemini_with_retry(client, prompt, model_name: str | None = None) -> str:
    """
    Execute a Gemini generate_content call with a linear retry loop.

    Retries up to ``MAX_GEMINI_RETRIES`` times on any transient failure,
    pausing ``RETRY_PAUSE_SECONDS`` between attempts. Uses only
    ``gemini-2.5-flash`` — no model fallback.
    """
    model = model_name or GEMINI_MODEL

    for attempt in range(MAX_GEMINI_RETRIES):
        try:
            result = client.models.generate_content(model=model, contents=prompt)
            return result.text
        except Exception as err:
            if attempt < MAX_GEMINI_RETRIES - 1:
                time.sleep(RETRY_PAUSE_SECONDS)
                continue
            _display_pipeline_error(err)
            raise err from err

    raise RuntimeError("Gemini API call failed without a captured exception.")
