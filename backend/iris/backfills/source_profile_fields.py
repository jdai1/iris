"""Create and backfill flattened source profile analysis fields."""

from __future__ import annotations

import json

from sqlalchemy import inspect, text

from iris.dao import db


PROFILE_FIELD_TYPES = {
    "bio": "text",
    "themes": "json",
    "writing_style": "json",
    "strong_takes": "json",
    "public_links": "json",
    "public_contact": "json",
    "caveats": "json",
}


def migrate_source_profile_fields() -> int:
    """Create top-level profile-analysis columns and backfill them from legacy payload JSON."""
    session = db.current_session()
    session.flush()
    _ensure_columns()
    columns = {column["name"] for column in inspect(session.connection()).get_columns("source_profile_analyses")}
    if "payload" not in columns:
        return 0

    rows = session.execute(
        text(
            "select id, payload from source_profile_analyses "
            "where payload is not null and (bio is null and themes is null and writing_style is null)"
        )
    ).mappings()
    changed = 0
    for row in rows:
        try:
            payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        session.execute(
            text(
                "update source_profile_analyses set "
                "bio = :bio, themes = :themes, writing_style = :writing_style, "
                "strong_takes = :strong_takes, public_links = :public_links, "
                "public_contact = :public_contact, caveats = :caveats "
                "where id = :id"
            ),
            {
                "id": row["id"],
                "bio": payload.get("bio"),
                "themes": _json_or_none(payload.get("themes")),
                "writing_style": _json_or_none(payload.get("writing_style")),
                "strong_takes": _json_or_none(payload.get("strong_takes")),
                "public_links": _json_or_none(payload.get("public_links")),
                "public_contact": _json_or_none(payload.get("public_contact")),
                "caveats": _json_or_none(payload.get("caveats")),
            },
        )
        changed += 1
    return changed


def _ensure_columns() -> None:
    session = db.current_session()
    connection = session.connection()
    columns = {column["name"] for column in inspect(connection).get_columns("source_profile_analyses")}
    for name, kind in PROFILE_FIELD_TYPES.items():
        if name in columns:
            continue
        session.execute(text(f"alter table source_profile_analyses add column {name} {_column_type(connection.dialect.name, kind)}"))


def _column_type(dialect_name: str, kind: str) -> str:
    if kind == "text":
        return "text"
    return "json" if dialect_name == "postgresql" else "json"


def _json_or_none(value: object) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def main() -> int:
    with db.session_scope():
        print(f"backfilled={migrate_source_profile_fields()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
