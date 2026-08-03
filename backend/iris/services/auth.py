from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass
from functools import lru_cache

import firebase_admin
from fastapi import HTTPException
from firebase_admin import auth, credentials
from google.auth.exceptions import DefaultCredentialsError

from iris.services.common.config import (
    FIREBASE_HTTP_TIMEOUT_SECONDS,
    FIREBASE_PROJECT_ID,
    FIREBASE_SERVICE_ACCOUNT_FILE,
    FIREBASE_SERVICE_ACCOUNT_JSON,
    RAILWAY_SERVICE_ID,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FirebaseIdentity:
    uid: str
    email: str | None = None
    display_name: str | None = None
    photo_url: str | None = None


@lru_cache(maxsize=1)
def _firebase_app():
    options = {"httpTimeout": FIREBASE_HTTP_TIMEOUT_SECONDS}
    if FIREBASE_PROJECT_ID:
        options["projectId"] = FIREBASE_PROJECT_ID
    if FIREBASE_SERVICE_ACCOUNT_JSON:
        cred = credentials.Certificate(json.loads(FIREBASE_SERVICE_ACCOUNT_JSON))
        return firebase_admin.initialize_app(cred, options)
    if FIREBASE_SERVICE_ACCOUNT_FILE:
        cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_FILE)
        return firebase_admin.initialize_app(cred, options)
    if RAILWAY_SERVICE_ID:
        raise DefaultCredentialsError(
            "FIREBASE_SERVICE_ACCOUNT_JSON or FIREBASE_SERVICE_ACCOUNT_FILE is required on Railway"
        )
    return firebase_admin.initialize_app(options=options)


def verify_firebase_token(token: str) -> FirebaseIdentity:
    try:
        decoded = auth.verify_id_token(token, app=_firebase_app())
    except DefaultCredentialsError as exc:
        logger.exception("Firebase application credentials are unavailable")
        raise HTTPException(
            status_code=503,
            detail="Firebase authentication is temporarily unavailable",
        ) from exc
    except auth.CertificateFetchError as exc:
        logger.exception("Firebase signing certificate fetch failed")
        raise HTTPException(
            status_code=503,
            detail="Firebase authentication is temporarily unavailable",
        ) from exc
    except (auth.InvalidIdTokenError, ValueError) as exc:
        logger.info("Firebase rejected an invalid ID token: %s", type(exc).__name__)
        raise HTTPException(status_code=401, detail="Invalid Firebase token") from exc
    except Exception as exc:
        logger.exception("Unexpected Firebase token verification failure")
        raise HTTPException(
            status_code=503,
            detail="Firebase authentication is temporarily unavailable",
        ) from exc
    uid = decoded.get("uid") or decoded.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="Firebase token is missing uid")
    return FirebaseIdentity(
        uid=uid,
        email=decoded.get("email"),
        display_name=decoded.get("name"),
        photo_url=decoded.get("picture"),
    )


def warm_firebase_token_verifier() -> None:
    """Fetch and cache Firebase signing certificates before serving requests."""
    if not (FIREBASE_PROJECT_ID or FIREBASE_SERVICE_ACCOUNT_FILE or FIREBASE_SERVICE_ACCOUNT_JSON):
        return

    try:
        app = _firebase_app()
    except DefaultCredentialsError:
        logger.exception("Firebase application credentials are unavailable during warmup")
        return

    project_id = app.project_id
    if not project_id:
        return

    now = int(time.time())
    header = {"alg": "RS256", "kid": "iris-startup-warmup", "typ": "JWT"}
    payload = {
        "aud": project_id,
        "exp": now + 60,
        "iat": now,
        "iss": f"https://securetoken.google.com/{project_id}",
        "sub": "iris-startup-warmup",
    }
    token = ".".join(
        [
            _base64url_json(header),
            _base64url_json(payload),
            "c3RhcnR1cA",
        ]
    )
    try:
        # This intentionally fails signature validation after the Admin SDK has
        # populated its shared cache of Google's Firebase signing certificates.
        auth.verify_id_token(token, app=app)
    except DefaultCredentialsError:
        logger.exception("Firebase application credentials are unavailable during warmup")
    except auth.CertificateFetchError:
        logger.exception("Firebase signing certificate warmup failed")
    except auth.InvalidIdTokenError:
        logger.info("Firebase token verifier certificate cache is warm")
    except Exception:
        logger.exception("Unexpected Firebase token verifier warmup failure")


def _base64url_json(value: dict[str, object]) -> str:
    encoded = json.dumps(value, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).rstrip(b"=").decode("ascii")
