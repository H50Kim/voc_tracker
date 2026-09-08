# VoC Tracker — Apps Script 웹앱

Node 서버 없이 Google이 호스팅합니다. 데이터는 자동 생성되는 스프레드시트에 저장되고, 기존 VoC Tracker Google Form 응답은 익명 ID로 게시판에 반영됩니다.

## 수동 배포

1. [script.google.com](https://script.google.com)에서 새 프로젝트 만들기
2. 프로젝트 이름을 `VoC Tracker`로 변경
3. 기본 `코드.gs` 내용을 `Code.gs`로 교체
4. **파일 → 새로 만들기 → HTML** 이름을 `Index`로 두고 `Index.html` 내용 붙여넣기
5. **프로젝트 설정 → 스크립트 속성**은 첫 실행 시 자동 생성됨 (`ANON_SECRET`, `SPREADSHEET_ID`)
6. 편집기에서 `setup` 함수를 선택하고 **실행** → 권한 허용 (시트, 폼)
7. **배포 → 새 배포 → 유형: 웹 앱**
   - 실행 계정: `나`
   - 액세스 권한: `도메인의 모든 사용자` (사내) 또는 `모든 사용자`
8. 배포 URL을 팀에 공유

첫 실행 후 Drive에 `VoC Tracker Data` 시트가 생깁니다. Users / Opinions / Votes 탭이 저장소입니다.

## 이 프로젝트에 올리기

대상: [VoC Tracker Apps Script](https://script.google.com/home/projects/1qMmwILfqKxntP5yQGrPUFEmYUrsCE5f_1odTu5TrEsseOpXyUsN6VM0Z/edit)

`apps-script/.clasp.json`에 위 프로젝트 ID가 연결되어 있습니다.

```bash
cd apps-script
npx @google/clasp login
npx @google/clasp push --force
npx @google/clasp deploy
```

또는 에디터에서 `Code.gs`와 HTML 파일 `Index`에 로컬 파일을 붙여넣으면 됩니다.

## 동작

- 로그인: 이메일 또는 사내 Google 계정 자동 인식
- 익명 ID: 이메일 HMAC → `VOC-XXXXXXXX` (이메일은 화면에 없음)
- 글/투표: 이메일당 각 1회
- Google Form ID `12jEITV1PpsrhIaDekBKpE5uo5nnQSuZdHye6PPUvxOE` 응답을 읽어 익명 ID로 표시
- 웹앱에서 글을 쓰면 시트에 저장하고, 가능하면 같은 폼에도 응답을 남김

폼 소유자 계정으로 전환해 스크립트를 만들어야 폼 응답을 읽을 수 있습니다.
