"""The run-completed email: outcome rules, subject, HTML and plain text.

Pure — `SendTestRunReportEmailActivity` loads a `RunEmail` from the
database and passes it here, so every rule below is unit-tested without a
database or SMTP.

Only final Vantage statuses are shown. A test that passed after
self-healing is simply passed — nothing here knows healing exists.

Email HTML is tables plus inline styles only (no <style>, no JS, no
flex/grid) so Gmail and desktop Outlook render the same layout. Every
database-derived value is HTML-escaped where it's inserted.
"""

import html
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import quote, urlsplit

from mailer import EMAIL_HEADER

Outcome = Literal["passed", "failed", "couldnt_run"]

MAX_LISTED_FAILURES = 10
_MAX_ERROR_CHARS = 140

# Same palette as the Vantage report (vantage_report/template.html).
_FG, _FG_2, _FG_4, _FG_5 = "#16161A", "#3E3E46", "#5C5C66", "#6C6C76"
_LINE, _TRACK, _PAGE_BG = "#E5E6E9", "#E8E9EC", "#EDEEF0"
_ACCENT = "#0f766e"
_STATUS_COLORS = {
    "passed": ("#0D8A64", "#e8f6f0"),
    "failed": ("#C93049", "#fdeef1"),
    "timed_out": ("#b45309", "#fff6e6"),
    "errored": ("#64748b", "#f1f3f6"),
    "blocked": ("#64748b", "#f1f3f6"),
}
_STATUS_LABELS = {
    "passed": "Passed",
    "failed": "Failed",
    "timed_out": "Timed out",
    "errored": "Errored",
    "blocked": "Blocked",
}
_FONT = "-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif"


@dataclass
class RunCounts:
    total: int = 0
    passed: int = 0
    failed: int = 0
    timed_out: int = 0
    errored: int = 0
    blocked: int = 0

    @property
    def executed(self) -> int:
        """Blocked tests never started, so they never count for or against
        the pass rate."""
        return self.total - self.blocked

    @property
    def not_passed(self) -> int:
        return self.failed + self.timed_out + self.errored


@dataclass
class FailedTest:
    name: str
    journey: str | None
    status: str  # failed | timed_out | errored
    error_message: str | None
    duration_ms: int | None
    # Plain-language failure (`workflows.failure_explainer` rule title, or a
    # cached AI one); shown instead of `short_error(error_message)` when set.
    description: str | None = None


@dataclass
class RunEmail:
    application_id: str
    test_run_id: str
    app_name: str
    run_number: int
    counts: RunCounts
    started_at: datetime | None
    completed_at: datetime | None
    target_url: str | None
    # Manual: the starter's name. Scheduled: the schedule's name.
    triggered_by_name: str | None
    scheduled: bool
    report_available: bool
    base_url: str
    failed_tests: list[FailedTest] = field(default_factory=list)
    # One sentence when most failures share one cause ("38 of 40 failed
    # tests have the same cause — ..."), shown above the failed tests.
    root_cause: str | None = None


def outcome_of(counts: RunCounts) -> Outcome:
    """One verdict that the subject, banner and pass-rate text all follow.

    - couldnt_run: nothing passed and nothing failed an assertion or timed
      out — every executed test errored (or nothing executed at all).
    - passed: something ran and nothing failed, timed out or errored.
    - failed: anything else. So any failed, timed-out or errored test keeps
      a run from ever getting the all-passed banner."""
    if counts.passed == 0 and counts.failed == 0 and counts.timed_out == 0:
        return "couldnt_run"
    if counts.not_passed == 0:
        return "passed"
    return "failed"


def pass_rate_of(counts: RunCounts) -> int | None:
    """Whole-percent passed ÷ executed (blocked excluded); None when nothing
    executed. Floored, so 100% only ever means every executed test passed."""
    if counts.executed <= 0:
        return None
    return math.floor(counts.passed * 100 / counts.executed)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def headline_of(counts: RunCounts) -> str:
    match outcome_of(counts):
        case "passed":
            if counts.passed == 1:
                return "The test passed"
            return f"All {counts.passed} tests passed"
        case "failed":
            return f"{counts.not_passed} of {_plural(counts.executed, 'test')} didn't pass"
        case _:
            return "No tests ran" if counts.executed <= 0 else "Run couldn't complete"


def _one_line(text: str) -> str:
    # Headers must stay on one line (and a newline in one would be rejected).
    return " ".join(text.split())


def subject_of(email: RunEmail) -> str:
    mark = {"passed": "✓", "failed": "✕", "couldnt_run": "!"}[outcome_of(email.counts)]
    return _one_line(
        f"{mark} Run #{email.run_number} · {email.app_name} — {headline_of(email.counts)}"
    )


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def short_error(message: str | None) -> str | None:
    """First non-empty line, ANSI codes stripped, capped for the table."""
    if not message:
        return None
    for line in _ANSI.sub("", message).splitlines():
        line = line.strip()
        if line:
            if len(line) > _MAX_ERROR_CHARS:
                return line[: _MAX_ERROR_CHARS - 1].rstrip() + "…"
            return line
    return None


def format_duration(ms: float | None) -> str:
    if ms is None or ms < 0:
        return "—"
    seconds = int(round(ms / 1000))
    if seconds < 60:
        return f"{seconds}s" if seconds else "<1s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s" if seconds else f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m" if minutes else f"{hours}h"


def _run_duration_ms(email: RunEmail) -> float | None:
    if email.started_at is None or email.completed_at is None:
        return None
    return (email.completed_at - email.started_at).total_seconds() * 1000


def _format_time(value: datetime | None) -> str:
    if value is None:
        return "—"
    value = value if value.tzinfo else value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%d %b %Y, %H:%M UTC")


def _safe_http_url(url: str | None) -> str | None:
    """`url` if it's a plain http(s) URL, else None — only those become
    links; anything else (javascript:, data:, garbage) is shown as text."""
    if not url:
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme.lower() in ("http", "https") and parts.netloc:
        return url.strip()
    return None


def run_url(email: RunEmail) -> str:
    return (
        f"{email.base_url.rstrip('/')}/applications/{quote(email.application_id, safe='')}"
        f"/test-runs/{quote(email.test_run_id, safe='')}"
    )


def report_url(email: RunEmail) -> str:
    return f"{run_url(email)}/report"


def _ordered_failures(email: RunEmail) -> list[FailedTest]:
    order = {"failed": 0, "timed_out": 1, "errored": 2}
    return sorted(email.failed_tests, key=lambda t: (order.get(t.status, 3), t.name.lower()))


def _started_by(email: RunEmail) -> str:
    if email.scheduled:
        return f"Schedule “{email.triggered_by_name}”" if email.triggered_by_name else "Schedule"
    return email.triggered_by_name or "—"


def _why_received(email: RunEmail) -> str:
    if email.scheduled:
        if email.triggered_by_name:
            return f"You're receiving this because you created the schedule “{email.triggered_by_name}”."
        return "You're receiving this because you created this run's schedule."
    return "You're receiving this because you started this run."


# --- HTML ------------------------------------------------------------------


def _banner(email: RunEmail) -> str:
    outcome = outcome_of(email.counts)
    color, wash = {
        "passed": _STATUS_COLORS["passed"],
        "failed": _STATUS_COLORS["failed"],
        "couldnt_run": _STATUS_COLORS["errored"],
    }[outcome]
    icon = {"passed": "&#10003;", "failed": "&#10005;", "couldnt_run": "!"}[outcome]
    detail = ""
    if outcome == "couldnt_run" and email.counts.executed > 0:
        detail = f"{_plural(email.counts.errored, 'test')} errored before finishing"
    elif email.counts.blocked:
        detail = f"{email.counts.blocked} blocked"
    detail_html = (
        f'<p style="margin:6px 0 0;font-size:13px;color:{_FG_4};">{_e(detail)}</p>' if detail else ""
    )
    return f"""\
        <tr><td style="padding:24px 32px 8px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{wash};border-left:4px solid {color};border-radius:8px;">
            <tr><td style="padding:16px 18px;">
              <p style="margin:0;font-size:12px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;color:{_FG_4};">{_e(email.app_name)} &middot; Run #{email.run_number}</p>
              <p style="margin:6px 0 0;font-size:20px;line-height:1.3;font-weight:700;color:{color};">{icon}&nbsp; {_e(headline_of(email.counts))}</p>
              {detail_html}
            </td></tr>
          </table>
        </td></tr>"""


def _tiles(counts: RunCounts) -> str:
    cells = []
    for key in ("passed", "failed", "timed_out", "errored", "blocked"):
        value = getattr(counts, key)
        color = _STATUS_COLORS[key][0] if value else _FG_5
        cells.append(
            f'<td width="20%" align="center" style="padding:12px 4px;border:1px solid {_LINE};'
            f'border-radius:8px;background:#ffffff;">'
            f'<div style="font-size:22px;line-height:1.2;font-weight:700;color:{color};">{value}</div>'
            f'<div style="margin-top:2px;font-size:12px;color:{_FG_4};">{_STATUS_LABELS[key]}</div>'
            f"</td>"
        )
    spacer = '<td width="6" style="font-size:0;line-height:0;">&nbsp;</td>'
    return f"""\
        <tr><td style="padding:16px 32px 0;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
            {spacer.join(cells)}
          </tr></table>
        </td></tr>"""


def _pass_rate_bar(counts: RunCounts) -> str:
    rate = pass_rate_of(counts)
    if rate is None:
        return f"""\
        <tr><td style="padding:16px 32px 0;font-size:13px;color:{_FG_4};">Pass rate not available — no tests ran.</td></tr>"""
    segments = []
    for key in ("passed", "failed", "timed_out", "errored"):
        value = getattr(counts, key)
        if value:
            width = max(1, round(value * 100 / counts.executed))
            segments.append(
                f'<td width="{width}%" style="height:8px;background:{_STATUS_COLORS[key][0]};'
                f'font-size:0;line-height:0;">&nbsp;</td>'
            )
    return f"""\
        <tr><td style="padding:18px 32px 0;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_TRACK};border-radius:4px;overflow:hidden;"><tr>
            {"".join(segments)}
          </tr></table>
          <p style="margin:8px 0 0;font-size:13px;color:{_FG_2};"><strong>{rate}%</strong> pass rate <span style="color:{_FG_5};">({counts.passed} of {_plural(counts.executed, 'executed test')})</span></p>
        </td></tr>"""


def _failed_table(email: RunEmail) -> str:
    failures = _ordered_failures(email)
    if not failures:
        return ""
    rows = []
    for test in failures[:MAX_LISTED_FAILURES]:
        color, wash = _STATUS_COLORS.get(test.status, _STATUS_COLORS["errored"])
        error = short_error(test.error_message)
        journey = (
            f'<div style="margin-top:2px;font-size:12px;color:{_FG_5};">{_e(test.journey)}</div>'
            if test.journey
            else ""
        )
        error_html = (
            f'<div style="margin-top:4px;font-size:13px;color:{_FG_2};word-break:break-word;">{_e(test.description)}</div>'
            if test.description
            else f'<div style="margin-top:4px;font-size:12px;color:{_FG_4};font-family:Consolas,Menlo,monospace;word-break:break-word;">{_e(error)}</div>'
            if error
            else ""
        )
        rows.append(
            f"""\
            <tr>
              <td valign="top" style="padding:10px 8px 10px 0;border-top:1px solid {_LINE};white-space:nowrap;">
                <span style="display:inline-block;padding:2px 8px;border-radius:10px;background:{wash};color:{color};font-size:11px;font-weight:700;">{_STATUS_LABELS.get(test.status, "Errored")}</span>
              </td>
              <td valign="top" style="padding:10px 8px;border-top:1px solid {_LINE};">
                <div style="font-size:14px;font-weight:600;color:{_FG};">{_e(test.name)}</div>{journey}{error_html}
              </td>
              <td valign="top" align="right" style="padding:10px 0 10px 8px;border-top:1px solid {_LINE};font-size:12px;color:{_FG_5};white-space:nowrap;">{format_duration(test.duration_ms)}</td>
            </tr>"""
        )
    more = len(failures) - MAX_LISTED_FAILURES
    more_html = (
        f'<p style="margin:8px 0 0;font-size:13px;color:{_FG_4};">+ {_plural(more, "more test")} not shown — open the report for the full list.</p>'
        if more > 0
        else ""
    )
    root_cause_html = (
        f'<p style="margin:0 0 8px;font-size:13px;color:{_FG_2};">{_e(email.root_cause)}</p>'
        if email.root_cause
        else ""
    )
    return f"""\
        <tr><td style="padding:24px 32px 0;">
          <p style="margin:0 0 6px;font-size:15px;font-weight:700;color:{_FG};">Tests that didn't pass</p>
          {root_cause_html}
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
{"".join(rows)}
          </table>
          {more_html}
        </td></tr>"""


def _details(email: RunEmail) -> str:
    target = _safe_http_url(email.target_url)
    if target:
        target_html = f'<a href="{_e(target)}" style="color:{_ACCENT};text-decoration:none;word-break:break-all;">{_e(target)}</a>'
    else:
        target_html = _e(email.target_url or "—")
    items = [
        ("Started by", _e(_started_by(email))),
        ("Trigger", "Scheduled" if email.scheduled else "Manual"),
        ("Started", _e(_format_time(email.started_at))),
        ("Duration", _e(format_duration(_run_duration_ms(email)))),
        ("Target", target_html),
    ]
    rows = "".join(
        f'<tr><td valign="top" style="padding:4px 12px 4px 0;font-size:13px;color:{_FG_5};white-space:nowrap;">{label}</td>'
        f'<td valign="top" style="padding:4px 0;font-size:13px;color:{_FG_2};">{value}</td></tr>'
        for label, value in items
    )
    return f"""\
        <tr><td style="padding:24px 32px 0;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F5F6F7;border-radius:8px;"><tr><td style="padding:12px 16px;">
            <table role="presentation" cellpadding="0" cellspacing="0">{rows}</table>
          </td></tr></table>
        </td></tr>"""


def _buttons(email: RunEmail) -> str:
    vantage = (
        f'<td style="border-radius:8px;border:1px solid {_LINE};background:#ffffff;">'
        f'<a href="{_e(run_url(email))}" style="display:inline-block;padding:11px 22px;color:{_FG_2};text-decoration:none;font-size:14px;font-weight:600;">Open in Vantage</a></td>'
    )
    if email.report_available:
        report = (
            f'<td style="border-radius:8px;background:{_ACCENT};">'
            f'<a href="{_e(report_url(email))}" style="display:inline-block;padding:12px 24px;color:#ffffff;text-decoration:none;font-size:14px;font-weight:600;">View report</a></td>'
            '<td width="10" style="font-size:0;line-height:0;">&nbsp;</td>'
        )
        note = ""
    else:
        report = ""
        note = f'<p style="margin:10px 0 0;font-size:13px;color:{_FG_4};">The detailed report isn\'t available for this run.</p>'
    return f"""\
        <tr><td style="padding:28px 32px 0;">
          <table role="presentation" cellpadding="0" cellspacing="0"><tr>{report}{vantage}</tr></table>
          {note}
        </td></tr>"""


def render_html(email: RunEmail) -> str:
    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{_e(subject_of(email))}</title></head>
<body style="margin:0;padding:0;background:{_PAGE_BG};font-family:{_FONT};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_PAGE_BG};padding:32px 12px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
        <tr><td style="background:#ffffff;border-bottom:1px solid {_LINE};padding:20px 32px;">
{EMAIL_HEADER}
        </td></tr>
{_banner(email)}
{_tiles(email.counts)}
{_pass_rate_bar(email.counts)}
{_failed_table(email)}
{_details(email)}
{_buttons(email)}
        <tr><td style="padding:28px 32px 28px;">
          <p style="margin:0;padding-top:16px;border-top:1px solid {_LINE};font-size:12px;color:{_FG_5};line-height:1.5;">{_e(_why_received(email))} Opening a link asks you to sign in to Vantage first.</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


# --- Plain text --------------------------------------------------------------


def render_text(email: RunEmail) -> str:
    counts = email.counts
    rate = pass_rate_of(counts)
    lines = [
        f"{email.app_name} · Run #{email.run_number}",
        headline_of(counts),
        "",
        f"Passed {counts.passed} · Failed {counts.failed} · Timed out {counts.timed_out}"
        f" · Errored {counts.errored} · Blocked {counts.blocked}",
        f"Pass rate: {rate}% ({counts.passed} of {_plural(counts.executed, 'executed test')})"
        if rate is not None
        else "Pass rate not available — no tests ran.",
    ]
    failures = _ordered_failures(email)
    if failures:
        lines += ["", "Tests that didn't pass:"]
        if email.root_cause:
            lines.append(email.root_cause)
        for test in failures[:MAX_LISTED_FAILURES]:
            where = f" ({test.journey})" if test.journey else ""
            lines.append(
                f"- [{_STATUS_LABELS.get(test.status, 'Errored')}] {test.name}{where}"
                f" · {format_duration(test.duration_ms)}"
            )
            error = test.description or short_error(test.error_message)
            if error:
                lines.append(f"    {error}")
        more = len(failures) - MAX_LISTED_FAILURES
        if more > 0:
            lines.append(f"+ {_plural(more, 'more test')} not shown — open the report for the full list.")
    lines += [
        "",
        f"Started by: {_started_by(email)}",
        f"Trigger: {'Scheduled' if email.scheduled else 'Manual'}",
        f"Started: {_format_time(email.started_at)}",
        f"Duration: {format_duration(_run_duration_ms(email))}",
        f"Target: {email.target_url or '—'}",
        "",
    ]
    if email.report_available:
        lines.append(f"View report: {report_url(email)}")
    else:
        lines.append("The detailed report isn't available for this run.")
    lines += [
        f"Open in Vantage: {run_url(email)}",
        "",
        f"{_why_received(email)} Opening a link asks you to sign in to Vantage first.",
    ]
    return "\n".join(lines)


def build_email(email: RunEmail) -> tuple[str, str, str]:
    """(subject, plain text, HTML)."""
    return subject_of(email), render_text(email), render_html(email)
