"""
Enterprise authentication gate for TraceAct B2B SaaS.

Unauthenticated viewers see only an isolated login portal. The authenticated
application shell (sidebar, wizard, multi-agent pipeline) loads only after
``authentication_status`` is True.
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
import streamlit_authenticator as stauth
import yaml

from utils.auth_session import (
    AUTHENTICATOR_STATE_KEY,
    AUTH_STATUS_KEY,
    AUTH_USERNAME_KEY,
)
from utils.credential_store import (
    load_merged_credentials,
    register_runtime_user,
    sync_yaml_credentials_snapshot,
)
from utils.tenant_db import ensure_company_profile
from utils.user_session import sync_auth_session

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_AUTH_CONFIG_PATH = _PROJECT_ROOT / "config" / "auth_config.yaml"
_AUTH_STATE_KEY = AUTHENTICATOR_STATE_KEY
_OPEN_REGISTRATION = object()


def _load_auth_config() -> dict:
    if _AUTH_CONFIG_PATH.is_file():
        with open(_AUTH_CONFIG_PATH, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    try:
        return dict(st.secrets.get("auth", {}))
    except Exception:
        return {}


def _build_authenticator() -> stauth.Authenticate:
    cfg = _load_auth_config()
    cookie = cfg.get("cookie", {})
    return stauth.Authenticate(
        load_merged_credentials(),
        cookie_name=cookie.get("name", "traceact_auth"),
        cookie_key=os.getenv(
            "AUTH_COOKIE_KEY",
            cookie.get("key", "traceact_dev_cookie_signing_key_change_me"),
        ),
        cookie_expiry_days=float(cookie.get("expiry_days", 30)),
        auto_hash=True,
    )


def _reset_authenticator_cache() -> None:
    st.session_state.pop(_AUTH_STATE_KEY, None)


def _registration_preauthorized():
    if os.getenv("AUTH_INVITE_ONLY", "").lower() not in ("1", "true", "yes"):
        return _OPEN_REGISTRATION
    cfg = _load_auth_config()
    emails = cfg.get("pre-authorized", {}).get("emails")
    if emails is None:
        emails = cfg.get("preauthorized", {}).get("emails")
    return list(emails or [])


def _register_user(authenticator: stauth.Authenticate, **kwargs):
    policy = _registration_preauthorized()
    pre_authorized = None if policy is _OPEN_REGISTRATION else policy
    return authenticator.authentication_controller.register_user(
        kwargs["new_first_name"],
        kwargs["new_last_name"],
        kwargs["new_email"],
        kwargs["new_username"],
        kwargs["new_password"],
        kwargs["new_password_repeat"],
        kwargs.get("password_hint") or "",
        pre_authorized,
        kwargs.get("domains"),
        kwargs.get("roles"),
        kwargs.get("callback"),
        kwargs.get("captcha", False),
        kwargs.get("entered_captcha"),
    )


def _get_authenticator() -> stauth.Authenticate:
    if _AUTH_STATE_KEY not in st.session_state:
        st.session_state[_AUTH_STATE_KEY] = _build_authenticator()
    return st.session_state[_AUTH_STATE_KEY]


def _restore_session_from_cookie() -> None:
    """Silent cookie re-auth — no UI."""
    if st.session_state.get(AUTH_STATUS_KEY) is True:
        return
    authenticator = _get_authenticator()
    authenticator.login(location="unrendered", key="TraceActSilentLogin")


def _inject_login_portal_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        html, body, [class*="css"] {
            font-family: 'Inter', 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(160deg, #EFF6FF 0%, #F8FAFC 45%, #E2E8F0 100%);
        }
        #MainMenu, footer, header { visibility: hidden; }
        section[data-testid="stSidebar"],
        [data-testid="stSidebarCollapsedControl"] {
            display: none !important;
        }
        [data-testid="stNavigation"] { display: none !important; }
        .main .block-container {
            max-width: 480px !important;
            padding: 2rem 1.75rem 2.25rem;
            margin-top: 2.5rem;
            margin-bottom: 3rem;
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 18px;
            box-shadow: 0 24px 48px rgba(15, 23, 42, 0.08);
        }
        .traceact-login-eyebrow {
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: #2563EB;
            text-align: center;
            margin-bottom: 0.45rem;
        }
        .traceact-login-title {
            font-size: 1.55rem;
            font-weight: 700;
            color: #0F172A;
            text-align: center;
            letter-spacing: -0.02em;
            margin-bottom: 0.35rem;
        }
        .traceact-login-sub {
            font-size: 0.88rem;
            color: #64748B;
            text-align: center;
            line-height: 1.6;
            margin-bottom: 1.25rem;
        }
        div[data-testid="stTabs"] [role="tablist"] {
            border-bottom: 2px solid #E2E8F0;
            gap: 0;
        }
        div[data-testid="stTabs"] button[role="tab"] {
            font-size: 0.82rem;
            font-weight: 600;
            color: #64748B;
            padding: 0.55rem 1rem;
            border-bottom: 3px solid transparent;
            background: transparent;
        }
        div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            color: #2563EB;
            border-bottom-color: #2563EB;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_login_portal_header() -> None:
    st.markdown(
        """
        <div style="text-align:center;margin-bottom:1rem;">
            <svg width="48" height="48" viewBox="0 0 36 36" fill="none"
                 xmlns="http://www.w3.org/2000/svg">
              <path d="M18 2L4 8V18C4 25.18 10.08 31.84 18 34C25.92 31.84 32 25.18 32 18V8L18 2Z"
                    fill="#2563EB" opacity="0.15"/>
              <path d="M18 2L4 8V18C4 25.18 10.08 31.84 18 34C25.92 31.84 32 25.18 32 18V8L18 2Z"
                    stroke="#2563EB" stroke-width="2" stroke-linejoin="round" fill="none"/>
              <path d="M12 18L16 22L24 14" stroke="#2563EB" stroke-width="2.2"
                    stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          <div class="traceact-login-eyebrow">TraceAct Enterprise</div>
          <div class="traceact-login-title">EU AI Act Compliance Workspace</div>
          <div class="traceact-login-sub">
            Secure B2B access to the multi-agent conformity auditor.
            Sign in or register your organisation to begin.
          </div>
        """,
        unsafe_allow_html=True,
    )


def _try_auto_login_after_registration(
    authenticator: stauth.Authenticate,
    username: str,
    password: str,
    contact_email: str,
) -> bool:
    """Mount the workspace immediately after successful registration."""
    if authenticator.authentication_controller.login(username, password):
        authenticator.cookie_controller.set_cookie()
        ensure_company_profile(username, contact_email=contact_email)
        sync_auth_session()
        st.rerun()
    return False


def _render_registration_form(authenticator: stauth.Authenticate) -> None:
    with st.form("TraceActRegister", clear_on_submit=False):
        st.subheader("Register Organisation")
        col1, col2 = st.columns(2)
        first_name = col1.text_input("First name", autocomplete="off")
        last_name = col2.text_input("Last name", autocomplete="off")
        email = st.text_input("Email", autocomplete="off")
        username = st.text_input("Username", autocomplete="off")
        password = st.text_input("Password", type="password", autocomplete="off")
        password_repeat = st.text_input("Repeat password", type="password", autocomplete="off")
        password_hint = st.text_input("Password hint (optional)", autocomplete="off")
        submitted = st.form_submit_button("Register", type="primary")

    if not submitted:
        return

    try:
        registered_email, registered_user, registered_name = _register_user(
            authenticator,
            new_first_name=first_name,
            new_last_name=last_name,
            new_email=email,
            new_username=username,
            new_password=password,
            new_password_repeat=password_repeat,
            password_hint=password_hint,
            captcha=False,
        )
    except Exception as err:
        st.error(f"Registration unavailable: {err}")
        return

    if registered_email and registered_user:
        saved_user = register_runtime_user(
            registered_user,
            registered_email,
            registered_name,
            password,
            password_hint=password_hint,
        )
        creds = _extract_live_credentials(authenticator)
        if creds:
            sync_yaml_credentials_snapshot(creds)
        _reset_authenticator_cache()
        authenticator = _get_authenticator()
        _try_auto_login_after_registration(
            authenticator, saved_user, password, registered_email,
        )
        st.success(
            f"Organisation registered for **{registered_name}**. "
            f"Sign in with username **`{saved_user}`** on the **Sign In** tab."
        )


def _extract_live_credentials(authenticator: stauth.Authenticate) -> dict | None:
    controller = getattr(authenticator, "authentication_controller", None)
    if controller is None:
        return None
    if hasattr(controller, "credentials"):
        return controller.credentials
    model = getattr(controller, "authentication_model", None)
    if model is not None and hasattr(model, "credentials"):
        return model.credentials
    return None


def get_sidebar_authenticator() -> stauth.Authenticate:
    """Expose authenticator for sidebar logout (post-authentication only)."""
    return _get_authenticator()


def render_isolated_login_portal() -> None:
    """Full-screen login portal — no sidebar, wizard, or workspace chrome."""
    _inject_login_portal_css()
    _render_login_portal_header()

    authenticator = _get_authenticator()
    login_tab, register_tab = st.tabs(["Sign In", "Register Organisation"])
    with login_tab:
        authenticator.login(location="main", key="TraceActLogin")
    with register_tab:
        _render_registration_form(authenticator)

    auth_status = st.session_state.get(AUTH_STATUS_KEY)
    if auth_status is False:
        st.error(
            "Invalid username or password. Usernames are stored in lowercase — "
            "try again or re-register if this is a new deployment."
        )
    elif auth_status is not True:
        st.warning("Please sign in or register to access the compliance workspace.")


def authenticate_or_show_portal() -> bool:
    """
    Restore cookie session, then either admit the user or render the login wall.

    Returns True when ``authentication_status`` is active and the username is
    synced into TraceAct session scope.
    """
    _restore_session_from_cookie()

    username = sync_auth_session() or st.session_state.get(AUTH_USERNAME_KEY)
    if st.session_state.get(AUTH_STATUS_KEY) is True and username:
        ensure_company_profile(
            username,
            contact_email=st.session_state.get("email", ""),
        )
        return True

    render_isolated_login_portal()

    # Login may have succeeded during form submission in this run.
    username = sync_auth_session() or st.session_state.get(AUTH_USERNAME_KEY)
    if st.session_state.get(AUTH_STATUS_KEY) is True and username:
        ensure_company_profile(
            username,
            contact_email=st.session_state.get("email", ""),
        )
        st.rerun()

    return False


def enforce_authentication() -> str:
    """
    Primary auth entrypoint for ``app.py``.

    Renders the isolated login portal when unauthenticated and calls
    ``st.stop()`` so no workspace modules execute.
    """
    if not authenticate_or_show_portal():
        st.stop()
    return sync_auth_session()


__all__ = [
    "authenticate_or_show_portal",
    "enforce_authentication",
    "get_sidebar_authenticator",
    "render_isolated_login_portal",
]
