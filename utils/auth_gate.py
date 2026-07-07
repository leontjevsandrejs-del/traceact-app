"""
Enterprise authentication gate for TraceAct B2B SaaS.

Uses streamlit-authenticator for sign-in / registration. Unauthenticated
viewers see only the enterprise login screen; ``st.stop()`` halts the script
before any proprietary multi-agent evaluation logic is loaded.
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

from utils.tenant_db import ensure_company_profile
from utils.user_session import set_authenticated_user

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_AUTH_CONFIG_PATH = _PROJECT_ROOT / "config" / "auth_config.yaml"
_AUTH_STATE_KEY = "_traceact_authenticator"


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
    credentials = cfg.get("credentials", {})
    cookie = cfg.get("cookie", {})
    return stauth.Authenticate(
        credentials,
        cookie_name=cookie.get("name", "traceact_auth"),
        cookie_key=os.getenv(
            "AUTH_COOKIE_KEY",
            cookie.get("key", "traceact_dev_cookie_signing_key_change_me"),
        ),
        cookie_expiry_days=float(cookie.get("expiry_days", 30)),
        auto_hash=True,
    )


def _get_authenticator() -> stauth.Authenticate:
    if _AUTH_STATE_KEY not in st.session_state:
        st.session_state[_AUTH_STATE_KEY] = _build_authenticator()
    return st.session_state[_AUTH_STATE_KEY]


def _render_enterprise_login_shell() -> None:
    st.markdown(
        """
        <div style="max-width:520px;margin:2.5rem auto 1.5rem;text-align:center;">
          <div style="font-size:0.72rem;font-weight:700;letter-spacing:0.14em;
               text-transform:uppercase;color:#2563EB;margin-bottom:0.5rem;">
            TraceAct Enterprise
          </div>
          <div style="font-size:1.65rem;font-weight:700;color:#0F172A;
               letter-spacing:-0.02em;margin-bottom:0.35rem;">
            EU AI Act Compliance Workspace
          </div>
          <div style="font-size:0.9rem;color:#64748B;line-height:1.6;">
            Secure B2B access to the multi-agent conformity auditor.
            Sign in with your corporate credentials or register your organisation.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def enforce_authentication() -> str:
    """
    Render login / registration and return the authenticated username.

    Calls ``st.stop()`` when the session is unauthenticated so downstream
    application code never executes.
    """
    authenticator = _get_authenticator()

    # Restore cookie sessions without rendering the login form.
    if not st.session_state.get("authentication_status"):
        authenticator.login(location="unrendered", key="TraceActSilentLogin")

    if not st.session_state.get("authentication_status"):
        _render_enterprise_login_shell()
        login_tab, register_tab = st.tabs(["Sign In", "Register Organisation"])
        with login_tab:
            authenticator.login(location="main", key="TraceActLogin")
        with register_tab:
            pre_authorized = _load_auth_config().get("preauthorized", {}).get("emails")
            try:
                authenticator.register_user(
                    location="main",
                    pre_authorized=pre_authorized,
                    captcha=False,
                    key="TraceActRegister",
                )
            except Exception as err:
                st.error(f"Registration unavailable: {err}")

    username = st.session_state.get("username")
    auth_status = st.session_state.get("authentication_status")

    if auth_status and username:
        set_authenticated_user(username, st.session_state.get("name") or username)
        ensure_company_profile(
            username,
            contact_email=st.session_state.get("email", ""),
        )
        return username

    if auth_status is False:
        st.error("Invalid username or password.")
    else:
        st.warning("Please sign in or register to access the compliance workspace.")
    st.stop()


def render_account_sidebar() -> None:
    """Authenticated session controls in the sidebar."""
    authenticator = _get_authenticator()
    with st.sidebar:
        st.markdown(f"**Signed in as:** {st.session_state.get('name', '')}")
        authenticator.logout(
            button_name="Sign Out",
            location="sidebar",
            key="TraceActLogout",
        )
