"""Email Access tab (2.3) — connect/disconnect Gmail & Outlook accounts via
OAuth, read-only mail scope. Tokens never touch the DB or a config file —
only a keychain reference is stored (see app/email_auth/oauth.py)."""

import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException
from msal import SerializableTokenCache
from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.auth.dependencies import require_auth
from app.config import Settings
from app.dependencies import get_settings, get_storage
from app.email_auth.oauth import build_google_flow, build_msal_app, delete_token, store_google_credentials, store_ms_cache
from app.models.db import EmailAccount, User
from app.models.schemas import EmailAccountOut, OAuthStatusOut
from app.storage.base import BaseStorageBackend

router = APIRouter(prefix="/api/v1/email-accounts", tags=["email-accounts"])

# connect/* and callback/* are plain browser-navigation redirects (an <a
# href>, then Google/Microsoft redirecting back) and can't carry a Bearer
# header, so they can't use the require_auth dependency the rest of the API
# uses — they're gated separately below instead of at router-include time.


@router.get("", response_model=list[EmailAccountOut])
def list_accounts(storage: BaseStorageBackend = Depends(get_storage), _user: User = Depends(require_auth)):
    with storage.session() as session:
        return list(session.execute(select(EmailAccount)).scalars())


@router.get("/oauth-status", response_model=OAuthStatusOut)
def oauth_status(settings: Settings = Depends(get_settings), _user: User = Depends(require_auth)):
    # Lets the Email Access page show setup steps *before* someone clicks
    # Connect and hits a raw JSON error page — connect_google/connect_ms
    # below already 400 on this, but that response never reaches the app's
    # own UI since those routes are plain browser-navigation redirects, not
    # fetch() calls the frontend could catch and render nicely.
    return OAuthStatusOut(
        google_configured=bool(settings.google_oauth_client_id),
        microsoft_configured=bool(settings.ms_oauth_client_id),
    )


@router.get("/connect/google")
def connect_google(settings: Settings = Depends(get_settings)):
    if not settings.google_oauth_client_id:
        raise HTTPException(400, "GOOGLE_OAUTH_CLIENT_ID not configured — see architecture/getting-started.md")
    redirect_uri = f"{settings.oauth_redirect_base_url}/api/v1/email-accounts/callback/google"
    flow = build_google_flow(settings.google_oauth_client_id, settings.google_oauth_client_secret, redirect_uri)
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    return RedirectResponse(auth_url)


@router.get("/callback/google")
def callback_google(
    request: Request,
    storage: BaseStorageBackend = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    redirect_uri = f"{settings.oauth_redirect_base_url}/api/v1/email-accounts/callback/google"
    flow = build_google_flow(settings.google_oauth_client_id, settings.google_oauth_client_secret, redirect_uri)
    flow.fetch_token(authorization_response=str(request.url))
    creds = flow.credentials

    account_id = str(uuid.uuid4())
    store_google_credentials(account_id, creds)

    profile_resp = httpx.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {creds.token}"},
        timeout=10.0,
    )
    email_address = profile_resp.json().get("email", "(unknown)") if profile_resp.is_success else "(unknown)"

    with storage.session() as session:
        account = EmailAccount(
            id=account_id,
            provider="gmail",
            email_address=email_address,
            keychain_ref=f"recruit-assistant-email:{account_id}",
        )
        session.add(account)
        session.commit()
    return RedirectResponse(f"{settings.frontend_base_url}/app/email-access?connected=gmail")


@router.get("/connect/microsoft")
def connect_microsoft(settings: Settings = Depends(get_settings)):
    if not settings.ms_oauth_client_id:
        raise HTTPException(400, "MS_OAUTH_CLIENT_ID not configured — see architecture/getting-started.md")
    app_client = build_msal_app(settings.ms_oauth_client_id, settings.ms_oauth_client_secret, settings.ms_oauth_tenant_id)
    redirect_uri = f"{settings.oauth_redirect_base_url}/api/v1/email-accounts/callback/microsoft"
    from app.email_auth.oauth import MS_SCOPES

    auth_url = app_client.get_authorization_request_url(MS_SCOPES, redirect_uri=redirect_uri)
    return RedirectResponse(auth_url)


@router.get("/callback/microsoft")
def callback_microsoft(
    code: str,
    storage: BaseStorageBackend = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    from app.email_auth.oauth import MS_SCOPES

    cache = SerializableTokenCache()
    app_client = build_msal_app(
        settings.ms_oauth_client_id, settings.ms_oauth_client_secret, settings.ms_oauth_tenant_id, token_cache=cache
    )
    redirect_uri = f"{settings.oauth_redirect_base_url}/api/v1/email-accounts/callback/microsoft"
    result = app_client.acquire_token_by_authorization_code(code, scopes=MS_SCOPES, redirect_uri=redirect_uri)
    if "access_token" not in result:
        raise HTTPException(400, f"Microsoft OAuth failed: {result.get('error_description')}")

    account_id = str(uuid.uuid4())
    store_ms_cache(account_id, cache)

    profile_resp = httpx.get(
        "https://graph.microsoft.com/v1.0/me",
        headers={"Authorization": f"Bearer {result['access_token']}"},
        timeout=10.0,
    )
    profile = profile_resp.json() if profile_resp.is_success else {}
    email_address = profile.get("mail") or profile.get("userPrincipalName") or "(unknown)"

    with storage.session() as session:
        account = EmailAccount(
            id=account_id,
            provider="outlook",
            email_address=email_address,
            keychain_ref=f"recruit-assistant-email:{account_id}",
        )
        session.add(account)
        session.commit()
    return RedirectResponse(f"{settings.frontend_base_url}/app/email-access?connected=outlook")


@router.delete("/{account_id}")
def disconnect_account(
    account_id: str, storage: BaseStorageBackend = Depends(get_storage), _user: User = Depends(require_auth)
):
    with storage.session() as session:
        account = session.get(EmailAccount, account_id)
        if not account:
            raise HTTPException(404, "Account not found")
        session.delete(account)
        session.commit()
    delete_token(account_id)
    return {"status": "disconnected"}
