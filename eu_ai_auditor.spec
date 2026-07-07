# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for EU AI Act Compliance Auditor
# Run from the project root:
#   pyinstaller eu_ai_auditor.spec --noconfirm
#
# Requirements before building:
#   pip install pyinstaller pywebview streamlit fpdf2 pypdf python-dotenv google-genai
#

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_all, copy_metadata

project_root = Path(SPECPATH)   # directory containing this .spec file

# ── Collect everything Streamlit needs (static assets, templates, etc.) ──────
st_datas, st_binaries, st_hiddenimports = collect_all("streamlit")

# ── Extra metadata that Streamlit inspects at runtime via importlib.metadata ──
meta_packages = [
    "streamlit", "altair", "click", "packaging", "pydeck",
    "requests", "rich", "toml", "toolz", "typing_extensions",
]
extra_datas = []
for pkg in meta_packages:
    try:
        extra_datas += copy_metadata(pkg)
    except Exception:
        pass

# ── Project-specific data files ───────────────────────────────────────────────
project_datas = [
    # (source_path,          destination_folder_inside_bundle)
    (str(project_root / "app.py"),            "."),
    (str(project_root / "ui_layouts.py"),     "."),
    (str(project_root / "content.json"),      "."),
    (str(project_root / ".streamlit"),        ".streamlit"),
    (str(project_root / ".env"),              "."),
    (str(project_root / "config"),            "config"),
    (str(project_root / "utils"),             "utils"),
    (str(project_root / "knowledge_base"),    "knowledge_base"),
]

all_datas = st_datas + extra_datas + project_datas

# ── Hidden imports Streamlit / its deps need but PyInstaller misses ───────────
hidden_imports = st_hiddenimports + [
    # Streamlit internals
    "streamlit.runtime.scriptrunner.magic_funcs",
    "streamlit.runtime.caching",
    # Google GenAI SDK
    "google.genai",
    "google.genai.errors",
    "google.auth",
    "google.auth.transport.requests",
    # PDF / document
    "fpdf",
    "pypdf",
    # Standard lib used at runtime
    "email.mime.multipart",
    "email.mime.text",
    # pywebview native back-end (Windows)
    "webview",
    "webview.platforms.winforms",
    "clr",
    # B2B auth (web deployment via app.py)
    "streamlit_authenticator",
    "yaml",
    "bcrypt",
    "extra_streamlit_components",
]

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    [str(project_root / "launcher.py")],
    pathex=[str(project_root)],
    binaries=st_binaries,
    datas=all_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim unused heavy packages to keep the bundle smaller
        "matplotlib", "scipy", "PIL.ImageQt", "PyQt5", "PyQt6", "tkinter",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EU_AI_Act_Auditor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # pure desktop window — no terminal
    icon=None,              # swap in a .ico path here if you have one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="EU_AI_Act_Auditor",
)
