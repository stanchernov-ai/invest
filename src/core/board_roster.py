"""Board panelist roster — SSOT for voting member keys, display names, and avatars."""

from __future__ import annotations

import re

ASSET_BASE = "https://stboardroomprod.blob.core.windows.net/assets"

# Voting panel (Round 1 + Round 2). Keys are stable pipeline identifiers.
PANELIST_KEYS = ("hypatia", "davinci", "suntzu", "tesla", "aurelius")

PANELIST_ROLES: dict[str, str] = {
    "hypatia": "Hypatia of Alexandria",
    "davinci": "Leonardo da Vinci",
    "suntzu": "Sun Tzu",
    "tesla": "Nikola Tesla",
    "aurelius": "Marcus Aurelius",
}

PANELIST_ARCHETYPES: dict[str, str] = {
    "hypatia": "The Value Anchor",
    "davinci": "The Growth Narrator",
    "suntzu": "The Tape Reader",
    "tesla": "The Tech Visionary",
    "aurelius": "The Pure Quant",
}

# Stealth Wealth bust avatars — see docs/briefing_avatars.md for art direction.
PANELIST_AVATAR_URLS: dict[str, str] = {
    "hypatia": f"{ASSET_BASE}/hypatia.png",
    "davinci": f"{ASSET_BASE}/davinci.png",
    "suntzu": f"{ASSET_BASE}/suntzu.png",
    "tesla": f"{ASSET_BASE}/tesla.png",
    "aurelius": f"{ASSET_BASE}/aurelius.png",
}

PANELIST_AVATAR_MATERIAL: dict[str, str] = {
    "hypatia": "weathered white marble",
    "davinci": "rich white marble",
    "suntzu": "tarnished bronze",
    "tesla": "black obsidian",
    "aurelius": "black obsidian",
}

# Backward compatibility for checkpoints / chairman JSON from prior rosters.
LEGACY_AGENT_KEY_MAP: dict[str, str] = {
    "buffett": "hypatia",
    "lynch": "davinci",
    "livermore": "suntzu",
    "huang": "tesla",
    "simons": "aurelius",
    "franklin": "hypatia",
    "darwin": "davinci",
    "pythagoras": "aurelius",
    "aristotle": "hypatia",
}

LEGACY_DISPLAY_TO_KEY: dict[str, str] = {
    "Warren Buffett": "hypatia",
    "Peter Lynch": "davinci",
    "Jesse Livermore": "suntzu",
    "Jensen Huang": "tesla",
    "Jim Simons": "aurelius",
    "Benjamin Franklin": "hypatia",
    "Charles Darwin": "davinci",
    "Pythagoras": "aurelius",
    "Aristotle": "hypatia",
    "Hypatia of Alexandria": "hypatia",
    "Leonardo da Vinci": "davinci",
    "Sun Tzu": "suntzu",
    "Nikola Tesla": "tesla",
    "Marcus Aurelius": "aurelius",
}


def normalize_panelist_key(agent_key: str) -> str:
    """Map legacy pipeline keys to current roster keys."""
    return LEGACY_AGENT_KEY_MAP.get(agent_key, agent_key)


def resolve_panelist_key(name_or_key: str) -> str | None:
    """Resolve display name or legacy key to a current panelist key."""
    if name_or_key in PANELIST_ROLES:
        return name_or_key
    normalized = normalize_panelist_key(name_or_key)
    if normalized in PANELIST_ROLES:
        return normalized
    legacy = LEGACY_DISPLAY_TO_KEY.get(name_or_key)
    if legacy:
        return legacy
    for key, role in PANELIST_ROLES.items():
        if role == name_or_key:
            return key
    return None


# Investor-facing short names when panelists refer to each other in debate dialogue.
PANELIST_SHORT_NAMES: dict[str, str] = {
    "hypatia": "Hypatia",
    "davinci": "Leonardo",
    "suntzu": "Sun Tzu",
    "tesla": "Nikola",
    "aurelius": "Marcus",
}


def panelist_short_name(panelist_key: str) -> str:
    """First-name (or familiar) label for cross-references in debate prose."""
    key = resolve_panelist_key(panelist_key) or panelist_key
    return PANELIST_SHORT_NAMES.get(key, PANELIST_ROLES.get(key, panelist_key).split()[0])


def shorten_panelist_references(text: str) -> str:
    """Replace full panelist names with short names in debate and SoTU quote bodies."""
    if not text:
        return text
    replacements: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key in PANELIST_KEYS:
        role = PANELIST_ROLES[key]
        short = panelist_short_name(key)
        if role != short and role.lower() not in seen:
            replacements.append((role, short))
            seen.add(role.lower())
    for legacy, key in LEGACY_DISPLAY_TO_KEY.items():
        short = panelist_short_name(key)
        if legacy != short and legacy.lower() not in seen:
            replacements.append((legacy, short))
            seen.add(legacy.lower())
    replacements.sort(key=lambda pair: len(pair[0]), reverse=True)
    result = text
    for full, short in replacements:
        result = re.sub(re.escape(full), short, result, flags=re.IGNORECASE)
    return result


# Concentration audit (legacy Munger pass) — value, tech, growth lenses.
CONCENTRATION_AUDIT_KEYS = ("hypatia", "tesla", "davinci")
