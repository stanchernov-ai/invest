"""Persist Legal Counsel findings and email Stan a dedicated report."""
from __future__ import annotations

import html
import logging
from typing import Any

from src import storage_client
from src.config.settings import now_local
from src.output import notifier

logger = logging.getLogger(__name__)


def briefing_blob_name(run_id: str) -> str:
    return f"legal_counsel_briefing_{run_id}.json"


def code_audit_blob_name(day_stamp: str) -> str:
    return f"legal_code_audit_{day_stamp}.json"


def _severity_rank(severity: str) -> int:
    order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
    return order.get(str(severity or "").upper(), 9)


def render_legal_counsel_email_html(
    report: dict,
    *,
    title: str,
    subtitle: str,
    artifact_ref: str,
) -> str:
    """Dark-premium HTML email for Legal Counsel findings."""
    findings = sorted(
        report.get("findings") or [],
        key=lambda f: (_severity_rank(f.get("severity", "")), f.get("category", "")),
    )
    compliant = bool(report.get("is_compliant"))
    status = "PASS" if compliant else "FINDINGS"
    status_color = "#6ee7b7" if compliant else "#fca5a5"
    summary = html.escape(report.get("summary") or "No summary recorded.")

    rows = ""
    for f in findings:
        sev = html.escape(str(f.get("severity", "")))
        cat = html.escape(str(f.get("category", "")))
        desc = html.escape(str(f.get("description", "")))
        rec = html.escape(str(f.get("recommendation", "")))
        sev_color = "#fca5a5" if sev.upper() == "CRITICAL" else (
            "#fcd34d" if sev.upper() == "WARNING" else "#a1a1aa"
        )
        rows += (
            f"<tr>"
            f"<td style='padding:8px;border-bottom:1px solid #3f3f46;color:{sev_color};'>{sev}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #3f3f46;color:#a1a1aa;'>{cat}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #3f3f46;color:#f4f4f5;'>{desc}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #3f3f46;color:#a1a1aa;'>{rec}</td>"
            f"</tr>"
        )

    findings_block = (
        "<p style='color:#a1a1aa;margin:16px 0 8px 0;'>No findings flagged.</p>"
        if not rows
        else (
            "<table width='100%' cellpadding='0' cellspacing='0' "
            "style='border-collapse:collapse;margin-top:12px;font-size:0.9em;'>"
            "<tr>"
            "<th align='left' style='padding:8px;border-bottom:2px solid #3f3f46;color:#95b8a2;'>Severity</th>"
            "<th align='left' style='padding:8px;border-bottom:2px solid #3f3f46;color:#95b8a2;'>Category</th>"
            "<th align='left' style='padding:8px;border-bottom:2px solid #3f3f46;color:#95b8a2;'>Description</th>"
            "<th align='left' style='padding:8px;border-bottom:2px solid #3f3f46;color:#95b8a2;'>Remediation</th>"
            "</tr>"
            f"{rows}</table>"
        )
    )

    files = report.get("files_scanned") or []
    files_line = ""
    if files:
        files_line = (
            "<p style='color:#71717a;font-size:0.85em;margin-top:16px;'>"
            f"Files scanned: {html.escape(', '.join(files))}</p>"
        )

    return f"""
    <html>
    <body style="font-family:'Segoe UI',Tahoma,sans-serif;background:#121212;padding:24px;color:#a1a1aa;">
        <div style="max-width:720px;margin:0 auto;background:#1e1e1e;border:1px solid #3f3f46;border-radius:8px;padding:24px;">
            <h1 style="color:#95b8a2;margin:0 0 4px 0;font-size:1.4em;">{html.escape(title)}</h1>
            <p style="margin:0 0 16px 0;color:#71717a;font-size:0.9em;">{html.escape(subtitle)}</p>
            <p style="margin:0 0 12px 0;">
                <strong style="color:{status_color};">{status}</strong>
                &nbsp;&middot;&nbsp; {len(findings)} finding(s)
            </p>
            <div style="background:#27272a;border-left:4px solid #95b8a2;padding:12px 14px;border-radius:4px;margin-bottom:8px;">
                <strong style="color:#f4f4f5;">Summary:</strong> {summary}
            </div>
            {findings_block}
            {files_line}
            <p style="color:#71717a;font-size:0.82em;margin-top:24px;border-top:1px solid #3f3f46;padding-top:12px;">
                Artifact: boardroom-state/{html.escape(artifact_ref)}<br>
                Advisory only — not legal advice.
            </p>
        </div>
    </body>
    </html>
    """


def persist_and_notify_briefing_legal(
    run_id: str,
    report: dict,
    *,
    send_email: bool = True,
) -> dict[str, Any]:
    """Save per-run briefing legal report; email owner when send_email=True."""
    finished = now_local().isoformat()
    payload = {
        "audit_type": "briefing",
        "run_id": run_id,
        "finished_at": finished,
        "report": report,
    }
    blob = briefing_blob_name(run_id)
    storage_client.save_state_blob(blob, payload)

    compliant = bool(report.get("is_compliant"))
    findings_n = len(report.get("findings") or [])
    subject_tag = "PASS" if compliant and findings_n == 0 else "REVIEW"
    email_html = render_legal_counsel_email_html(
        report,
        title="Legal Counsel — Executive Briefing Review",
        subtitle=f"Run {run_id} · pre-distribution briefing audit",
        artifact_ref=blob,
    )
    if send_email:
        email_ok = notifier.send_legal_counsel_report(
            email_html,
            subject=f"Legal Counsel Briefing — {subject_tag} ({run_id})",
        )
    else:
        email_ok = None
    logger.info(
        "[LEGAL COUNSEL] Briefing audit saved %s compliant=%s findings=%d email_ok=%s send_email=%s",
        blob, compliant, findings_n, email_ok, send_email,
    )
    return {"blob": blob, "email_ok": email_ok, "payload": payload}


def persist_and_notify_code_legal(day_stamp: str, report: dict, *, started_at: str) -> dict[str, Any]:
    """Save daily code audit and email Stan."""
    payload = {
        "audit_type": "code_daily",
        "day_stamp": day_stamp,
        "started_at": started_at,
        "finished_at": now_local().isoformat(),
        "report": report,
    }
    blob = code_audit_blob_name(day_stamp)
    storage_client.save_state_blob(blob, payload)

    compliant = bool(report.get("is_compliant"))
    findings_n = len(report.get("findings") or [])
    subject_tag = "PASS" if compliant and findings_n == 0 else "REVIEW"
    email_html = render_legal_counsel_email_html(
        report,
        title="Legal Counsel — Daily Codebase Audit",
        subtitle=f"Date {day_stamp} · prompts, templates, and product copy",
        artifact_ref=blob,
    )
    email_ok = notifier.send_legal_counsel_report(
        email_html,
        subject=f"Legal Counsel Code Audit — {subject_tag} ({day_stamp})",
    )
    logger.info(
        "[LEGAL COUNSEL] Code audit saved %s compliant=%s findings=%d email_ok=%s",
        blob, compliant, findings_n, email_ok,
    )
    if not compliant:
        crit = sum(
            1 for f in (report.get("findings") or [])
            if str(f.get("severity", "")).upper() == "CRITICAL"
        )
        notifier.send_error_alert(
            f"Legal Counsel daily code audit: {crit} CRITICAL finding(s). "
            f"See boardroom-state/{blob} and your Legal Counsel email."
        )
    return {"blob": blob, "email_ok": email_ok, "payload": payload}
