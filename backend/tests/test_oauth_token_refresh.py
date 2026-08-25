"""get_valid_access_token() is what fixed "a real Gmail scan just starts
failing with 401s after an hour" — Google access tokens expire in ~1hr and
the previous code read a raw, possibly-stale access_token straight out of
the keychain blob with no refresh path at all. These tests fake the OS
keychain (never touch the real one) and stub the SDK refresh calls (never
hit the network) to confirm the orchestration: expired -> refresh -> token
returned -> refreshed credential re-persisted."""

from datetime import datetime, timedelta

import pytest
from google.oauth2.credentials import Credentials as GoogleCredentials
from msal import SerializableTokenCache

from app.email_auth import oauth


@pytest.fixture
def fake_keychain(monkeypatch):
    store: dict[str, str] = {}
    monkeypatch.setattr(oauth.keyring, "set_password", lambda service, account, value: store.__setitem__(account, value))
    monkeypatch.setattr(oauth.keyring, "get_password", lambda service, account: store.get(account))
    return store


def test_expired_google_token_is_refreshed_and_repersisted(fake_keychain, monkeypatch):
    account_id = "acct-1"
    creds = GoogleCredentials(
        token="stale-token",
        refresh_token="a-refresh-token",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="client-id",
        client_secret="client-secret",
        scopes=oauth.GOOGLE_SCOPES,
        expiry=datetime.utcnow() - timedelta(hours=2),  # already expired
    )
    oauth.store_google_credentials(account_id, creds)

    def fake_refresh(self, request):
        self.token = "fresh-token"
        self.expiry = datetime.utcnow() + timedelta(hours=1)

    monkeypatch.setattr(GoogleCredentials, "refresh", fake_refresh)

    token = oauth.get_valid_access_token(account_id, "gmail")

    assert token == "fresh-token"
    # re-persisted: loading again should reflect the refreshed token, not the stale one
    reloaded = oauth.load_google_credentials(account_id)
    assert reloaded.token == "fresh-token"


def test_valid_google_token_is_not_refreshed(fake_keychain, monkeypatch):
    account_id = "acct-2"
    creds = GoogleCredentials(
        token="still-good",
        refresh_token="a-refresh-token",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="client-id",
        client_secret="client-secret",
        scopes=oauth.GOOGLE_SCOPES,
        expiry=datetime.utcnow() + timedelta(hours=1),  # not expired
    )
    oauth.store_google_credentials(account_id, creds)

    def fail_if_called(self, request):
        raise AssertionError("refresh() should not be called for a non-expired token")

    monkeypatch.setattr(GoogleCredentials, "refresh", fail_if_called)

    token = oauth.get_valid_access_token(account_id, "gmail")
    assert token == "still-good"


def test_missing_account_returns_none(fake_keychain):
    assert oauth.get_valid_access_token("no-such-account", "gmail") is None


def test_outlook_uses_msal_acquire_token_silent(fake_keychain, monkeypatch):
    account_id = "acct-outlook"
    cache = SerializableTokenCache()
    oauth.store_ms_cache(account_id, cache)

    fake_account = {"username": "user@example.com"}

    class FakeApp:
        def __init__(self, *a, **kw):
            self.token_cache = kw.get("token_cache")

        def get_accounts(self):
            return [fake_account]

        def acquire_token_silent(self, scopes, account):
            return {"access_token": "outlook-fresh-token"}

    monkeypatch.setattr(oauth, "ConfidentialClientApplication", FakeApp)

    token = oauth.get_valid_access_token(account_id, "outlook", ms_client_id="id", ms_client_secret="secret")
    assert token == "outlook-fresh-token"
