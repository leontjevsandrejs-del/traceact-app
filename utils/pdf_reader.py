"""
Google Files API PDF reader with automatic temporary-file cleanup.

Uploads PDFs to the Gemini Files API, extracts plaintext via the production
model, and deletes each remote file in a ``finally`` block so context files
never accumulate. Falls back to local ``pypdf`` extraction when the API key is
missing or the Files API call fails.
"""

from __future__ import annotations

import io
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator

from google.genai import types
from pypdf import PdfReader

from utils.gemini_client import (
    GEMINI_MODEL,
    call_gemini_generate_content_with_retry,
    get_gemini_client,
)

_FILE_ACTIVE_TIMEOUT_SECONDS = 120.0
_FILE_POLL_INTERVAL_SECONDS = 2.0

_EXTRACTION_PROMPT = (
    "Extract the complete plaintext of this PDF for EU regulatory compliance "
    "analysis. Preserve headings, numbered sections, and paragraph breaks. "
    "Return only the extracted document text — no commentary."
)


def _normalise_pdf_source(
    source: BinaryIO | Path | str | bytes,
) -> BinaryIO | Path | str:
    if isinstance(source, bytes):
        return io.BytesIO(source)
    return source


def _extract_with_pypdf(source: BinaryIO | Path | str | bytes) -> str:
    payload = _normalise_pdf_source(source)
    if isinstance(payload, (str, Path)):
        reader = PdfReader(str(payload))
    else:
        payload.seek(0)
        reader = PdfReader(payload)
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def _safe_delete_file(client, file_name: str | None) -> None:
    if not file_name:
        return
    try:
        client.files.delete(name=file_name)
    except Exception:
        pass


def _wait_until_active(client, file_name: str) -> None:
    """Poll until Google's Files API marks the upload ACTIVE."""
    deadline = time.time() + _FILE_ACTIVE_TIMEOUT_SECONDS
    while time.time() < deadline:
        meta = client.files.get(name=file_name)
        state = getattr(meta, "state", None)
        if state in (types.FileState.ACTIVE, "ACTIVE"):
            return
        if state in (types.FileState.FAILED, "FAILED"):
            raise RuntimeError(f"Gemini Files API processing failed for {file_name}")
        time.sleep(_FILE_POLL_INTERVAL_SECONDS)
    raise TimeoutError(f"Timed out waiting for Gemini file to become ACTIVE: {file_name}")


@contextmanager
def managed_pdf_upload(
    client,
    file_source: BinaryIO | Path | str,
    *,
    display_name: str,
    mime_type: str = "application/pdf",
) -> Iterator[types.File]:
    """
    Upload a PDF to the Gemini Files API and always delete it on exit.

    Yields the uploaded ``File`` handle once processing reaches ACTIVE state.
    """
    uploaded: types.File | None = None
    file_name: str | None = None
    try:
        config = {"mime_type": mime_type, "display_name": display_name}
        if isinstance(file_source, (str, Path)):
            uploaded = client.files.upload(file=str(file_source), config=config)
        else:
            file_source.seek(0)
            uploaded = client.files.upload(file=file_source, config=config)
        file_name = uploaded.name
        _wait_until_active(client, file_name)
        yield uploaded
    finally:
        _safe_delete_file(client, file_name)


def extract_pdf_text_via_files_api(
    source: BinaryIO | Path | str | bytes,
    *,
    display_name: str = "document.pdf",
    client=None,
) -> str:
    """Upload → extract via ``gemini-3.5-flash`` → delete remote file."""
    api_client = client or get_gemini_client()
    if api_client is None:
        raise ValueError("GEMINI_API_KEY is required for Files API PDF extraction.")

    payload = _normalise_pdf_source(source)
    with managed_pdf_upload(
        api_client,
        payload,
        display_name=display_name,
    ) as uploaded:
        return call_gemini_generate_content_with_retry(
            api_client,
            contents=[uploaded, _EXTRACTION_PROMPT],
            model_name=GEMINI_MODEL,
        ).strip()


def extract_pdf_text(
    source: BinaryIO | Path | str | bytes,
    *,
    display_name: str = "document.pdf",
    prefer_files_api: bool = True,
) -> str:
    """
    Extract PDF plaintext using the Files API when available.

    Falls back to ``pypdf`` without raising when the API is unavailable.
    """
    if prefer_files_api and get_gemini_client() is not None:
        try:
            return extract_pdf_text_via_files_api(
                source,
                display_name=display_name,
            )
        except Exception:
            pass

    return _extract_with_pypdf(source)


def extract_pdf_texts_loop(
    items: list[tuple[str, BinaryIO | Path | str | bytes]],
    *,
    prefer_files_api: bool = True,
) -> dict[str, str]:
    """
    Sequentially extract multiple PDFs; each remote upload is deleted before
    the next file is processed.
    """
    results: dict[str, str] = {}
    client = get_gemini_client() if prefer_files_api else None

    for label, source in items:
        text = ""
        try:
            if client is not None:
                text = extract_pdf_text_via_files_api(
                    source,
                    display_name=label,
                    client=client,
                )
            else:
                text = extract_pdf_text(
                    source,
                    display_name=label,
                    prefer_files_api=False,
                )
        except Exception:
            text = extract_pdf_text(
                source,
                display_name=label,
                prefer_files_api=False,
            )
        if text:
            results[label] = text
    return results


def extract_pdf_text_from_path(path: str | Path) -> str:
    """Convenience wrapper for on-disk PDFs (knowledge base, vault files)."""
    pdf_path = Path(path)
    return extract_pdf_text(
        pdf_path,
        display_name=pdf_path.name,
        prefer_files_api=True,
    )
