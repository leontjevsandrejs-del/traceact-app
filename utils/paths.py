"""
Cross-platform path helpers for the desktop auditor.

Streamlit's worker thread can inherit a synthetic HOME (e.g. /home/appuser)
inside PyInstaller bundles. Resolving Downloads via expanduser("~") therefore
lands in the wrong place on Windows. This module uses the OS shell APIs first.
"""

import os
import sys
from pathlib import Path


def _windows_downloads_via_shell() -> str | None:
    """Return the logged-in user's Downloads folder via SHGetKnownFolderPath."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", wintypes.BYTE * 8),
            ]

        FOLDERID_Downloads = GUID(
            0x374DE290,
            0x123F,
            0x4565,
            (0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B),
        )

        path_ptr = ctypes.c_wchar_p()
        hr = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(FOLDERID_Downloads),
            0,
            None,
            ctypes.byref(path_ptr),
        )
        if hr == 0 and path_ptr.value:
            result = path_ptr.value
            ctypes.windll.ole32.CoTaskMemFree(path_ptr)
            return result
    except Exception:
        pass
    return None


def _windows_userprofile_downloads() -> str | None:
    profile = os.environ.get("USERPROFILE", "").strip()
    if profile and not profile.startswith("/"):
        return os.path.join(profile, "Downloads")
    return None


def _xdg_downloads() -> str | None:
    xdg = os.environ.get("XDG_DOWNLOAD_DIR", "").strip()
    if xdg:
        return xdg
    xdg_config = Path.home() / ".config" / "user-dirs.dirs"
    if xdg_config.is_file():
        try:
            for line in xdg_config.read_text(encoding="utf-8").splitlines():
                if line.startswith("XDG_DOWNLOAD_DIR="):
                    raw = line.split("=", 1)[1].strip().strip('"')
                    return raw.replace("$HOME", str(Path.home()))
        except OSError:
            pass
    return None


def get_downloads_directory() -> Path:
    """
    Resolve the interactive user's Downloads folder.

    Resolution order:
      Windows — SHGetKnownFolderPath (immune to wrong HOME), then USERPROFILE
      Linux   — XDG_DOWNLOAD_DIR, then ~/Downloads
      macOS   — ~/Downloads
    """
    if sys.platform == "win32":
        for resolver in (_windows_downloads_via_shell, _windows_userprofile_downloads):
            path = resolver()
            if path:
                return Path(path)

    xdg = _xdg_downloads()
    if xdg:
        return Path(xdg)

    return Path.home() / "Downloads"


def pin_interactive_user_profile() -> None:
    """
    Write the real interactive profile into USERPROFILE/HOME before Streamlit
    boots so downstream libraries do not inherit a synthetic /home/appuser.
    """
    downloads = get_downloads_directory()
    profile = str(downloads.parent)

    if sys.platform == "win32":
        os.environ["USERPROFILE"] = profile
        if len(profile) >= 3 and profile[1] == ":" and profile[2] == "\\":
            os.environ["HOMEDRIVE"] = profile[:2]
            os.environ["HOMEPATH"] = profile[2:]
    os.environ["HOME"] = profile
