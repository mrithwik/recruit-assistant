"""
OAuth connect flow for Gmail (Google) and Outlook (Microsoft Graph), read-only
mail scopes only. Tokens are stored via the OS keychain (`keyring`) — never in
the SQLite DB or a config file — the EmailAccount row only holds a reference
key (`keychain_ref`), never the token itself. This is the safeguard called out
in requirement 2.3.

Setup note: using this requires registering an OAuth app with Google Cloud
Console / Azure AD and putting the client id/secret in .env — see
architecture/getting-started.md. Until that's done, /scan/email-accounts
returns a clear "not configured" error rather than silently failing.

Token refresh: a Google access token expires in ~1 hour. Rather than storing
a raw {access_token, refresh_token} pair and letting a scan started after
expiry just fail with 401s, the full credential material needed to refresh
is what's actually persisted (see store_google_credentials /
load_google_credentials, and store_ms_cache / load_ms_cache for the MSAL
equivalent), and get_valid_access_token() refreshes before handing back a
token whenever the SDK says it's needed.
"""

import json
import os
from datetime import datetime

import keyring
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials as GoogleCredentials
from google_auth_oauthlib.flow import Flow
from msal import ConfidentialClientApplication, SerializableTokenCache

KEYCHAIN_SERVICE = "recruit-assistant-email"

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.insert",
    "https://www.googleapis.com/auth/userinfo.email",
]
MS_SCOPES = ["Mail.Read"]


def store_token(account_id: str, token_json: str) -> str:
    keychain_ref = f"{KEYCHAIN_SERVICE}:{account_id}"
    keyring.set_password(KEYCHAIN_SERVICE, account_id, token_json)
    return keychain_ref


def load_token(account_id: str) -> str | None:
    return keyring.get_password(KEYCHAIN_SERVICE, account_id)


def delete_token(account_id: str) -> None:
    try:
        keyring.delete_password(KEYCHAIN_SERVICE, account_id)
    except keyring.errors.PasswordDeleteError:
        pass


def build_google_flow(client_id: str, client_secret: str, redirect_uri: str) -> Flow:
    # oauthlib refuses to parse a plain-http authorization response by
    # default (InsecureTransportError). Google itself allows http://localhost
    # redirect URIs for local/desktop testing, so relax the check only for
    # that exact case — never for a real https deployment.
    if redirect_uri.startswith("http://localhost") or redirect_uri.startswith("http://127.0.0.1"):
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

    # Google always adds the "openid" scope to the token response once
    # userinfo.email is requested, even though we didn't ask for it
    # explicitly. oauthlib treats any scope drift as a hard error unless
    # told to relax — this is expected Google behavior, not a real mismatch.
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    # PKCE is auto-enabled by default, but the code_verifier it generates
    # lives only on this Flow instance in memory — connect_google and
    # callback_google each build a fresh Flow, so a verifier from the
    # authorize step never reaches the token-exchange step (would need a
    # server-side session to bridge them). This is a confidential client
    # (has a client_secret), so PKCE isn't required; disable it instead.
    return Flow.from_client_config(
        client_config,
        scopes=GOOGLE_SCOPES,
        redirect_uri=redirect_uri,
        autogenerate_code_verifier=False,
    )


def store_google_credentials(account_id: str, creds: GoogleCredentials) -> str:
    """Persists everything Credentials.refresh() needs later — a bare
    {access_token, refresh_token} dict (the previous shape) isn't enough,
    since refreshing also needs the token endpoint + client id/secret, and
    `expiry` is what creds.expired actually checks: without persisting it, a
    freshly-reloaded Credentials object always looks non-expired (expiry
    defaults to None) and refresh() would never fire."""
    payload = {
        "provider": "google",
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }
    return store_token(account_id, json.dumps(payload))


def load_google_credentials(account_id: str) -> GoogleCredentials | None:
    raw = load_token(account_id)
    if not raw:
        return None
    data = json.loads(raw)
    creds = GoogleCredentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes"),
    )
    if data.get("expiry"):
        creds.expiry = datetime.fromisoformat(data["expiry"])
    return creds


def build_msal_app(
    client_id: str, client_secret: str, tenant_id: str, token_cache: SerializableTokenCache | None = None
) -> ConfidentialClientApplication:
    return ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        token_cache=token_cache,
    )


def store_ms_cache(account_id: str, cache: SerializableTokenCache) -> str:
    return store_token(account_id, json.dumps({"provider": "outlook", "cache": cache.serialize()}))


def load_ms_cache(account_id: str) -> SerializableTokenCache | None:
    raw = load_token(account_id)
    if not raw:
        return None
    cache = SerializableTokenCache()
    cache.deserialize(json.loads(raw)["cache"])
    return cache


def get_valid_access_token(
    account_id: str,
    provider: str,
    ms_client_id: str = "",
    ms_client_secret: str = "",
    ms_tenant_id: str = "common",
) -> str | None:
    """Returns a live access token for this account, refreshing first if the
    stored one has expired — the call site (routes/scan.py) no longer reads
    a possibly-stale access_token straight out of the keychain blob."""
    if provider == "gmail":
        creds = load_google_credentials(account_id)
        if creds is None:
            return None
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleAuthRequest())
            store_google_credentials(account_id, creds)
        return creds.token

    if provider == "outlook":
        cache = load_ms_cache(account_id)
        if cache is None:
            return None
        app_client = build_msal_app(ms_client_id, ms_client_secret, ms_tenant_id, token_cache=cache)
        accounts = app_client.get_accounts()
        if not accounts:
            return None
        # acquire_token_silent refreshes against the cache's refresh token
        # internally if the cached access token is expired — this is the
        # entire point of using MSAL's own cache instead of a raw dict.
        result = app_client.acquire_token_silent(MS_SCOPES, account=accounts[0])
        if cache.has_state_changed:
            store_ms_cache(account_id, cache)
        if not result or "access_token" not in result:
            return None
        return result["access_token"]

    return None
