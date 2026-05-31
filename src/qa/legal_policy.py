"""Legal Counsel SaaS/commercial policy — briefing + codebase review boundaries."""

LEGAL_COUNSEL_SAAS_POLICY = """
[COMMERCIAL SaaS BOUNDARIES — Invest AI moving to multi-tenant product]:
You CAN mention public investors and quote them when done correctly. Stay out of the endorsement trap.

NOMINATIVE FAIR USE:
* Phrases like "a Mungeresque strategy" or "Lynch-style growth framing" are fine — describing a known style,
  NOT claiming the person built or endorses the app.
* Referring to public figures in commentary/analysis is permitted; implying partnership is not.

SHORT QUOTES:
* Pulling a brief sentence from a public speech, shareholder letter, or book is usually fair use for commentary
  or education — especially when attributed and not presented as today's live endorsement.

AVOID IMPLIED ENDORSEMENT (CRITICAL):
* Marketing, UI copy, agent output, and email HTML must NOT suggest Warren Buffett, Charlie Munger, Cathie Wood,
  Peter Lynch, or any living investor blessed, built, operates, or recommends Invest AI / this boardroom.
* If a reasonable user could believe the real investor is involved → CRITICAL.

RIGHT OF PUBLICITY:
* Dead historical personas used as AI agents (da Vinci, Marcus Aurelius, Hypatia, Sun Tzu, Nikola Tesla) are
  public-domain fictional voices in this product — OK as characters.
* Living or recently deceased people must NOT be used as core commercial mascots, product logos, or implied operators.

DO NOT FAKE QUOTES (CRITICAL):
* AI hallucinating a quote attributed to a real person → defamation / false light risk.
* Direct quotes must be plausibly from public record OR clearly framed as paraphrase/style
  ("in the Buffett tradition…"). Quotation marks around invented speech → CRITICAL.

COPYRIGHT & STYLE:
* Copyright protects specific text blocks, not speaking style or investing vocabulary.
* Industry terms (margin of safety, economic moat, compounding machine) are free to use.

THE LINE:
* Risk returns if mimicry becomes identity theft: trademarked catchphrases of living investors used as if they
  typed the update, or false impression the real person authors daily emails.
""".strip()

# Deterministic code/text scan — case-insensitive patterns → (category, severity, recommendation).
CODE_ENDORSEMENT_PATTERNS: list[tuple] = [
    (
        r"\b(?:warren\s+buffett|charlie\s+munger|cathie\s+wood|peter\s+lynch)\b[^.\n]{0,80}"
        r"\b(?:recommend|endorses?|approved|partners?\s+with|built\s+this|official)\b",
        "Implied Endorsement",
        "CRITICAL",
        "Remove language implying a living investor endorses or operates the product.",
    ),
    (
        r"\bofficial\s+(?:warren\s+buffett|buffett|munger|cathie\s+wood|lynch)\b",
        "Implied Endorsement",
        "CRITICAL",
        "Delete 'official [investor]' phrasing — nominative fair use does not cover false affiliation.",
    ),
]

# User-facing copy only — prompts may mention these terms when forbidding them.
CODE_MARKETING_PATTERNS: list[tuple] = [
    (
        r"\b(?:guaranteed|risk[- ]free)\s+(?:returns?|profits?|gains?)\b",
        "Securities Marketing",
        "CRITICAL",
        "Remove guaranteed-return or risk-free profit claims.",
    ),
]

USER_FACING_CODE_PATHS = frozenset({
    "src/output/reporting.py",
    "src/output/notifier.py",
    "src/output/briefing_style.py",
    "README.md",
})

BRIEFING_ENDORSEMENT_PATTERNS: list[tuple] = [
    (
        r"\b(?:warren\s+buffett|charlie\s+munger|cathie\s+wood)\s+(?:says?|said|recommends?|approves?)\b",
        "Implied Endorsement",
        "CRITICAL",
        "Briefing must not present living investors as live authors; paraphrase or attribute to public record with context.",
    ),
    (
        r"[\"\"][^\"\"]{10,200}[\"\"]\s*[-—]\s*(?:warren\s+buffett|charlie\s+munger|cathie\s+wood|peter\s+lynch)\b",
        "Fabricated Quote Risk",
        "WARNING",
        "Verify quoted text against public record; prefer paraphrase if uncertain.",
    ),
]

CODE_SCAN_REL_PATHS = (
    "src/core/agents.py",
    "src/core/investor_voice.py",
    "src/core/schemas.py",
    "src/output/reporting.py",
    "src/output/briefing_style.py",
    "src/output/notifier.py",
    "function_app.py",
    "README.md",
)
