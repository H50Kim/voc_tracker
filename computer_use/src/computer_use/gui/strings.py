"""KO/EN UI strings."""

from computer_use.modes.types import AutomationMode

STRINGS = {
    "app_title": {"ko": "Computer Use 자동화", "en": "Computer Use Automation"},
    "mode": {"ko": "모드", "en": "Mode"},
    "refresh_windows": {"ko": "창 목록 새로고침", "en": "Refresh windows"},
    "region_hint": {
        "ko": "영역: 캡처 후 검증 (Phase 1)",
        "en": "Region: capture & validate (Phase 1)",
    },
    "start": {"ko": "시작", "en": "Start"},
    "pause": {"ko": "일시정지", "en": "Pause"},
    "resume": {"ko": "재개", "en": "Resume"},
    "stop": {"ko": "중지", "en": "Stop"},
    "natural_language": {"ko": "자연어 목표", "en": "Natural language goal"},
    "run_log": {"ko": "실행 로그", "en": "Run log"},
    "emergency_stop": {"ko": "긴급 중지", "en": "Emergency stop"},
    "confirm_title": {"ko": "동작 승인", "en": "Confirm action"},
    "confirm_action": {
        "ko": "다음 동작을 실행할까요?\n동작: {description}\n목표: {goal}",
        "en": "Execute this action?\nAction: {description}\nGoal: {goal}",
    },
    "goal_required": {"ko": "자연어 목표를 입력하세요.", "en": "Enter a natural language goal."},
    "ai_model_panel": {
        "ko": "로컬 LLM (Ollama) — 상태/권장 모델",
        "en": "Local LLM (Ollama) — status & recommendation",
    },
    "paused_status": {"ko": "일시정지됨", "en": "Paused"},
    "resumed_status": {"ko": "재개됨", "en": "Resumed"},
    "browser_warning": {
        "ko": "Browser 모드: 기존 Edge 창만 사용 (launch/CDP/cookie 추출 금지)",
        "en": "Browser mode: existing Edge only (no launch/CDP/cookie harvest)",
    },
    "browser_no_edge": {
        "ko": "(실행 중인 Microsoft Edge 창 없음)",
        "en": "(No running Microsoft Edge windows)",
    },
    "browser_pick_edge": {
        "ko": "Browser 모드: Edge 창을 목록에서 선택하세요.",
        "en": "Browser mode: select an Edge window from the list.",
    },
    "auth_pause_status": {
        "ko": "인증 대기 — Edge에서 로그인/MFA를 완료한 뒤 재개하세요.",
        "en": "Auth pause — complete sign-in/MFA in Edge, then Resume.",
    },
    "auth_pause_log": {
        "ko": "MFA/로그인 감지: 자동 일시정지 (세션/쿠키 추출 없음)",
        "en": "Sign-in/MFA detected: auto-paused (no session/cookie harvest)",
    },
    "auth_resume_status": {
        "ko": "재개됨 — 화면 재관찰(REOBSERVE)",
        "en": "Resumed — re-observe (REOBSERVE)",
    },
    "remote_warning": {
        "ko": "Remote 모드: RDP/Citrix/Horizon 클라이언트 창만 사용 (원격 VM 에이전트 설치 없음, 비전 루프)",
        "en": "Remote mode: RDP/Citrix/Horizon client window only (no remote agent; visual loop)",
    },
    "remote_no_client": {
        "ko": "(실행 중인 원격 데스크톱 클라이언트 창 없음)",
        "en": "(No remote desktop client windows)",
    },
    "remote_pick_client": {
        "ko": "Remote 모드: RDP/Citrix/Horizon 창을 목록에서 선택하세요.",
        "en": "Remote mode: select a remote client window from the list.",
    },
    "remote_region_outside": {
        "ko": "드래그 영역이 원격 창과 겹치지 않습니다.",
        "en": "Drag region does not overlap the remote client window.",
    },
    "remote_pause_status": {
        "ko": "원격 세션 일시정지 — 연결/잠금/최소화/검은 화면을 확인한 뒤 재개하세요.",
        "en": "Remote session paused — fix disconnect/lock/minimize/black screen, then Resume.",
    },
    "remote_stop_status": {
        "ko": "원격 세션 중지됨 — 연결 끊김 등으로 실행을 종료했습니다.",
        "en": "Remote session stopped — disconnected or unusable session.",
    },
    "teach_replay_enable": {
        "ko": "Teach & Replay 모드 (폐루프 대신 워크플로 녹화/재생)",
        "en": "Teach & Replay mode (record/replay workflow instead of closed-loop)",
    },
    "teach_replay_group": {
        "ko": "워크플로",
        "en": "Workflow",
    },
    "teach_record_start": {"ko": "녹화 시작", "en": "Start record"},
    "teach_record_stop": {"ko": "녹화 중지", "en": "Stop record"},
    "teach_workflow_name": {"ko": "워크플로 이름", "en": "Workflow name"},
    "teach_save": {"ko": "저장…", "en": "Save…"},
    "teach_load": {"ko": "불러오기…", "en": "Load…"},
    "teach_replay": {"ko": "재생", "en": "Replay"},
    "teach_glean": {"ko": "Glean 도움말", "en": "Glean helper"},
    "teach_recording_on": {"ko": "녹화 중 (클릭·특수키; 비밀번호/MFA/OTP는 저장하지 않음)", "en": "Recording (clicks/special keys; no password/MFA/OTP stored)"},
    "teach_recording_off": {
        "ko": "녹화 종료 — {count}단계",
        "en": "Recording stopped — {count} step(s)",
    },
    "teach_loaded": {
        "ko": "불러옴: {path} ({count}단계)",
        "en": "Loaded: {path} ({count} step(s))",
    },
    "teach_replay_ok": {"ko": "재생 완료", "en": "Replay finished"},
    "teach_replay_fail": {"ko": "재생 실패 (화면 검증 또는 단계 오류)", "en": "Replay failed (screen verify or step error)"},
    "teach_mode_blocks_closed_loop": {
        "ko": "Teach & Replay 모드에서는 폐루프 Start를 사용할 수 없습니다.",
        "en": "Closed-loop Start is disabled in Teach & Replay mode.",
    },
}

MODE_LABELS = {
    AutomationMode.LOCAL: {"ko": "로컬", "en": "Local"},
    AutomationMode.BROWSER: {"ko": "브라우저 (Edge)", "en": "Browser (Edge)"},
    AutomationMode.REMOTE: {"ko": "원격 (RDP/Citrix)", "en": "Remote (RDP/Citrix)"},
}


def t(key: str, lang: str = "ko") -> str:
    entry = STRINGS.get(key, {})
    return entry.get(lang) or entry.get("en") or key
