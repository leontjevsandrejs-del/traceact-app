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

from utils.tenant_db import ensure_company_profile
from utils.user_session import set_authenticated_user

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_AUTH_CONFIG_PATH = _PROJECT_ROOT / "config" / "auth_config.yaml"
_AUTH_STATE_KEY = "_traceact_authenticator"
_OPEN_REGISTRATION = object()


def _load_auth_config() -> dict:
    if _AUTH_CONFIG_PATH.is_file():
        with open(_AUTH_CONFIG_PATH, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    try:
        return dict(st.secrets.get("auth", {}))
    except Exception:
        return {}


def _save_auth_config(cfg: dict) -> bool:
    """Best-effort credential persistence (works locally; Cloud FS may be read-only)."""
    if not _AUTH_CONFIG_PATH.is_file():
        return False
    try:
        with open(_AUTH_CONFIG_PATH, "w", encoding="utf-8") as fh:
            yaml.safe_dump(cfg, fh, default_flow_style=False, allow_unicode=True)
        return True
    except OSError:
        return False


def _build_authenticator() -> stauth.Authenticate:
    cfg = _load_auth_config()
    cookie = cfg.get("cookie", {})
    # Dict-backed credentials (not a yaml path) so open registration is never
    # overridden by streamlit-authenticator's file-level pre-authorized list.
    return stauth.Authenticate(
        cfg.get("credentials", {}),
        cookie_name=cookie.get("name", "traceact_auth"),
        cookie_key=os.getenv(
            "AUTH_COOKIE_KEY",
            cookie.get("key", "traceact_dev_cookie_signing_key_change_me"),
        ),
        cookie_expiry_days=float(cookie.get("expiry_days", 30)),
        auto_hash=True,
    )


def _registration_preauthorized():
    """
    Control who may self-register.

    Default: open registration (``_OPEN_REGISTRATION`` sentinel).
    Set ``AUTH_INVITE_ONLY=true`` to restrict to emails in auth_config.yaml.
    """
    if os.getenv("AUTH_INVITE_ONLY", "").lower() not in ("1", "true", "yes"):
        return _OPEN_REGISTRATION
    cfg = _load_auth_config()
    emails = cfg.get("pre-authorized", {}).get("emails")
    if emails is None:
        emails = cfg.get("preauthorized", {}).get("emails")
    return list(emails or [])


def _register_user(authenticator: stauth.Authenticate, **kwargs):
    """
    Register via streamlit-authenticator without accidental invite-only gating.

    The upstream library treats any list (including from yaml) as invite-only.
    We route open registration through the controller with ``pre_authorized=None``
    and no config-file path attached to the credentials object.
    """
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


def _extract_live_credentials(authenticator: stauth.Authenticate) -> dict | None:
    """Read the mutable credential store from streamlit-authenticator (version-tolerant)."""
    controller = getattr(authenticator, "authentication_controller", None)
    if controller is None:
        return None
    if hasattr(controller, "credentials"):
        return controller.credentials
    model = getattr(controller, "authentication_model", None)
    if model is not None and hasattr(model, "credentials"):
        return model.credentials
    return None


def _persist_credentials_snapshot() -> None:
    """Best-effort yaml sync; never block registration if Cloud FS is read-only."""
    try:
        authenticator = _get_authenticator()
        credentials = _extract_live_credentials(authenticator)
        if not credentials:
            return
        cfg = _load_auth_config()
        cfg["credentials"] = credentials
        cfg.pop("preauthorized", None)
        _save_auth_config(cfg)
    except Exception:
        return


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


def _render_registration_form(authenticator: stauth.Authenticate) -> None:
    """Open-registration form that bypasses invite-only yaml defaults."""
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
        ensure_company_profile(registered_user, contact_email=registered_email)
        _persist_credentials_snapshot()
        st.success(
            f"Organisation registered for **{registered_name}**. "
            "Sign in on the **Sign In** tab with your new credentials."
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
            _render_registration_form(authenticator)

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
