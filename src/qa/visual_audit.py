"""Deterministic Visual QA — ground-truth checks on the final briefing HTML.

These rules encode the email-safe layout requirements from the Graphics Designer
QA persona. Golden fixtures in tests/fixtures/visual_qa/ regression-test them.
"""
import re
from bs4 import BeautifulSoup

from src.output.briefing_style import BG_CANVAS, BRAND_SAGE

# Patterns that break in Gmail/Outlook (from graphics_designer_qa mandate).
_EMAIL_UNSAFE_CSS = re.compile(
    r"(display\s*:\s*flex|flex-direction|display\s*:\s*grid|object-fit)",
    re.IGNORECASE,
)


def _style_blocks(html: str) -> list[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    blocks = []
    for tag in soup.find_all("style"):
        blocks.append(tag.get_text() or "")
    for tag in soup.find_all(style=True):
        blocks.append(tag.get("style") or "")
    return blocks


def audit_briefing_theme(html: str) -> list[dict]:
    """Verify the dark premium palette SSOT is present in the saved briefing artifact."""
    findings: list[dict] = []
    if not (html or "").strip():
        return findings

    if BG_CANVAS not in html:
        findings.append({
            "severity": "WARNING",
            "category": "Brand Palette",
            "description": f"Dark canvas color {BG_CANVAS} not found in briefing HTML.",
            "recommendation": "Use executive_briefing_inline_styles() on body and outer wrapper table.",
        })
    soup = BeautifulSoup(html or "", "html.parser")
    body = soup.find("body")
    body_style = (body.get("style") or "") if body else ""
    if body and BG_CANVAS not in body_style:
        findings.append({
            "severity": "CRITICAL",
            "category": "Brand Palette",
            "description": "Body tag missing inline Stealth Wealth canvas background (Gmail strips head CSS).",
            "recommendation": f"Set body style background-color:{BG_CANVAS} via executive_briefing_inline_styles().",
        })
    if BRAND_SAGE not in html:
        findings.append({
            "severity": "WARNING",
            "category": "Brand Palette",
            "description": f"Matte sage accent {BRAND_SAGE} not found in briefing CSS.",
            "recommendation": "Headings and chart titles should use --brand-sage.",
        })
    if "filter:" in html and "chart-img" in html:
        findings.append({
            "severity": "CRITICAL",
            "category": "Chart Presentation",
            "description": "CSS filter applied to chart images — ruins categorical color fidelity.",
            "recommendation": "Render charts natively on #121212 via QuickChart; remove filter rules from chart CSS.",
        })
    return findings


def audit_briefing_html(html: str) -> list[dict]:
    """Return structured findings for the saved/emailed briefing HTML artifact."""
    findings: list[dict] = []
    if not (html or "").strip():
        return [{
            "severity": "CRITICAL",
            "category": "Missing Artifact",
            "description": "Executive briefing HTML is empty.",
            "recommendation": "Regenerate the briefing before deliver.",
        }]

    soup = BeautifulSoup(html, "html.parser")
    findings.extend(audit_briefing_theme(html))

    for idx, block in enumerate(_style_blocks(html)):
        if _EMAIL_UNSAFE_CSS.search(block):
            findings.append({
                "severity": "CRITICAL",
                "category": "Email Layout",
                "description": (
                    f"Email-unsafe CSS detected (flex/grid/object-fit) in style block #{idx + 1}. "
                    "Gmail and Outlook strip these rules, collapsing chart layouts."
                ),
                "recommendation": "Use `<table role=\"presentation\">` layout for chart rows; remove flex/grid/object-fit.",
            })
            break

    chart_images = []
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        alt = (img.get("alt") or "").strip()
        classes = " ".join(img.get("class") or [])
        parent_classes = " ".join(
            c for p in img.parents if getattr(p, "name", None)
            for c in (p.get("class") or [])
        )
        is_chart = "chart" in classes.lower() or "chart" in parent_classes.lower() or "chart" in alt.lower()

        if not alt:
            findings.append({
                "severity": "CRITICAL",
                "category": "Accessibility",
                "description": f"Image missing alt text (src={src[:80] or 'MISSING'}).",
                "recommendation": "Add descriptive alt text to every briefing image.",
            })

        if is_chart or "chart-container" in parent_classes:
            chart_images.append(img)
            if not src:
                findings.append({
                    "severity": "CRITICAL",
                    "category": "Broken Chart",
                    "description": "Chart image has an empty or missing src URL.",
                    "recommendation": "Rebuild chart URLs before sending the briefing.",
                })
            elif not src.startswith(("http://", "https://")):
                findings.append({
                    "severity": "CRITICAL",
                    "category": "Broken Chart",
                    "description": f"Chart image src is not a fetchable HTTP URL: {src[:80]}",
                    "recommendation": "Use QuickChart short URLs for all embedded charts.",
                })
            inline_style = (img.get("style") or "").lower()
            if "max-width" not in inline_style and "chart-img" not in classes:
                findings.append({
                    "severity": "WARNING",
                    "category": "Email Layout",
                    "description": f"Chart image may overflow email clients (no max-width or chart-img class): {alt or src[:60]}",
                    "recommendation": "Add class=\"chart-img\" or inline max-width:100% on chart images.",
                })

    if soup.find(class_=re.compile(r"chart-container", re.I)) and not chart_images:
        findings.append({
            "severity": "CRITICAL",
            "category": "Broken Chart",
            "description": "Chart container present but no chart images found in the HTML.",
            "recommendation": "Ensure chart URLs are embedded as <img> tags inside chart containers.",
        })

    return findings


def build_deterministic_visual_report(html: str, chart_health: list[dict]) -> dict:
    """Merge chart-health probes with HTML structure audit — no LLM."""
    from src.qa_pipeline import build_graphics_report, reconcile_compliance

    chart_report = build_graphics_report(chart_health)
    html_findings = audit_briefing_html(html)
    combined_findings = list(chart_report.get("findings") or []) + html_findings
    has_critical = any(str(f.get("severity", "")).upper() == "CRITICAL" for f in combined_findings)
    chart_ok = bool(chart_report.get("is_compliant"))
    html_ok = not any(str(f.get("severity", "")).upper() == "CRITICAL" for f in html_findings)

    summaries = [chart_report.get("summary", "")]
    if html_findings:
        html_crit = sum(1 for f in html_findings if str(f.get("severity", "")).upper() == "CRITICAL")
        html_warn = sum(1 for f in html_findings if str(f.get("severity", "")).upper() == "WARNING")
        summaries.append(
            f"HTML structure audit: {html_crit} CRITICAL, {html_warn} WARNING."
            if html_findings else "HTML structure audit: clean."
        )
    else:
        summaries.append("HTML structure audit: clean.")

    return reconcile_compliance({
        "agent_role": "Graphics Designer Visual SME (deterministic)",
        "is_compliant": chart_ok and html_ok and not has_critical,
        "findings": combined_findings,
        "summary": " | ".join(s for s in summaries if s),
    })
