from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from computer_use.validation.cu5_report import (
    CheckStatus,
    Cu5Check,
    Cu5Report,
    PytestSummary,
    default_pending_checks,
    load_report,
    map_pytest_to_checks,
    merge_pytest_summary,
    parse_junit_xml,
    parse_pytest_summary,
    render_paste_block,
    upsert_check,
    write_reports,
)

PENDING_REASON_INTERACTIVE = "requires_interactive_gui"


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            cwd=Path(__file__).resolve().parents[4],
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except OSError:
        pass
    return ""


def _git_branch() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            cwd=Path(__file__).resolve().parents[4],
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except OSError:
        pass
    return ""


def _run_pytest_marker(
    pkg_root: Path,
    marker: str,
    junit_path: Path | None,
) -> tuple[int, str]:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-m",
        marker,
        "--tb=short",
    ]
    if junit_path:
        cmd.extend(["--junitxml", str(junit_path)])
    proc = subprocess.run(
        cmd,
        cwd=pkg_root,
        capture_output=True,
        text=True,
        check=False,
    )
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    return proc.returncode, text


def _check_import_smoke() -> Cu5Check:
    try:
        import computer_use  # noqa: F401
        from computer_use.core.window_enum import get_window_enumerator  # noqa: F401

        return Cu5Check(
            id="import-smoke",
            status=CheckStatus.PASS,
            message="import computer_use OK",
            evidence="python -c import smoke",
        )
    except Exception as exc:  # noqa: BLE001
        return Cu5Check(
            id="import-smoke",
            status=CheckStatus.FAIL,
            message=str(exc),
            evidence="python import",
        )


def _check_screen_capture() -> Cu5Check:
    if sys.platform != "win32":
        return Cu5Check(
            id="§11-3",
            status=CheckStatus.SKIP,
            message="Screen capture smoke runs on Windows only",
        )
    try:
        from computer_use.core.capture import ScreenCapture

        cap = ScreenCapture()
        w, h = cap.primary_monitor_size()
        img = cap.capture_screen()
        ok = w > 0 and h > 0 and img.width > 0 and img.height > 0
        return Cu5Check(
            id="§11-3",
            status=CheckStatus.PASS if ok else CheckStatus.FAIL,
            message=f"primary {w}x{h}, capture {img.width}x{img.height}",
            evidence="ScreenCapture.capture_screen()",
        )
    except Exception as exc:  # noqa: BLE001
        return Cu5Check(
            id="§11-3",
            status=CheckStatus.FAIL,
            message=str(exc),
            evidence="ScreenCapture",
        )


def _check_window_enum() -> Cu5Check:
    if sys.platform != "win32":
        return Cu5Check(
            id="§11-6",
            status=CheckStatus.SKIP,
            message="Win32 enumeration requires Windows",
        )
    from computer_use.core.window_enum import get_window_enumerator

    wins = get_window_enumerator().list_windows()
    if not wins:
        return Cu5Check(
            id="§11-6",
            status=CheckStatus.FAIL,
            message="No windows returned",
            evidence="list_windows()",
        )
    if len(wins) == 1 and "(stub)" in wins[0].title:
        return Cu5Check(
            id="§11-6",
            status=CheckStatus.FAIL,
            message="Stub enumerator only (pywin32 missing?)",
            evidence=wins[0].title,
        )
    real = [w for w in wins if w.handle > 0]
    return Cu5Check(
        id="§11-6",
        status=CheckStatus.PASS if real else CheckStatus.FAIL,
        message=f"{len(real)} windows with handle > 0",
        evidence=", ".join(w.title[:40] for w in real[:3]),
    )


def _run_policy_pytest(pkg_root: Path) -> Cu5Check:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_policy_guard.py",
            "-q",
            "--tb=line",
        ],
        cwd=pkg_root,
        capture_output=True,
        text=True,
        check=False,
    )
    summary = parse_pytest_summary(proc.stdout + proc.stderr)
    summary.exit_code = proc.returncode
    ok = proc.returncode == 0 and summary.failed == 0
    return Cu5Check(
        id="§11-5",
        status=CheckStatus.PASS if ok else CheckStatus.FAIL,
        message=summary.summary_line() or f"exit {proc.returncode}",
        evidence="pytest tests/test_policy_guard.py",
    )


def _run_gui_pytest_offscreen(pkg_root: Path) -> list[Cu5Check]:
    if sys.platform != "win32":
        return []
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_gui_closed_loop_controller.py",
            "-q",
            "--tb=line",
        ],
        cwd=pkg_root,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    summary = parse_pytest_summary(proc.stdout + proc.stderr)
    ok = proc.returncode == 0
    status = CheckStatus.PASS if ok else CheckStatus.FAIL
    return [
        Cu5Check(
            id="GL-10",
            status=status,
            message=f"Headless GUI controller tests: {summary.summary_line()}",
            evidence="pytest test_gui_closed_loop_controller (QT offscreen)",
        )
    ]


def run_cu5_validation(
    *,
    pkg_root: Path,
    output_dir: Path,
    install_ok: bool = True,
    pytest_not_windows_log: Path | None = None,
    pytest_windows_log: Path | None = None,
    junit_not_windows: Path | None = None,
    junit_windows: Path | None = None,
    smoke_exit_code: int | None = None,
    pytest_not_windows_exit: int | None = None,
    pytest_windows_exit: int | None = None,
    run_local_pytest: bool = False,
    include_gui: bool = False,
) -> Cu5Report:
    report = Cu5Report(
        meta={
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "platform": platform.platform(),
            "hostname": platform.node(),
            "commit": _git_head(),
            "branch": _git_branch(),
        },
        checks=default_pending_checks(),
    )

    not_windows = PytestSummary()
    windows = PytestSummary()

    if run_local_pytest and sys.platform == "win32":
        junit_nw = junit_not_windows or (output_dir / "junit-not-windows.xml")
        junit_w = junit_windows or (output_dir / "junit-windows.xml")
        code_nw, log_nw = _run_pytest_marker(pkg_root, "not windows", junit_nw)
        code_w, log_w = _run_pytest_marker(pkg_root, "windows", junit_w)
        if pytest_not_windows_log:
            pytest_not_windows_log.write_text(log_nw, encoding="utf-8")
        if pytest_windows_log:
            pytest_windows_log.write_text(log_w, encoding="utf-8")
        not_windows = merge_pytest_summary(parse_pytest_summary(log_nw), parse_junit_xml(junit_nw))
        not_windows.exit_code = code_nw
        windows = merge_pytest_summary(parse_pytest_summary(log_w), parse_junit_xml(junit_w))
        windows.exit_code = code_w
    else:
        if pytest_not_windows_log and pytest_not_windows_log.is_file():
            log_text = pytest_not_windows_log.read_text(encoding="utf-8", errors="replace")
            not_windows = merge_pytest_summary(
                parse_pytest_summary(log_text),
                parse_junit_xml(junit_not_windows) if junit_not_windows else None,
            )
        elif junit_not_windows and junit_not_windows.is_file():
            not_windows = parse_junit_xml(junit_not_windows)
        if pytest_not_windows_exit is not None:
            not_windows.exit_code = pytest_not_windows_exit
            if pytest_not_windows_exit != 0 and not_windows.failed == 0:
                not_windows.failed = max(not_windows.failed, 1)
        if pytest_windows_log and pytest_windows_log.is_file():
            log_text = pytest_windows_log.read_text(encoding="utf-8", errors="replace")
            windows = merge_pytest_summary(
                parse_pytest_summary(log_text),
                parse_junit_xml(junit_windows) if junit_windows else None,
            )
        elif junit_windows and junit_windows.is_file():
            windows = parse_junit_xml(junit_windows)
        if pytest_windows_exit is not None:
            windows.exit_code = pytest_windows_exit
            if pytest_windows_exit != 0 and windows.failed == 0:
                windows.failed = max(windows.failed, 1)

    report.pytest_not_windows = not_windows
    report.pytest_windows = windows
    if smoke_exit_code is not None:
        report.smoke_script = {"exit_code": smoke_exit_code}

    map_pytest_to_checks(
        report,
        not_windows=not_windows,
        windows=windows,
        install_ok=install_ok,
    )

    import_check = _check_import_smoke()
    if import_check.status == CheckStatus.FAIL:
        upsert_check(report, import_check)

    upsert_check(report, _check_screen_capture())
    upsert_check(report, _check_window_enum())

    if sys.platform == "win32":
        policy = _run_policy_pytest(pkg_root)
        upsert_check(report, policy)
        upsert_check(
            report,
            Cu5Check(
                id="W-06",
                status=policy.status,
                message=policy.message,
                evidence=policy.evidence,
            ),
        )

    if include_gui:
        for gui_check in _run_gui_pytest_offscreen(pkg_root):
            upsert_check(report, gui_check)

    write_reports(report, output_dir)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CU-5 structured Windows validation runner")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory for cu5-validation-report.{json,md}",
    )
    parser.add_argument(
        "--pkg-root",
        type=Path,
        default=None,
        help="computer_use package root (default: parent of src/)",
    )
    parser.add_argument("--install-ok", action="store_true", help="Mark §11-1 install step successful")
    parser.add_argument("--install-failed", action="store_true", help="Mark §11-1 install step failed")
    parser.add_argument("--pytest-not-windows-log", type=Path, default=None)
    parser.add_argument("--pytest-windows-log", type=Path, default=None)
    parser.add_argument("--junit-not-windows", type=Path, default=None)
    parser.add_argument("--junit-windows", type=Path, default=None)
    parser.add_argument("--smoke-exit-code", type=int, default=None)
    parser.add_argument("--pytest-not-windows-exit", type=int, default=None)
    parser.add_argument("--pytest-windows-exit", type=int, default=None)
    parser.add_argument(
        "--run-pytest",
        action="store_true",
        help="Run pytest markers from this process (Windows only; PS script usually runs pytest)",
    )
    parser.add_argument("--include-gui", action="store_true", help="Run minimal Qt offscreen GUI pytest")
    parser.add_argument(
        "--print-paste-block",
        action="store_true",
        help="Print cu5-results-paste-template compatible block to stdout",
    )
    parser.add_argument(
        "--from-report",
        type=Path,
        default=None,
        help="Load existing JSON report (for paste block only)",
    )
    args = parser.parse_args(argv)

    if args.from_report:
        report = load_report(args.from_report)
        if args.print_paste_block:
            print(render_paste_block(report))
        return 0 if report.automated_ok() else 1

    pkg_root = args.pkg_root
    if pkg_root is None:
        pkg_root = Path(__file__).resolve().parents[3]

    install_ok = True
    if args.install_failed:
        install_ok = False
    elif args.install_ok:
        install_ok = True

    report = run_cu5_validation(
        pkg_root=pkg_root,
        output_dir=args.output_dir,
        install_ok=install_ok,
        pytest_not_windows_log=args.pytest_not_windows_log,
        pytest_windows_log=args.pytest_windows_log,
        junit_not_windows=args.junit_not_windows,
        junit_windows=args.junit_windows,
        smoke_exit_code=args.smoke_exit_code,
        pytest_not_windows_exit=args.pytest_not_windows_exit,
        pytest_windows_exit=args.pytest_windows_exit,
        run_local_pytest=args.run_pytest,
        include_gui=args.include_gui,
    )

    if args.print_paste_block:
        print(render_paste_block(report))

    return 0 if report.automated_ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())
