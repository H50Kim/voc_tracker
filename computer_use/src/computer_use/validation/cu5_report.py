from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

# Checklist IDs in stable order (see Project store windows-validation-checklist.md).
ALL_CU5_IDS: tuple[str, ...] = (
    "§11-1",
    "§11-2",
    "§11-2b",
    "§11-3",
    "§11-4",
    "§11-5",
    "§11-6",
    "§11-7",
    "§11-8",
    "§11-9",
    "§11-10",
    "W-01",
    "W-02",
    "W-03",
    "W-04",
    "W-05",
    "W-06",
    "W-07",
    "W-08",
    "W-09",
    "W-10",
    "W-11",
    "GL-01",
    "GL-02",
    "GL-03",
    "GL-04",
    "GL-05",
    "GL-06",
    "GL-07",
    "GL-08",
    "GL-09",
    "GL-10",
    "GL-11",
)

MANUAL_GUI_IDS: frozenset[str] = frozenset(
    {
        "§11-4",
        "§11-7",
        "§11-8",
        "§11-9",
        "§11-10",
        "W-01",
        "W-02",
        "W-03",
        "W-04",
        "W-05",
        "W-07",
        "W-08",
        "W-09",
        "W-10",
        "W-11",
        "GL-01",
        "GL-02",
        "GL-03",
        "GL-04",
        "GL-05",
        "GL-06",
        "GL-07",
        "GL-08",
        "GL-09",
        "GL-10",
        "GL-11",
    }
)

PENDING_REASON_INTERACTIVE = "requires_interactive_gui"


class CheckStatus(str, Enum):
    PASS = "Pass"
    FAIL = "Fail"
    PENDING = "Pending"
    SKIP = "Skip"
    NA = "N/A"


@dataclass
class PytestSummary:
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    exit_code: int | None = None
    source: str = ""

    @property
    def ok(self) -> bool:
        return self.failed == 0 and self.errors == 0 and (self.exit_code in (None, 0))

    def summary_line(self) -> str:
        return f"{self.passed} passed, {self.failed} failed, {self.skipped} skipped"


@dataclass
class Cu5Check:
    id: str
    status: CheckStatus
    message: str = ""
    evidence: str = ""
    reason: str = ""


@dataclass
class Cu5Report:
    meta: dict[str, Any] = field(default_factory=dict)
    checks: list[Cu5Check] = field(default_factory=list)
    pytest_not_windows: PytestSummary | None = None
    pytest_windows: PytestSummary | None = None
    smoke_script: dict[str, Any] | None = None

    def check_by_id(self, check_id: str) -> Cu5Check | None:
        for item in self.checks:
            if item.id == check_id:
                return item
        return None

    def automated_ok(self) -> bool:
        for item in self.checks:
            if item.status == CheckStatus.FAIL:
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        data = {
            "meta": self.meta,
            "automated_ok": self.automated_ok(),
            "checks": [asdict(c) | {"status": c.status.value} for c in self.checks],
        }
        if self.pytest_not_windows:
            data["pytest_not_windows"] = asdict(self.pytest_not_windows)
        if self.pytest_windows:
            data["pytest_windows"] = asdict(self.pytest_windows)
        if self.smoke_script:
            data["smoke_script"] = self.smoke_script
        return data


_SUMMARY_LINE_RE = re.compile(
    r"=+\s*(?P<body>.+?)\s+in\s+[\d.]+\s*s\s*=+",
    re.IGNORECASE,
)
_COUNT_RE = re.compile(r"(?P<n>\d+)\s+(?P<label>passed|failed|skipped|error|errors)", re.IGNORECASE)


def parse_pytest_summary(text: str) -> PytestSummary:
    """Parse pytest terminal summary line(s) from captured log output."""
    summary = PytestSummary(source="pytest_log")
    if not text:
        return summary
    bodies = [m.group("body") for m in _SUMMARY_LINE_RE.finditer(text)]
    if not bodies:
        bodies = [text.splitlines()[-1]] if text.splitlines() else []
    if not bodies:
        return summary
    body = bodies[-1]
    for match in _COUNT_RE.finditer(body):
        count = int(match.group("n"))
        label = match.group("label").lower()
        if label == "passed":
            summary.passed = count
        elif label == "failed":
            summary.failed = count
        elif label == "skipped":
            summary.skipped = count
        elif label.startswith("error"):
            summary.errors = count
    return summary


def parse_junit_xml(path: Path) -> PytestSummary:
    """Aggregate pass/fail/skip counts from a JUnit XML file."""
    summary = PytestSummary(source=f"junit:{path.name}")
    if not path.is_file():
        return summary
    root = ElementTree.parse(path).getroot()
    if root.tag == "testsuite":
        suites = [root]
    else:
        suites = root.findall("testsuite")
    for suite in suites:
        for case in suite.findall("testcase"):
            skipped = case.find("skipped")
            failure = case.find("failure")
            error = case.find("error")
            if skipped is not None:
                summary.skipped += 1
            elif failure is not None or error is not None:
                summary.failed += 1
            else:
                summary.passed += 1
    return summary


def merge_pytest_summary(
    log_summary: PytestSummary,
    junit_summary: PytestSummary | None,
) -> PytestSummary:
    """Prefer JUnit counts when present; keep exit_code from log side."""
    if junit_summary and (junit_summary.passed + junit_summary.failed + junit_summary.skipped) > 0:
        merged = junit_summary
        merged.exit_code = log_summary.exit_code
        merged.source = f"{junit_summary.source};{log_summary.source}"
        return merged
    return log_summary


def default_pending_checks() -> list[Cu5Check]:
    checks: list[Cu5Check] = []
    for check_id in ALL_CU5_IDS:
        if check_id in MANUAL_GUI_IDS:
            checks.append(
                Cu5Check(
                    id=check_id,
                    status=CheckStatus.PENDING,
                    reason=PENDING_REASON_INTERACTIVE,
                    message="Manual interactive GUI or E2E step",
                )
            )
        else:
            checks.append(
                Cu5Check(
                    id=check_id,
                    status=CheckStatus.PENDING,
                    message="Not evaluated yet",
                )
            )
    return checks


def upsert_check(report: Cu5Report, check: Cu5Check) -> None:
    for idx, existing in enumerate(report.checks):
        if existing.id == check.id:
            report.checks[idx] = check
            return
    report.checks.append(check)


def map_pytest_to_checks(
    report: Cu5Report,
    *,
    not_windows: PytestSummary,
    windows: PytestSummary | None,
    install_ok: bool,
) -> None:
    upsert_check(
        report,
        Cu5Check(
            id="§11-1",
            status=CheckStatus.PASS if install_ok else CheckStatus.FAIL,
            message="venv + pip install -e .[gui,windows,dev]" if install_ok else "Install step failed or skipped",
            evidence="run_cu5_validation.ps1 install",
        ),
    )
    upsert_check(
        report,
        Cu5Check(
            id="§11-2",
            status=CheckStatus.PASS if not_windows.ok else CheckStatus.FAIL,
            message=not_windows.summary_line(),
            evidence=not_windows.source,
        ),
    )
    if windows is not None:
        has_windows_run = (
            windows.passed + windows.failed + windows.skipped > 0
            or windows.exit_code is not None
        )
        if has_windows_run:
            upsert_check(
                report,
                Cu5Check(
                    id="§11-2b",
                    status=CheckStatus.PASS if windows.ok else CheckStatus.FAIL,
                    message=windows.summary_line(),
                    evidence=windows.source,
                ),
            )
        elif sys.platform == "win32":
            upsert_check(
                report,
                Cu5Check(
                    id="§11-2b",
                    status=CheckStatus.FAIL,
                    message="pytest -m windows was not executed",
                    evidence="missing log/junit",
                ),
            )
    policy_ok = not_windows.ok and not_windows.passed > 0
    upsert_check(
        report,
        Cu5Check(
            id="§11-5",
            status=CheckStatus.PASS if policy_ok else CheckStatus.FAIL,
            message="Derived from pytest suite (includes test_policy_guard)",
            evidence="pytest -m \"not windows\"",
        ),
    )
    upsert_check(
        report,
        Cu5Check(
            id="W-06",
            status=CheckStatus.PASS if policy_ok else CheckStatus.FAIL,
            message="Policy launch/CDP checks via pytest",
            evidence="tests/test_policy_guard.py",
        ),
    )


def render_markdown(report: Cu5Report) -> str:
    lines = [
        "# CU-5 validation report",
        "",
        f"- Generated: {report.meta.get('generated_at', '')}",
        f"- Platform: {report.meta.get('platform', '')}",
        f"- Automated OK: **{report.automated_ok()}**",
        "",
        "## Pytest",
        "",
    ]
    if report.pytest_not_windows:
        pw = report.pytest_not_windows
        lines.append(f"- `pytest -m \"not windows\"`: {pw.summary_line()} (exit {pw.exit_code})")
    if report.pytest_windows:
        pw = report.pytest_windows
        lines.append(f"- `pytest -m windows`: {pw.summary_line()} (exit {pw.exit_code})")
    if report.smoke_script:
        lines.append(f"- `run_windows_smoke.ps1`: exit {report.smoke_script.get('exit_code')}")
    lines.extend(["", "## Checks", "", "| ID | Status | Message | Evidence |", "|----|--------|---------|----------|"])
    for item in report.checks:
        lines.append(
            f"| {item.id} | {item.status.value} | {item.message} | {item.evidence} |"
        )
    lines.append("")
    pending = [c for c in report.checks if c.status == CheckStatus.PENDING]
    if pending:
        lines.append("## Manual follow-up (Pending)")
        lines.append("")
        for item in pending:
            reason = item.reason or item.message
            lines.append(f"- **{item.id}**: {reason}")
        lines.append("")
    return "\n".join(lines)


def render_paste_block(report: Cu5Report) -> str:
    """Format matching cu5-results-paste-template.md for chat paste."""
    lines: list[str] = []
    meta_date = report.meta.get("generated_at", "")[:10]
    lines.append(f"meta-date: {meta_date} | |")
    lines.append(f"meta-pc: {report.meta.get('hostname', '')} | {report.meta.get('platform', '')} |")
    lines.append(f"meta-commit: {report.meta.get('commit', '')} | {report.meta.get('branch', '')} |")
    lines.append("")

    if report.pytest_not_windows:
        pw = report.pytest_not_windows
        status = "Pass" if pw.ok else "Fail"
        lines.append(
            f"auto-not-windows: {status} | pytest-not-windows.log | {pw.summary_line()}"
        )
    if report.pytest_windows:
        pw = report.pytest_windows
        status = "Pass" if pw.ok else "Fail"
        lines.append(f"auto-windows: {status} | pytest-windows.log | {pw.summary_line()}")
    if report.smoke_script is not None:
        ok = report.smoke_script.get("exit_code") == 0
        lines.append(f"auto-smoke: {'Pass' if ok else 'Fail'} | run_windows_smoke.txt |")

    lines.append("")
    for item in report.checks:
        if item.id.startswith("§11") or item.id.startswith("W-") or item.id.startswith("GL-"):
            if item.status == CheckStatus.PENDING:
                continue
            lines.append(f"{item.id}: {item.status.value} | {item.evidence} | {item.message}")
    return "\n".join(lines)


def write_reports(report: Cu5Report, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "cu5-validation-report.json"
    md_path = output_dir / "cu5-validation-report.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report) + "\n", encoding="utf-8")
    return json_path, md_path


def load_report(path: Path) -> Cu5Report:
    data = json.loads(path.read_text(encoding="utf-8"))
    checks = [
        Cu5Check(
            id=c["id"],
            status=CheckStatus(c["status"]),
            message=c.get("message", ""),
            evidence=c.get("evidence", ""),
            reason=c.get("reason", ""),
        )
        for c in data.get("checks", [])
    ]
    report = Cu5Report(meta=data.get("meta", {}), checks=checks)
    if "pytest_not_windows" in data:
        report.pytest_not_windows = PytestSummary(**data["pytest_not_windows"])
    if "pytest_windows" in data:
        report.pytest_windows = PytestSummary(**data["pytest_windows"])
    if "smoke_script" in data:
        report.smoke_script = data["smoke_script"]
    return report
