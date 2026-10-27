from __future__ import annotations

import json
from pathlib import Path

from computer_use.validation.cu5_report import (
    ALL_CU5_IDS,
    CheckStatus,
    Cu5Check,
    Cu5Report,
    MANUAL_GUI_IDS,
    PytestSummary,
    default_pending_checks,
    load_report,
    map_pytest_to_checks,
    parse_junit_xml,
    parse_pytest_summary,
    render_paste_block,
    upsert_check,
    write_reports,
)
from computer_use.validation.cu5_runner import run_cu5_validation


def test_parse_pytest_summary_last_line_wins():
    text = """
============================= test session starts ==============================
collected 10 items
......
======================== 89 passed, 2 skipped in 1.40s =========================
"""
    summary = parse_pytest_summary(text)
    assert summary.passed == 89
    assert summary.skipped == 2
    assert summary.failed == 0


def test_parse_pytest_summary_with_failures():
    text = "======= 1 failed, 88 passed, 2 skipped in 2.0s ======="
    summary = parse_pytest_summary(text)
    assert summary.failed == 1
    assert summary.passed == 88
    assert not summary.ok


def test_default_pending_covers_manual_gui_ids():
    checks = default_pending_checks()
    ids = {c.id for c in checks}
    assert ids == set(ALL_CU5_IDS)
    for check in checks:
        if check.id in MANUAL_GUI_IDS:
            assert check.status == CheckStatus.PENDING
            assert check.reason == "requires_interactive_gui"


def test_map_pytest_marks_section_11_2_and_5():
    report = Cu5Report(checks=default_pending_checks())
    not_windows = PytestSummary(passed=89, skipped=2, exit_code=0)
    windows = PytestSummary(passed=7, exit_code=0)
    map_pytest_to_checks(report, not_windows=not_windows, windows=windows, install_ok=True)
    assert report.check_by_id("§11-1").status == CheckStatus.PASS
    assert report.check_by_id("§11-2").status == CheckStatus.PASS
    assert report.check_by_id("§11-2b").status == CheckStatus.PASS
    assert report.check_by_id("§11-5").status == CheckStatus.PASS
    assert report.check_by_id("W-06").status == CheckStatus.PASS
    assert report.check_by_id("§11-8").status == CheckStatus.PENDING


def test_automated_ok_ignores_pending():
    report = Cu5Report(checks=default_pending_checks())
    map_pytest_to_checks(
        report,
        not_windows=PytestSummary(passed=10, exit_code=0),
        windows=PytestSummary(passed=7, exit_code=0),
        install_ok=True,
    )
    assert report.automated_ok()


def test_automated_ok_fails_on_fail_status():
    report = Cu5Report(checks=default_pending_checks())
    map_pytest_to_checks(
        report,
        not_windows=PytestSummary(passed=0, failed=1, exit_code=1),
        windows=PytestSummary(passed=7, exit_code=0),
        install_ok=True,
    )
    assert not report.automated_ok()


def test_render_paste_block_includes_auto_lines():
    report = Cu5Report(
        meta={"generated_at": "2026-10-26T12:00:00+00:00", "hostname": "PC", "platform": "Windows", "commit": "abc", "branch": "main"},
        checks=default_pending_checks(),
        pytest_not_windows=PytestSummary(passed=89, skipped=2, exit_code=0),
        pytest_windows=PytestSummary(passed=7, exit_code=0),
    )
    block = render_paste_block(report)
    assert "auto-not-windows: Pass" in block
    assert "89 passed" in block
    assert "§11-8" not in block


def test_write_and_load_report_roundtrip(tmp_path: Path):
    report = Cu5Report(
        meta={"generated_at": "2026-10-26T12:00:00+00:00"},
        checks=default_pending_checks(),
        pytest_not_windows=PytestSummary(passed=1, exit_code=0),
    )
    json_path, _md = write_reports(report, tmp_path)
    loaded = load_report(json_path)
    assert loaded.pytest_not_windows
    assert loaded.pytest_not_windows.passed == 1


def test_parse_junit_xml_counts(tmp_path: Path):
    xml = tmp_path / "junit.xml"
    xml.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="3" failures="1" skipped="1">
    <testcase classname="a" name="ok"/>
    <testcase classname="b" name="skip"><skipped/></testcase>
    <testcase classname="c" name="fail"><failure message="x"/></testcase>
  </testsuite>
</testsuites>
""",
        encoding="utf-8",
    )
    summary = parse_junit_xml(xml)
    assert summary.passed == 1
    assert summary.skipped == 1
    assert summary.failed == 1


def test_run_cu5_validation_linux_smoke(tmp_path: Path):
    pkg_root = Path(__file__).resolve().parents[1]
    log = tmp_path / "pytest-not-windows.log"
    log.write_text("89 passed, 2 skipped in 1.0s\n", encoding="utf-8")
    report = run_cu5_validation(
        pkg_root=pkg_root,
        output_dir=tmp_path,
        install_ok=True,
        pytest_not_windows_log=log,
        pytest_not_windows_exit=0,
        pytest_windows_log=None,
    )
    assert (tmp_path / "cu5-validation-report.json").is_file()
    data = json.loads((tmp_path / "cu5-validation-report.json").read_text(encoding="utf-8"))
    assert data["automated_ok"] is True
    pending = [c for c in data["checks"] if c["status"] == "Pending"]
    assert any(c["id"] == "GL-01" for c in pending)


def test_upsert_check_replaces_by_id():
    report = Cu5Report(checks=default_pending_checks())
    upsert_check(report, Cu5Check(id="§11-2", status=CheckStatus.FAIL, message="nope"))
    assert report.check_by_id("§11-2").status == CheckStatus.FAIL

