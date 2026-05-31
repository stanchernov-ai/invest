# Documentation hygiene (ongoing process)

**Status:** Active  
**SSOT for:** how to keep `action_tracker.md` lean and docs accurate over time.

---

## Roles (what belongs where)

| Need | Document | Max size target |
|------|----------|-----------------|
| **Today's pickup + open backlog (QA + engineering)** | [`action_tracker.md`](action_tracker.md) | **≤ ~200 lines** — one Session Handoff; Open items table logs every QA finding |
| **Rejected approaches / gotchas** | [`engineering_playbook.md`](engineering_playbook.md) | Short bullets with dates |
| **Which doc to open** | [`DOCUMENTATION.md`](DOCUMENTATION.md) | Index only — no duplicated prose |
| **Resolved epics / old handoffs** | [`archive/`](archive/) | Append-only history |
| **System design** | [`technical_solution.md`](technical_solution.md) | Update when pipeline shape changes |
| **Timers / deploy** | [`technical_solution.md`](technical_solution.md) §1.4 | Do not invent UTC times elsewhere |

---

## After every deliver (~5 min)

Follow [`post_deliver_checklist.md`](post_deliver_checklist.md) §6. When editing the tracker:

1. **Replace** the single **Session Handoff** block (do not add a second handoff section).
2. Update **Open items** only — drop completed P1s (one line in **Recently shipped** is enough).
3. **Do not** add Phase 0–6-style implementation specs or long “Resolution” narratives.
4. **Do not** duplicate the doc index — link [`DOCUMENTATION.md`](DOCUMENTATION.md).
5. Gotcha discovered twice? One bullet in **playbook**, not a paragraph in the tracker.

---

## Monthly or when `action_tracker.md` exceeds ~200 lines

1. Move superseded Session Handoff blocks to `docs/archive/implementation_log_YYYY-MM.md` (or start a new month file).
2. Move any lingering **Phase / DONE** implementation write-ups to archive.
3. Keep **Deferred** items as a short bullet list (≤ 5 lines) in the tracker, or drop if captured in playbook.

Agents may propose this trim when they notice bloat; humans approve large archives.

---

## Agents — required behavior

- **Read** only the top of `action_tracker.md` (Session Handoff + Open items) unless investigating history.
- **Never** paste Azure hostnames, full doc tables, or phase specs into the tracker.
- **Never** add a second “Documentation index” to the tracker.
- **Archive path** for historical detail: [`archive/implementation_log_2026-05.md`](archive/implementation_log_2026-05.md).
- **Timer SSOT:** `function_app.py` — prepare `0 0 6 * * *`, QA digest `0 0 7 * * *` in `WEBSITE_TIME_ZONE` (default `America/Los_Angeles`). Link §1.4 in `technical_solution.md`; do not write bare “11:00 UTC”.

---

## Humans

- Prefer **git commits** over tracker prose for “what shipped.”
- Sprint-specific SSOT (e.g. charts) may live in a **handoff doc** until the gate clears; then fold gotchas into playbook and shorten the handoff.
