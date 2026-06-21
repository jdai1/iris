from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

import firebase_admin
from fastapi import HTTPException
from firebase_admin import auth, credentials

from iris.services.common.config import (
    FIREBASE_PROJECT_ID,
    FIREBASE_SERVICE_ACCOUNT_FILE,
    FIREBASE_SERVICE_ACCOUNT_JSON,
)


@dataclass(frozen=True)
class FirebaseIdentity:
    uid: str
    email: str | None = None
    display_name: str | None = None
    photo_url: str | None = None


@lru_cache(maxsize=1)
def _firebase_app():
    options = {"projectId": FIREBASE_PROJECT_ID} if FIREBASE_PROJECT_ID else None
    if FIREBASE_SERVICE_ACCOUNT_JSON:
        cred = credentials.Certificate(json.loads(FIREBASE_SERVICE_ACCOUNT_JSON))
        return firebase_admin.initialize_app(cred, options)
    if FIREBASE_SERVICE_ACCOUNT_FILE:
        cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_FILE)
        return firebase_admin.initialize_app(cred, options)
    return firebase_admin.initialize_app(options=options)


def verify_firebase_token(token: str) -> FirebaseIdentity:
    try:
        decoded = auth.verify_id_token(token, app=_firebase_app())
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid Firebase token") from exc
    uid = decoded.get("uid") or decoded.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="Firebase token is missing uid")
    return FirebaseIdentity(
        uid=uid,
        email=decoded.get("email"),
        display_name=decoded.get("name"),
        photo_url=decoded.get("picture"),
    )
