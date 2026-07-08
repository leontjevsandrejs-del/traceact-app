"""
Legal knowledge-base loader for the grounding layer.

Ingests every .txt AND .pdf file in knowledge_base/ (the Annex PDFs were
previously ignored by the txt-only loader) and tags each document with a
source header so agents can produce verifiable [source: ...] citations.

PDFs are read through ``utils.pdf_reader`` (local ``pypdf`` for the static
corpus; the Google Files API path is used for wizard evidence uploads).
The corpus is cached at module level: extraction runs once per process.
"""

import os

from utils.pdf_reader import extract_pdf_text

_CACHE: dict[str, str] = {}


def _kb_dir() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "knowledge_base",
    )


def load_legal_knowledge_base(force_reload: bool = False) -> str:
    """Return the full tagged legal corpus (cached)."""
    kb_path = _kb_dir()
    if not force_reload and kb_path in _CACHE:
        return _CACHE[kb_path]
    if not os.path.isdir(kb_path):
        return ""

    sections = []
    pdf_items: list[tuple[str, str]] = []

    for filename in sorted(os.listdir(kb_path)):
        filepath = os.path.join(kb_path, filename)
        text = ""
        try:
            if filename.lower().endswith(".txt"):
                with open(filepath, "r", encoding="utf-8") as fh:
                    text = fh.read().strip()
                if text.startswith("[PLACEHOLDER]"):
                    continue
            elif filename.lower().endswith(".pdf"):
                pdf_items.append((filename, filepath))
                continue
        except Exception:
            continue
        if text:
            sections.append(
                f"<<< SOURCE DOCUMENT: {filename} >>>\n{text}\n"
                f"<<< END OF SOURCE: {filename} >>>"
            )

    for filename, filepath in pdf_items:
        try:
            # Static Annex PDFs: fast local extraction (no remote temp files).
            text = extract_pdf_text(
                filepath,
                display_name=filename,
                prefer_files_api=False,
            )
        except Exception:
            continue
        if text:
            sections.append(
                f"<<< SOURCE DOCUMENT: {filename} >>>\n{text}\n"
                f"<<< END OF SOURCE: {filename} >>>"
            )

    corpus = "\n\n".join(sections)
    _CACHE[kb_path] = corpus
    return corpus


def knowledge_base_inventory() -> list[str]:
    """List the source documents available for citation grounding."""
    kb_path = _kb_dir()
    if not os.path.isdir(kb_path):
        return []
    return sorted(
        f for f in os.listdir(kb_path)
        if f.lower().endswith((".txt", ".pdf"))
        and not f.startswith("eu_ai_act_placeholder")
    )
