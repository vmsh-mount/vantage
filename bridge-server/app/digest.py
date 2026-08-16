"""Daily deterministic email digest (task 27, planning-phase2.md §5.4) —
composed and sent entirely in Python. No agent, no MCP call, so it genuinely
always sends regardless of INDmoney/Claude Code availability — see the Scope
section of docs/tasks/27-daily-digest-email.md for why task 25's
vol-stops/benchmark are deliberately excluded (they depend on bridge-server's
INDmoney MCP client, exactly the "auth fragility"/"MCP mesh" this task's
design principle avoids).

Task 36 adds a second, best-effort "Agent's take" section — see
_compose_agent_section's own docstring for the augments-never-replaces
contract (docs/tasks/36-agent-authored-desk-note.md)."""

import asyncio
import html as html_escape
import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from sqlalchemy.orm import Session

from app.agent_runner import run_one_shot
from app.agent_security import build_scoped_extra_args
from app.compass import compute_compass_summary
from app.config import settings
from app.db import SessionLocal
from app.decisions import get_decisions
from app.models import DecisionLog, DigestLog, Thesis
from app.routers.alerts import get_alerts
from app.routers.dashboard import get_dashboard
from app.routers.risk import get_risk
from app.tax.suggestions import get_tax_suggestions
from app.thesis import get_recent_theses

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
FAILURE_LOG_PATH = LOG_DIR / "digest_failures.log"

_logger = logging.getLogger("vantage.digest")
_logger.setLevel(logging.ERROR)
_logger.propagate = False

MISSED_RUN_GAP = timedelta(hours=36)  # a daily job that hasn't fired in 36h didn't just run late

# Task 36 — generous enough to cover one cold INDmoney rate-limit window
# inside the reasoning turn (task 25's own live testing found ~2 minutes),
# short enough that a hung process doesn't meaningfully delay the digest
# send. See docs/tasks/36-agent-authored-desk-note.md's Scope.
AGENT_SECTION_TIMEOUT_SECONDS = 150
AGENT_CONTEXT_LIMIT = 20  # most-recent thesis/decision rows embedded in the prompt


def _ensure_failure_handler() -> None:
    if _logger.handlers:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(FAILURE_LOG_PATH)
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _logger.addHandler(handler)


def _missed_or_failed_previous_run(db: Session, now: datetime) -> str | None:
    """The dead-man's-switch check: did the last recorded run fail, or did no
    run happen at all in the last 36h (laptop off, process down)? Returns a
    human-readable gap description to lead today's email with, or None if
    the previous run was fine (or this is the very first run ever)."""
    last = db.query(DigestLog).order_by(DigestLog.run_at.desc()).first()
    if last is None:
        return None
    if last.status == "failed":
        return f"digest failed on {last.run_at.strftime('%d %b %Y')} ({last.error or 'no error recorded'})"
    if now - last.run_at.replace(tzinfo=timezone.utc) > MISSED_RUN_GAP:
        return f"no digest ran between {last.run_at.strftime('%d %b %Y')} and today"
    return None


def _needs_attention(db: Session) -> list[str]:
    lines = [f"Stop-loss hit: {a.title}" for a in get_alerts(db).alerts if a.kind == "stop_loss"]
    lines += [s["headline"] for s in get_tax_suggestions(db) if s["kind"] == "ltcg_crossing_soon"]
    return lines


def _tax_opportunities(db: Session) -> list[str]:
    harvest = [s for s in get_tax_suggestions(db) if s["kind"] in ("harvest_loss", "harvest_gain")]
    harvest.sort(key=lambda s: s["amount_inr"] or 0, reverse=True)
    return [s["headline"] for s in harvest]


def _concentration(db: Session) -> list[str]:
    return [
        f"{f.label} is {f.pct:.1f}% of your portfolio (limit {f.limit_pct:.0f}%)"
        for f in get_risk(db).concentration_flags
    ]


def _movers(db: Session) -> list[str]:
    return [a.title for a in get_alerts(db).alerts if a.kind == "mover"]


def _summary(db: Session) -> str:
    d = get_dashboard(db)
    direction = "up" if d.today_move_abs_inr >= 0 else "down"
    return (
        f"Net worth: Rs {d.net_worth_inr:,.2f} — today {direction} "
        f"Rs {abs(d.today_move_abs_inr):,.2f} ({d.today_move_pct:+.2f}%), "
        f"overall P&L {d.total_pnl_pct:+.2f}%"
    )


def _compass_summary_line(db: Session) -> str | None:
    """One deterministic line, not a new section — docs/compass-prd.md §12
    build order deliberately keeps Compass out of the digest's structure and
    just appends this to the existing summary. Returns None (and the line is
    omitted entirely, same "omitted when empty" convention as every other
    digest section) when nothing is configured yet, rather than a
    padded "no goals configured" line."""
    s = compute_compass_summary(db)
    parts = []
    if s["goals"]["total"]:
        parts.append(f"{s['goals']['met']}/{s['goals']['total']} goals met")
    if s["allocation_targets"]["total"]:
        parts.append(f"{s['allocation_targets']['on_target']}/{s['allocation_targets']['total']} allocations on target")
    if s["milestones"]["total"]:
        parts.append(f"{s['milestones']['on_pace']}/{s['milestones']['total']} milestones on pace")
    if not parts:
        return None
    return "Compass: " + ", ".join(parts)


def build_digest(db: Session) -> dict:
    """Clarity over volume (§5): each section is ranked most-important-first
    and simply omitted when empty — a digest padded with "nothing to report"
    sections isn't clearer than a shorter one."""
    return {
        "needs_attention": _needs_attention(db),
        "tax_opportunities": _tax_opportunities(db),
        "concentration": _concentration(db),
        "movers": _movers(db),
        "summary": _summary(db),
        "compass_summary": _compass_summary_line(db),
    }


def render_text(content: dict, gap_message: str | None, agent_section: str | None = None) -> str:
    lines: list[str] = []
    if gap_message:
        lines += [f"[!] {gap_message}", ""]
    for title, key in [
        ("NEEDS ATTENTION NOW", "needs_attention"),
        ("TAX OPPORTUNITIES", "tax_opportunities"),
        ("CONCENTRATION", "concentration"),
        ("BIG MOVERS TODAY", "movers"),
    ]:
        items = content[key]
        if items:
            lines.append(title)
            lines += [f"- {item}" for item in items]
            lines.append("")
    lines.append(content["summary"])
    if content.get("compass_summary"):
        lines.append(content["compass_summary"])
    if agent_section:
        # Task 36 — clearly labeled and visually separated from the
        # deterministic content above, never blended in as if it were the
        # same kind of fact.
        lines += ["", "-" * 40, "AGENT'S TAKE (best-effort, may be absent some days)", "-" * 40, agent_section]
    return "\n".join(lines)


def render_html(content: dict, gap_message: str | None, agent_section: str | None = None) -> str:
    def section(title: str, items: list[str]) -> str:
        if not items:
            return ""
        rows = "".join(f"<li>{item}</li>" for item in items)
        return f"<h3>{title}</h3><ul>{rows}</ul>"

    banner = (
        f'<p style="color:#b00020;font-weight:bold">[!] {gap_message}</p>' if gap_message else ""
    )
    # Task 36 — html_escape'd since this is model-generated text (and may
    # itself quote web content it looked up); everything else in this
    # function is Python-composed from known-safe values, this is the one
    # section that isn't.
    agent_html = (
        '<hr style="margin-top:24px">'
        '<h3 style="color:#555">Agent\'s take <span style="font-weight:normal;font-size:12px">'
        "(best-effort — may be absent some days)</span></h3>"
        f'<p style="white-space:pre-wrap">{html_escape.escape(agent_section)}</p>'
        if agent_section
        else ""
    )
    compass_html = f"<p>{content['compass_summary']}</p>" if content.get("compass_summary") else ""
    body = (
        banner
        + section("Needs attention now", content["needs_attention"])
        + section("Tax opportunities", content["tax_opportunities"])
        + section("Concentration", content["concentration"])
        + section("Big movers today", content["movers"])
        + f"<p>{content['summary']}</p>"
        + compass_html
        + agent_html
    )
    return f"<html><body style='font-family: sans-serif;'>{body}</body></html>"


def _agent_context_lines(db: Session) -> tuple[list[str], list[str]]:
    """Recent thesis/decision context to embed in the agent's prompt —
    task 35 quarantine-filtered by construction (get_recent_theses/
    get_decisions both default to excluding an unreviewed quarantined row),
    never passed in unfiltered."""
    theses: list[Thesis] = get_recent_theses(db, limit=AGENT_CONTEXT_LIMIT)
    decisions: list[DecisionLog] = get_decisions(db, limit=AGENT_CONTEXT_LIMIT)
    thesis_lines = [
        f"{t.broker}/{t.symbol} (conviction {t.conviction if t.conviction is not None else 'n/a'}, "
        f"{t.created_at.strftime('%d %b %Y')}): {t.text}"
        for t in theses
    ]
    decision_lines = [
        f'{d.broker}/{d.symbol}: "{d.headline}" — {d.success_criterion_kind} {d.success_criterion_value} '
        f"within {d.horizon_days}d (status: {d.status}, outcome: {d.outcome or 'pending'})"
        for d in decisions
    ]
    return thesis_lines, decision_lines


def _build_agent_prompt(content: dict, thesis_lines: list[str], decision_lines: list[str]) -> str:
    parts = [
        "You are writing a short \"Agent's take\" section for a daily portfolio digest email. "
        "Here is today's deterministic summary, already computed — don't just repeat it verbatim, "
        "add judgment and context:",
        content["summary"],
    ]
    if content["needs_attention"]:
        parts.append("Needs attention: " + "; ".join(content["needs_attention"]))
    if content["tax_opportunities"]:
        parts.append("Tax opportunities: " + "; ".join(content["tax_opportunities"]))
    if content["concentration"]:
        parts.append("Concentration flags: " + "; ".join(content["concentration"]))
    if content["movers"]:
        parts.append("Big movers: " + "; ".join(content["movers"]))
    if thesis_lines:
        parts.append("Recent investment thesis entries (most recent first):\n" + "\n".join(thesis_lines))
    if decision_lines:
        parts.append("Recently logged decisions (most recent first):\n" + "\n".join(decision_lines))
    parts.append(
        "Write 3-5 short, ranked, concrete observations or things worth considering today, given "
        "the above. You may search the web for relevant news and cite it if it helps. Keep the "
        "whole thing under 200 words. Plain text only, no markdown headers."
    )
    return "\n\n".join(parts)


async def _run_agent_turn(prompt: str) -> str | None:
    # Read-only (allow_write=False, the default) — this section only ever
    # composes commentary, it never calls log_decision/add_thesis_entry
    # itself. enable_web=True so it can cite news, same as the panel.
    extra_args = build_scoped_extra_args(enable_web=True)
    async for event in run_one_shot(prompt, extra_args=extra_args):
        if event.get("type") == "result":
            if event.get("is_error"):
                return None
            text = event.get("result")
            return text.strip() if text else None
    return None


def _compose_agent_section(db: Session, content: dict) -> str | None:
    """Task 36 — best-effort, additive only. Builds the prompt from the same
    deterministic content dict already assembled plus recent, quarantine-
    filtered Thesis/DecisionLog context, then runs one run_one_shot turn
    under a hard 150s budget. Returns the agent's text on success; returns
    None (logged, never raised) on any failure, timeout, or error result —
    by design, nothing this function can do prevents run_daily_digest's
    guaranteed deterministic send from happening."""
    try:
        thesis_lines, decision_lines = _agent_context_lines(db)
        prompt = _build_agent_prompt(content, thesis_lines, decision_lines)
        return asyncio.run(asyncio.wait_for(_run_agent_turn(prompt), timeout=AGENT_SECTION_TIMEOUT_SECONDS))
    except Exception as exc:
        _ensure_failure_handler()
        _logger.error("Agent desk-note section failed (deterministic send unaffected): %s", exc)
        return None


def _smtp_send(msg: MIMEMultipart) -> None:
    if not settings.smtp_host:
        raise RuntimeError("SMTP not configured (SMTP_HOST is blank in .env)")
    if not settings.digest_recipient_email:
        raise RuntimeError("DIGEST_RECIPIENT_EMAIL is blank — nowhere to send the digest")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(msg)


def _send_email(subject: str, text_body: str, html_body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.digest_from_email or settings.smtp_username
    msg["To"] = settings.digest_recipient_email
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    _smtp_send(msg)


def _send_fallback_email(original_error: str) -> None:
    """Deliberately independent of build_digest/render_* — those are exactly
    what might have broken, so the failure notice can't depend on them."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Vantage digest FAILED"
    msg["From"] = settings.digest_from_email or settings.smtp_username
    msg["To"] = settings.digest_recipient_email
    msg.attach(
        MIMEText(
            "The Vantage daily digest failed to compose.\n\n"
            f"Error: {original_error}\n\n"
            "Check bridge-server/logs/digest_failures.log for details.",
            "plain",
        )
    )
    _smtp_send(msg)


def run_daily_digest() -> None:
    """The one scheduled job (app/scheduler.py). Never lets an exception
    vanish silently: on failure, tries a minimal fallback email; either way,
    writes a DigestLog row so the *next* run's dead-man's-switch check can
    surface today's failure even if every email attempt failed outright."""
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        gap_message = _missed_or_failed_previous_run(db, now)
        try:
            content = build_digest(db)
            # Task 36: best-effort, additive — _compose_agent_section
            # internally catches everything and respects a hard timeout, so
            # calling it inline here (before the guaranteed send) can't
            # actually block that send; verified live, not just asserted
            # (see docs/tasks/36-agent-authored-desk-note.md's Acceptance
            # criteria's forced-failure test).
            agent_section = _compose_agent_section(db, content)
            text_body = render_text(content, gap_message, agent_section)
            html_body = render_html(content, gap_message, agent_section)
            subject = "Vantage — Daily Digest" + (" [!]" if gap_message else "")
            _send_email(subject, text_body, html_body)
            db.add(DigestLog(status="sent"))
            db.commit()
        except Exception as exc:
            error_text = f"{type(exc).__name__}: {exc}"
            _ensure_failure_handler()
            _logger.error("Digest composition/send failed: %s", error_text)
            try:
                _send_fallback_email(error_text)
                db.add(DigestLog(status="fallback_sent", error=error_text))
            except Exception as fallback_exc:
                _logger.error("Fallback email also failed: %s", fallback_exc)
                db.add(
                    DigestLog(
                        status="failed",
                        error=f"{error_text} | fallback also failed: {fallback_exc}",
                    )
                )
            db.commit()
    finally:
        db.close()
