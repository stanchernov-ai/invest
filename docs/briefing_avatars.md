# Board Panel Avatars — Stealth Wealth Art Direction

**Status:** Active  
**Last updated:** May 30, 2026  
**Code SSOT:** `src/core/board_roster.py` (`PANELIST_AVATAR_URLS`, `PANELIST_AVATAR_MATERIAL`)  
**Consumers:** `src/output/reporting.py` (SoTU + briefing HTML), Graphics Designer QA

---

## Design intent

Panel avatars are **architectural UI elements**, not decorative profile pictures. Generic AI generations collapse the premium feel. Busts read as framed portrait medallions — a gold ring around a portrait on a solid per-persona backdrop — sitting cleanly on the Obsidian briefing containers (`#121212` canvas, `#1e1e1e` cards) without glare in dark mode.

**Target audience:** Paying premium subscribers — the interface must project quiet authority and institutional wealth (**Stealth Wealth**).

---

## Global rendering rules

| Rule | Spec |
|------|------|
| **Lighting** | Cinematic single-source **overhead spotlight**. Deep shadow under brow and jaw — prevents blown highlights in dark mode. |
| **Background** | A **solid backdrop inside the circular crop is allowed** (e.g. per-persona studio color). Because the UI clips with `border-radius:50%`, only the inscribed disc is ever shown — corners are never visible, so rectangular/vignette artifacts outside the disc are irrelevant. Avoid blown-out white that breaks dark mode. |
| **Framing** | Shoulder-up bust, slightly off-center, facing ~15° toward center. Circular crop in UI (`border-radius: 50%`). |
| **Ring centering** | The gold frame ring **must be concentric with the square canvas** (equal margin all four sides). The UI clip is the circle *inscribed in the square* — an off-center ring leaves a dark crescent on one edge. **Never** correct this with `object-fit`/`object-position` (email-unsafe, hard Graphics-QA fail) — fix the asset. |
| **Delivery** | JPEG or WebP on Azure blob `stboardroomprod/assets/{key}.jpg` |

---

## Material palette by panelist

| Key | Persona | Archetype | Material | Rationale |
|-----|---------|-----------|----------|-----------|
| `hypatia` | Hypatia of Alexandria | Value Anchor | **White marble** (slightly weathered classical) | Mathematical truth, margin of safety |
| `davinci` | Leonardo da Vinci | Growth Narrator | **White marble** (rich classical) | Renaissance anatomy of scaling businesses |
| `suntzu` | Sun Tzu | Tape Reader | **Tarnished bronze** (heavy patina) | Enduring battlefield tactics |
| `tesla` | Nikola Tesla | Tech Visionary | **Black obsidian** (high polish, sharp facets) | Futuristic full-stack architecture |
| `aurelius` | Marcus Aurelius | Pure Quant | **Black obsidian** (sleek minimalist) | Cold, emotionless risk management |

Marble pair = value anchor + growth narrator. Obsidian pair = tech architecture + quantitative stoicism. Bronze = tactical tape reader — visually distinct from both.

---

## Blob asset map

| File | URL |
|------|-----|
| `hypatia.jpg` | `https://stboardroomprod.blob.core.windows.net/assets/hypatia.jpg` |
| `davinci.jpg` | `https://stboardroomprod.blob.core.windows.net/assets/davinci.jpg` |
| `suntzu.jpg` | `https://stboardroomprod.blob.core.windows.net/assets/suntzu.jpg` |
| `tesla.jpg` | `https://stboardroomprod.blob.core.windows.net/assets/tesla.jpg` |
| `aurelius.jpg` | `https://stboardroomprod.blob.core.windows.net/assets/aurelius.jpg` |

Until new assets land, legacy placeholders may 404 in QA — upload busts to these paths before the next prod run.

**Cache-busting:** the briefing appends `?v={AVATAR_VERSION}` (`src/core/board_roster.py`) to each URL. Email clients — especially Gmail's image proxy — cache by full URL, so re-uploading the *same* `{key}.png` leaves stale art in already-delivered inboxes. **After replacing blob content, bump `AVATAR_VERSION`** so clients re-fetch.

**Recentering tool:** new bust drops are rarely perfectly concentric. Run
`scripts/recenter_avatars.py --src <drop dir> --out assets/avatars --proof` to crop
each ring flush + centered, then eyeball `assets/avatars/_recenter_proof.png` (before/after
on real card colors) before uploading the `{key}.png` files to the blob.

---

## HTML usage

SoTU quote rows and Action Plan avatars reference `PANELIST_AVATAR_URLS` in `reporting.py`. Images use:

```html
<img src="..." style="width: 50px; height: 50px; border-radius: 50%; ..." alt="{role} avatar">
```

**Graphics QA:** Do not flag a bust's circular backdrop color as broken — solid per-persona backgrounds inside the `border-radius:50%` crop are intentional. Only flag if the blob image is genuinely broken/missing or a blown-out white block leaks visibly into the dark container.

---

## Related docs

| Doc | Section |
|-----|---------|
| [`briefing_style.md`](briefing_style.md) | Stealth Wealth palette, chart engine rules |
| [`agent_architecture.md`](agent_architecture.md) | Panel roster + debate flow |
