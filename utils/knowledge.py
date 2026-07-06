"""
Legal knowledge-base loader for the grounding layer.

Ingests every .txt AND .pdf file in knowledge_base/ (the Annex PDFs were
previously ignored by the txt-only loader) and tags each document with a
source header so agents can produce verifiable [source: ...] citations.

The corpus is cached at module level: PDF extraction runs once per process,
not once per audit.
"""

import os

from pypdf import PdfReader

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
    for filename in sorted(os.listdir(kb_path)):
        filepath = os.path.join(kb_path, filename)
        text = ""
        try:
            if filename.lower().endswith(".txt"):
                with open(filepath, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                if text.startswith("[PLACEHOLDER]"):
                    continue
            elif filename.lower().endswith(".pdf"):
                reader = PdfReader(filepath)
                text = "\n".join(
                    (page.extract_text() or "") for page in reader.pages
                ).strip()
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
