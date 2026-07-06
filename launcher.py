"""
Standalone desktop entry point for the EU AI Act Compliance Auditor.

Streamlit runs headless on a background thread; pywebview hosts the UI on the
main thread. No custom Starlette routes or ASGI middleware are used here.
"""

import os
import signal
import socket
import sys
import tempfile
import threading
import time
import traceback
import webbrowser

import webview
from streamlit.web import bootstrap

STREAMLIT_PORT = 8506
STREAMLIT_URL = f"http://127.0.0.1:{STREAMLIT_PORT}"

LOG_PATH = os.path.join(tempfile.gettempdir(), "eu_ai_auditor_startup.log")


def _log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _prepare_runtime_paths() -> None:
    """Ensure app.py resolves correctly in dev and PyInstaller bundles."""
    if getattr(sys, "frozen", False):
        os.chdir(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
    else:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))


def _block_external_browser() -> None:
    """Prevent Streamlit (or any dependency) from opening the system browser."""
    webbrowser.open = lambda *args, **kwargs: False  # type: ignore[assignment]


def _configure_streamlit_env() -> None:
    """Force headless local-server settings before bootstrap starts."""
    from utils.paths import pin_interactive_user_profile

    pin_interactive_user_profile()
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
    os.environ["STREAMLIT_SERVER_PORT"] = str(STREAMLIT_PORT)
    os.environ["STREAMLIT_SERVER_ADDRESS"] = "127.0.0.1"
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"


def _wait_for_tcp(port: int, timeout: int = 60) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def start_server() -> None:
    flag_options = {
        "server.port": STREAMLIT_PORT,
        "server.address": "127.0.0.1",
        "server.headless": True,
        "global.developmentMode": False,
        "browser.gatherUsageStats": False,
    }

    # Streamlit registers signal handlers during bootstrap; ignore failures
    # when this worker is not running on the main thread.
    _real_signal = signal.signal

    def _noop_signal(signum, handler):
        try:
            return _real_signal(signum, handler)
        except (ValueError, OSError):
            pass

    signal.signal = _noop_signal  # type: ignore[assignment]
    try:
        app_path = os.path.abspath("app.py")
        _log(f"Starting engine. app.py={app_path} exists={os.path.isfile(app_path)}")
        # bootstrap.run() alone does not apply flag_options — they must be
        # loaded into Streamlit's config first, or the server binds to 8501.
        bootstrap.load_config_options(flag_options=flag_options)
        # Second arg is the is_hello flag (bool) in current Streamlit versions.
        bootstrap.run(app_path, False, [], flag_options=flag_options)
        _log("bootstrap.run returned.")
    except Exception:
        _log("Engine crashed:\n" + traceback.format_exc())
    finally:
        signal.signal = _real_signal


if __name__ == "__main__":
    try:
        open(LOG_PATH, "w").close()
    except Exception:
        pass
    _log(f"=== startup === frozen={getattr(sys, 'frozen', False)}")
    _prepare_runtime_paths()
    _log(f"cwd={os.getcwd()}")
    _block_external_browser()
    _configure_streamlit_env()

    threading.Thread(target=start_server, daemon=True).start()

    if _wait_for_tcp(STREAMLIT_PORT, timeout=60):
        webview.create_window(
            "EU AI Act Compliance Auditor",
            STREAMLIT_URL,
            width=1300,
            height=850,
        )
    else:
        # No console in the packaged build — surface the failure in the window.
        error_html = """<!DOCTYPE html>
<html><body style="font-family:Segoe UI,Arial,sans-serif;background:#fff7ed;
      color:#7c2d12;padding:32px;">
  <h2>Startup Failed</h2>
  <p>The internal application engine did not start within 60 seconds.</p>
  <p>Details were written to the log file:<br><code>{log}</code></p>
</body></html>""".format(log=LOG_PATH)
        webview.create_window(
            "EU AI Act Compliance Auditor",
            html=error_html,
            width=1300,
            height=850,
        )
    webview.start()
