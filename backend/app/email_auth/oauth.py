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
"""

import keyring
from google_auth_oauthlib.flow import Flow
from msal import ConfidentialClientApplication

KEYCHAIN_SERVICE = "recruit-assistant-email"

GOOGLE_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
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
    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    return Flow.from_client_config(client_config, scopes=GOOGLE_SCOPES, redirect_uri=redirect_uri)


def build_msal_app(client_id: str, client_secret: str, tenant_id: str) -> ConfidentialClientApplication:
    return ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
    )
