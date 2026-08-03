from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from firebase_admin import auth
from google.auth.exceptions import DefaultCredentialsError

from iris.services import auth as auth_service


def _raise(error: Exception):
    def fail(*_args, **_kwargs):
        raise error

    return fail


def test_firebase_http_timeout_is_bounded(monkeypatch):
    initialized = {}
    monkeypatch.setattr(auth_service, "FIREBASE_PROJECT_ID", "try-iris")
    monkeypatch.setattr(auth_service, "FIREBASE_SERVICE_ACCOUNT_FILE", None)
    monkeypatch.setattr(auth_service, "FIREBASE_SERVICE_ACCOUNT_JSON", None)
    monkeypatch.setattr(auth_service, "FIREBASE_HTTP_TIMEOUT_SECONDS", 10.0)
    monkeypatch.setattr(auth_service, "RAILWAY_SERVICE_ID", None)
    monkeypatch.setattr(
        auth_service.firebase_admin,
        "initialize_app",
        lambda *, options: initialized.update(options=options) or SimpleNamespace(project_id="try-iris"),
    )
    auth_service._firebase_app.cache_clear()

    try:
        auth_service._firebase_app()
    finally:
        auth_service._firebase_app.cache_clear()

    assert initialized["options"] == {"projectId": "try-iris", "httpTimeout": 10.0}


def test_railway_requires_explicit_firebase_credentials(monkeypatch):
    monkeypatch.setattr(auth_service, "FIREBASE_PROJECT_ID", "try-iris")
    monkeypatch.setattr(auth_service, "FIREBASE_SERVICE_ACCOUNT_FILE", None)
    monkeypatch.setattr(auth_service, "FIREBASE_SERVICE_ACCOUNT_JSON", None)
    monkeypatch.setattr(auth_service, "RAILWAY_SERVICE_ID", "railway-service")
    auth_service._firebase_app.cache_clear()

    try:
        with pytest.raises(DefaultCredentialsError, match="required on Railway"):
            auth_service._firebase_app()
    finally:
        auth_service._firebase_app.cache_clear()


def test_invalid_firebase_token_stays_unauthorized(monkeypatch):
    monkeypatch.setattr(
        auth_service.auth,
        "verify_id_token",
        _raise(auth.InvalidIdTokenError("bad token")),
    )

    with pytest.raises(HTTPException) as raised:
        auth_service.verify_firebase_token("token")

    assert raised.value.status_code == 401
    assert raised.value.detail == "Invalid Firebase token"


def test_missing_firebase_credentials_is_service_unavailable(monkeypatch, caplog):
    monkeypatch.setattr(
        auth_service.auth,
        "verify_id_token",
        _raise(DefaultCredentialsError("missing credentials")),
    )

    with pytest.raises(HTTPException) as raised:
        auth_service.verify_firebase_token("token")

    assert raised.value.status_code == 503
    assert raised.value.detail == "Firebase authentication is temporarily unavailable"
    assert "Firebase application credentials are unavailable" in caplog.text


def test_certificate_fetch_failure_is_service_unavailable(monkeypatch, caplog):
    monkeypatch.setattr(
        auth_service.auth,
        "verify_id_token",
        _raise(auth.CertificateFetchError("certificate timeout", TimeoutError("timed out"))),
    )

    with pytest.raises(HTTPException) as raised:
        auth_service.verify_firebase_token("token")

    assert raised.value.status_code == 503
    assert raised.value.detail == "Firebase authentication is temporarily unavailable"
    assert "Firebase signing certificate fetch failed" in caplog.text


def test_unexpected_verification_failure_is_service_unavailable(monkeypatch, caplog):
    monkeypatch.setattr(
        auth_service.auth,
        "verify_id_token",
        _raise(RuntimeError("unexpected")),
    )

    with pytest.raises(HTTPException) as raised:
        auth_service.verify_firebase_token("token")

    assert raised.value.status_code == 503
    assert raised.value.detail == "Firebase authentication is temporarily unavailable"
    assert "Unexpected Firebase token verification failure" in caplog.text


def test_warmup_does_not_report_certificate_fetch_failure_as_success(monkeypatch, caplog):
    monkeypatch.setattr(auth_service, "FIREBASE_PROJECT_ID", "try-iris")
    monkeypatch.setattr(auth_service, "_firebase_app", lambda: SimpleNamespace(project_id="try-iris"))
    monkeypatch.setattr(
        auth_service.auth,
        "verify_id_token",
        _raise(auth.CertificateFetchError("certificate timeout", TimeoutError("timed out"))),
    )

    auth_service.warm_firebase_token_verifier()

    assert "Firebase signing certificate warmup failed" in caplog.text
    assert "certificate cache is warm" not in caplog.text


def test_warmup_handles_missing_credentials(monkeypatch, caplog):
    monkeypatch.setattr(auth_service, "FIREBASE_PROJECT_ID", "try-iris")
    monkeypatch.setattr(auth_service, "_firebase_app", _raise(DefaultCredentialsError("missing credentials")))

    auth_service.warm_firebase_token_verifier()

    assert "Firebase application credentials are unavailable during warmup" in caplog.text
