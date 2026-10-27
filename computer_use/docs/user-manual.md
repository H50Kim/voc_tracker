# Computer Use 사용자 매뉴얼 (Windows)

VOC Tracker 저장소의 `computer_use` 패키지 — 로컬·Edge·원격 데스크톱 화면 자동화 GUI 및 폐루프 에이전트.

## 설치

### Windows (권장)

```powershell
cd computer_use
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[gui,windows,dev]"
python -m computer_use.gui.app
```

### Linux (개발·CI)

GUI 없이 테스트만:

```bash
cd computer_use
pip install -e ".[dev]"
pytest
```

PySide6 GUI는 Windows에서 설치하세요 (`pip install -e ".[gui,windows]"`).

## CU-5 Windows 검증 (자동 실행)

물리 Windows PC에서 **자동화 가능한 CU-5 항목**을 한 번에 실행합니다 (pytest, import·캡처·Win32 열거 스모크, JSON/MD 리포트).

```powershell
cd computer_use\scripts
.\run_cu5_validation.ps1
```

옵션:

| 플래그 | 설명 |
|--------|------|
| `-OutputDir <path>` | `cu5-validation-report.json` / `.md` 출력 위치 (기본: 현재 디렉터리) |
| `-SkipInstall` | venv/`pip install` 생략 (이미 설치된 경우) |
| `-SkipSmoke` | repo `scripts\run_windows_smoke.ps1` 생략 |
| `-IncludeGui` | Qt offscreen GUI 컨트롤러 pytest 추가 |

리포트 붙여넣기 블록 (Coordinator 채팅용):

```powershell
python -m computer_use.validation.cu5_runner --from-report .\cu5-validation-report.json --print-paste-block
```

또는:

```powershell
.\merge_cu5_report_to_store.ps1 -ReportJson .\cu5-validation-report.json
```

**수동 sign-off:** W-* / GL-* / 대화형 GUI 단계는 리포트에서 `Pending`으로 남습니다. Project store [`windows-validation-checklist.md`](/cursor/stores/self/docs/windows-validation-checklist.md)와 [`windows-validation-results.md`](/cursor/stores/self/docs/windows-validation-results.md)에 증거를 기록하세요.

## 실행 모드

| 모드 | 설명 |
|------|------|
| **로컬 (Local)** | 일반 Windows 앱 창 목록 → 영역 선택 → 폐루프 또는 Teach & Replay |
| **브라우저 (Edge)** | **새 Edge launch 금지** — 이미 실행 중인 Edge 창만 attach. SSO/MFA 화면 감지 시 자동 일시정지 |
| **원격 (RDP/Citrix/Horizon)** | 원격 클라이언트 창 + 내부 상대 영역. 원격 VM 에이전트 설치 없음, 비전 기반 루프 |

## GUI 단축 동작

- **시작 / 일시정지 / 재개 / 중지** — 폐루프 에이전트 실행 제어
- **긴급 중지** — 협력적 중지 (입력 즉시 하드 킬은 Phase 5 이후에도 제한적)
- **창 목록 새로고침** — 모드별 창 목록 갱신
- **영역 선택** — 캡처 미리보기 위 드래그로 검증·실행 영역 지정

## Teach & Replay (Phase 5)

1. **Teach & Replay 모드** 체크 → 폐루프 Start 대신 워크플로 패널 사용
2. **녹화 시작/중지** — 클릭·특수키(Enter/Tab/Esc 등) 기록. **비밀번호·MFA·OTP·PIN은 저장하지 않음** (`[REDACTED]`)
3. **저장/불러오기** — `~/.computer_use/workflows/*.json` (로컬 JSON)
4. **재생** — 단계마다 화면 fingerprint 검증 후 상대 좌표·패치 템플릿으로 클릭 해석
5. **Glean 도움말** — 실행 중 Edge에서 Glean 탭 제목 힌트만 제안; 검색 결과 HTML/텍스트는 **참고용 파싱만** (위험 단계 자동 실행 없음)

## Ollama (로컬 LLM, Phase 4)

- Planner/Perception용 **Ollama** 연동은 `agents/pipeline.py` 스텁 단계 — 폐루프는 Phase 1 어댑터(결정론)로 동작
- Windows에서 Ollama 설치 후 향후 버전에서 `OLLAMA_HOST` 등 환경 변수로 연결 예정
- Executor는 LLM 없이 좌표·정책 기반 유지

## Ledger (실행 기록)

- 기본 경로: `~/.computer_use/agent_ledger.json`
- 미해결 `pending_operation`은 **자동 재실행하지 않음** — GUI 기동 시 로그에 표시
- 재시작 후에도 ledger 파일을 수동 백업 권장

## 안전·정책

- 인증 우회, 쿠키/localStorage/session 토큰 추출, CDP attach(기본 차단) 금지
- Browser 모드: Playwright/Selenium **launch()** 금지
- Teach & Replay JSON에도 시크릿 필드 저장 금지 (자동 삭제)
- 위험 동작은 폐루프 **승인 다이얼로그** (타임아웃 auto-deny는 미구현)

## 문제 해결

| 증상 | 조치 |
|------|------|
| Edge 창이 목록에 없음 | Edge를 먼저 실행; Browser 모드에서 새로고침 |
| MFA 후 재개 안 됨 | Edge에서 로그인 완료 → **재개** (REOBSERVE) |
| Remote 영역 오류 | 드래그 영역이 RDP/Citrix 창과 겹치는지 확인 |
| Replay 화면 불일치 | 해상도/DPI 변경 시 워크플로 재녹화 |
| pytest Linux 실패 | `pytest -m "not windows"` (기본). Windows 전용은 `-m windows` |
| pynput/evdev Linux 빌드 오류 | Windows 실기 또는 `dry_run` 테스트만 사용 |

## Windows 수동 검증

Project store [`windows-validation-checklist.md`](/cursor/stores/self/docs/windows-validation-checklist.md) — **W-* 항목은 사용자 PC에서만 sign-off** (에이전트가 Pass 주장하지 않음).

## 관련 문서

- 패키지 README: `computer_use/README.md`
- 구현 계획: Project store `docs/implementation-plan.md`
- 설계 갭: Project store `docs/closed-loop-design-gaps.md`
