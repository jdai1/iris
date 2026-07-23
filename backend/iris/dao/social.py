"""Persistence helpers for private profiles, personal websites, and friendships."""

from __future__ import annotations

import re

from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload

from iris.dao import db
from iris.dao.sources import get_or_create_source
from iris.models import Friendship, FriendshipStatus, User, UserProfile, UserWebsite
from iris.services.common.url_utils import is_valid_http_url, normalize_url


USERNAME_RE = re.compile(r"[^a-z0-9]+")


def normalize_username(value: str) -> str:
    username = USERNAME_RE.sub("-", value.strip().lower()).strip("-")
    if len(username) < 3:
        raise ValueError("Username must contain at least 3 letters or numbers")
    return username[:60].rstrip("-")


def get_or_create_profile(user: User) -> UserProfile:
    session = db.current_session()
    profile = session.scalar(
        select(UserProfile)
        .options(joinedload(UserProfile.websites).joinedload(UserWebsite.source))
        .where(UserProfile.user_id == user.id)
    )
    if profile is not None:
        return profile

    raw_base = user.display_name or user.email.partition("@")[0] or f"user-{user.id}"
    base = normalize_username(raw_base)
    username = base
    suffix = 2
    while session.scalar(select(UserProfile.id).where(UserProfile.username == username)) is not None:
        username = f"{base[: max(3, 60 - len(str(suffix)) - 1)]}-{suffix}"
        suffix += 1
    profile = UserProfile(user_id=user.id, username=username)
    session.add(profile)
    session.flush()
    return profile


def update_profile(
    user: User,
    *,
    username: str | None = None,
    bio: str | None = None,
    display_name: str | None = None,
    update_username: bool = False,
    update_bio: bool = False,
    update_display_name: bool = False,
) -> UserProfile:
    session = db.current_session()
    profile = get_or_create_profile(user)
    if update_username:
        normalized = normalize_username(username or "")
        existing = session.scalar(
            select(UserProfile).where(
                UserProfile.username == normalized,
                UserProfile.id != profile.id,
            )
        )
        if existing is not None:
            raise ValueError("Username is already in use")
        profile.username = normalized
    if update_bio:
        profile.bio = (bio or "").strip() or None
    if update_display_name:
        user.display_name = (display_name or "").strip() or None
    session.flush()
    return profile


def attach_website(user: User, *, url: str, label: str | None = None) -> UserWebsite:
    normalized = normalize_url(url)
    if not is_valid_http_url(normalized):
        raise ValueError("Website must be a valid HTTP or HTTPS URL")
    session = db.current_session()
    profile = get_or_create_profile(user)
    source = get_or_create_source(normalized)
    website = session.scalar(
        select(UserWebsite)
        .options(joinedload(UserWebsite.source))
        .where(UserWebsite.profile_id == profile.id, UserWebsite.source_id == source.id)
    )
    if website is not None:
        website.label = (label or "").strip() or website.label
        session.flush()
        return website
    website = UserWebsite(
        profile_id=profile.id,
        source_id=source.id,
        label=(label or "").strip() or None,
    )
    session.add(website)
    session.flush()
    return website


def remove_website(user: User, website_id: int) -> bool:
    session = db.current_session()
    profile = get_or_create_profile(user)
    website = session.scalar(
        select(UserWebsite).where(
            UserWebsite.id == website_id,
            UserWebsite.profile_id == profile.id,
        )
    )
    if website is None:
        return False
    session.delete(website)
    session.flush()
    return True


def pair_key(user_a_id: int, user_b_id: int) -> str:
    low, high = sorted((user_a_id, user_b_id))
    return f"{low}:{high}"


def get_friendship(user_a_id: int, user_b_id: int) -> Friendship | None:
    return db.current_session().scalar(
        select(Friendship).where(Friendship.pair_key == pair_key(user_a_id, user_b_id))
    )


def relationship_state(viewer: User, other: User) -> str:
    if viewer.id == other.id:
        return "self"
    friendship = get_friendship(viewer.id, other.id)
    if friendship is None:
        return "none"
    if friendship.status == FriendshipStatus.CONNECTED:
        return "connected"
    return "requested_outgoing" if friendship.requester_id == viewer.id else "requested_incoming"


def are_connected(user_a_id: int, user_b_id: int) -> bool:
    friendship = get_friendship(user_a_id, user_b_id)
    return friendship is not None and friendship.status == FriendshipStatus.CONNECTED


def request_friendship(requester: User, recipient: User) -> Friendship:
    if requester.id == recipient.id:
        raise ValueError("You cannot send a friend request to yourself")
    session = db.current_session()
    existing = get_friendship(requester.id, recipient.id)
    if existing is not None:
        if existing.status == FriendshipStatus.CONNECTED:
            raise ValueError("You are already friends")
        raise ValueError("A friend request already exists")
    friendship = Friendship(
        requester_id=requester.id,
        recipient_id=recipient.id,
        pair_key=pair_key(requester.id, recipient.id),
        status=FriendshipStatus.REQUESTED,
    )
    session.add(friendship)
    session.flush()
    return friendship


def accept_friendship(user: User, friendship_id: int) -> Friendship | None:
    session = db.current_session()
    friendship = session.get(Friendship, friendship_id)
    if (
        friendship is None
        or friendship.recipient_id != user.id
        or friendship.status != FriendshipStatus.REQUESTED
    ):
        return None
    friendship.status = FriendshipStatus.CONNECTED
    session.flush()
    return friendship


def remove_friendship(user: User, friendship_id: int, *, status: FriendshipStatus) -> bool:
    session = db.current_session()
    friendship = session.get(Friendship, friendship_id)
    if (
        friendship is None
        or friendship.status != status
        or user.id not in {friendship.requester_id, friendship.recipient_id}
    ):
        return False
    session.delete(friendship)
    session.flush()
    return True


def connected_friendships(user: User) -> list[Friendship]:
    return list(
        db.current_session()
        .execute(
            select(Friendship)
            .where(
                Friendship.status == FriendshipStatus.CONNECTED,
                or_(Friendship.requester_id == user.id, Friendship.recipient_id == user.id),
            )
            .order_by(Friendship.updated_at.desc(), Friendship.id.desc())
        )
        .scalars()
    )


def requested_friendships(user: User, *, incoming: bool) -> list[Friendship]:
    field = Friendship.recipient_id if incoming else Friendship.requester_id
    return list(
        db.current_session()
        .execute(
            select(Friendship)
            .where(
                Friendship.status == FriendshipStatus.REQUESTED,
                field == user.id,
            )
            .order_by(Friendship.created_at.desc(), Friendship.id.desc())
        )
        .scalars()
    )


def other_user(friendship: Friendship, user: User) -> User:
    other_id = friendship.recipient_id if friendship.requester_id == user.id else friendship.requester_id
    other = db.current_session().get(User, other_id)
    if other is None:
        raise RuntimeError("Friendship references a missing user")
    return other


def search_people(user: User, *, query: str, limit: int = 20) -> list[User]:
    normalized = " ".join(query.split()).lower()
    if not normalized:
        return []
    pattern = f"%{normalized}%"
    return list(
        db.current_session()
        .execute(
            select(User)
            .join(UserProfile, UserProfile.user_id == User.id)
            .where(
                User.id != user.id,
                or_(
                    UserProfile.username.ilike(pattern),
                    User.display_name.ilike(pattern),
                ),
            )
            .order_by(User.display_name.asc(), UserProfile.username.asc())
            .limit(max(1, min(limit, 50)))
        )
        .scalars()
    )


def get_visible_profile(viewer: User, username: str) -> UserProfile | None:
    profile = db.current_session().scalar(
        select(UserProfile)
        .options(
            joinedload(UserProfile.user),
            joinedload(UserProfile.websites).joinedload(UserWebsite.source),
        )
        .where(UserProfile.username == username.lower())
    )
    if profile is None:
        return None
    if profile.user_id == viewer.id or are_connected(viewer.id, profile.user_id):
        return profile
    return None
