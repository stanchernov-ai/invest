"""Board panelist roster — SSOT for voting member keys, display names, and avatars."""

from __future__ import annotations

# Voting panel (Round 1 + Round 2). Keys are stable pipeline identifiers.
PANELIST_KEYS = ("franklin", "darwin", "suntzu", "tesla", "pythagoras")

PANELIST_ROLES: dict[str, str] = {
    "franklin": "Benjamin Franklin",
    "darwin": "Charles Darwin",
    "suntzu": "Sun Tzu",
    "tesla": "Nikola Tesla",
    "pythagoras": "Pythagoras",
}

PANELIST_ARCHETYPES: dict[str, str] = {
    "franklin": "The Value Anchor",
    "darwin": "The Growth Narrator",
    "suntzu": "The Tape Reader",
    "tesla": "The Tech Visionary",
    "pythagoras": "The Pure Quant",
}

# Reuse existing blob portraits until persona-specific assets are uploaded.
PANELIST_AVATAR_URLS: dict[str, str] = {
    "franklin": "https://stboardroomprod.blob.core.windows.net/assets/buffett.jpg",
    "darwin": "https://stboardroomprod.blob.core.windows.net/assets/lynch.jpg",
    "suntzu": "https://stboardroomprod.blob.core.windows.net/assets/livermore.jpg",
    "tesla": "https://stboardroomprod.blob.core.windows.net/assets/huang.jpg",
    "pythagoras": "https://stboardroomprod.blob.core.windows.net/assets/simons.jpg",
}

# Backward compatibility for checkpoints / chairman JSON from prior roster.
LEGACY_AGENT_KEY_MAP: dict[str, str] = {
    "buffett": "franklin",
    "lynch": "darwin",
    "livermore": "suntzu",
    "huang": "tesla",
    "simons": "pythagoras",
}

LEGACY_DISPLAY_TO_KEY: dict[str, str] = {
    "Warren Buffett": "franklin",
    "Peter Lynch": "darwin",
    "Jesse Livermore": "suntzu",
    "Jensen Huang": "tesla",
    "Jim Simons": "pythagoras",
}


def normalize_panelist_key(agent_key: str) -> str:
    """Map legacy pipeline keys to current roster keys."""
    return LEGACY_AGENT_KEY_MAP.get(agent_key, agent_key)


def resolve_panelist_key(name_or_key: str) -> str | None:
    """Resolve display name or legacy key to a current panelist key."""
    if name_or_key in PANELIST_ROLES:
        return name_or_key
    if name_or_key in LEGACY_AGENT_KEY_MAP:
        return LEGACY_AGENT_KEY_MAP[name_or_key]
    legacy = LEGACY_DISPLAY_TO_KEY.get(name_or_key)
    if legacy:
        return legacy
    for key, role in PANELIST_ROLES.items():
        if role == name_or_key:
            return key
    return None

# Concentration audit (legacy Munger pass) — value, tech, growth lenses.
CONCENTRATION_AUDIT_KEYS = ("franklin", "tesla", "darwin")
