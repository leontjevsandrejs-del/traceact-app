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
MAX_GEMINI_RETRIES = 5


def get_gemini_api_key() -> str | None:
    key = None
    try:
        import streamlit as st

        key = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        key = None
    if not key:
        key = os.getenv("GEMINI_API_KEY", "")
    key = str(key or "").strip().strip("\"'")
    if not key or key == "YOUR_ACTUAL_API_KEY_HERE":
        return None
    return key


def get_gemini_client() -> genai.Client | None:
    """Prefer Vertex AI (europe-west1) when enterprise GCP secrets are configured."""
    try:
        import streamlit as st
        from google.oauth2 import service_account

        gcp_info = st.secrets.get("gcp_service_account")
        if gcp_info:
            credentials = service_account.Credentials.from_service_account_info(
                dict(gcp_info),
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            return genai.Client(
                vertexai=True,
                project=gcp_info["project_id"],
                location="europe-west1",
                credentials=credentials,
            )
    except Exception:
        pass

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

        if _is_transient_error(err):
            st.error(
                "**Gemini API temporarily unavailable (503).**\n\n"
                "Google reports high demand on `gemini-3.5-flash`. "
                "Wait **60–90 seconds**, then click **Run Compliance Audit** again.\n\n"
                f"Technical detail: `{err}`"
            )
        else:
            st.error(f"Multi-Agent Pipeline Failure: {err}")
    except Exception:
        pass


def _backoff_seconds(attempt: int) -> int:
    """Exponential backoff: 3s, 6s, 12s, 24s between retries."""
    return min(3 * (2 ** attempt), 30)


def _wait_with_status(attempt: int, max_attempts: int, delay: int) -> None:
    """Show animated thinking UI during API retry backoff."""
    try:
        from utils.thinking_ui import inject_thinking_styles, _thinking_html
        import streamlit as st

        inject_thinking_styles()
        status = st.empty()
        for remaining in range(delay, 0, -1):
            status.markdown(
                _thinking_html(
                    f"{GEMINI_MODEL} is overloaded (503). "
                    f"Retry {attempt + 1}/{max_attempts} in {remaining}s…"
                ),
                unsafe_allow_html=True,
            )
            time.sleep(1)
        status.empty()
    except Exception:
        time.sleep(delay)


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
            return result.text or ""
        except Exception as err:
            if not _is_transient_error(err):
                _display_pipeline_error(err)
                raise err from err

            if attempt < MAX_GEMINI_RETRIES - 1:
                _wait_with_status(attempt, MAX_GEMINI_RETRIES, _backoff_seconds(attempt))
                continue

            _display_pipeline_error(err)
            raise err from err

    raise RuntimeError("Gemini API call failed without a captured exception.")
