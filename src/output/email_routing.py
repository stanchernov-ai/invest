"""Per-user email routing for pipeline deliverables."""
from __future__ import annotations

import os

OWNER_SLUGS = frozenset({"stan"})


def ops_recipient() -> str | None:
    """Owner inbox for QA, legal, validation, and system alerts."""
    return os.getenv("STAN_PERSONAL_EMAIL")


def receives_ops_email(slug: str | None) -> bool:
    return (slug or "stan") in OWNER_SLUGS


async def resolve_delivery_context(user_id: str) -> dict:
    """Return slug, briefing email, and whether ops/validation emails should send."""
    slug = "stan"
    email = ops_recipient()
    if not user_id or user_id == "stan":
        return {
            "slug": slug,
            "email": email,
            "receives_ops_email": True,
        }
    if len(user_id) != 36:
        return {
            "slug": None,
            "email": email,
            "receives_ops_email": True,
        }
    from src.data.db import fetch_row

    row = await fetch_row(
        "SELECT slug, email FROM users WHERE id = $1::uuid",
        user_id,
    )
    if not row:
        return {
            "slug": None,
            "email": email,
            "receives_ops_email": True,
        }
    slug = row["slug"]
    return {
        "slug": slug,
        "email": row.get("email") or email,
        "receives_ops_email": receives_ops_email(slug),
    }


def briefing_recipient(ctx: dict) -> str | None:
    return ctx.get("email") or ops_recipient()
