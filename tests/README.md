# 🧪 검증 (브라우저 자동화)

실제 Chromium으로 앱을 조작해 **세 가지 저장 방식**(브라우저 IndexedDB / 자체 FastAPI 서버 /
Supabase 클라우드)에서 같은 기능이 동작하는지 확인합니다.

```bash
bash tests/run.sh              # 전체
bash tests/run.sh market-tab   # 하나만
```

준비물: `python3` (+ `fastapi`, `uvicorn`), `node`, Chromium.
Chromium 경로는 `TJ_CHROME` 로 지정할 수 있습니다 (기본: `/opt/pw-browsers/...`).
`playwright-core` 가 없으면 실행 시 자동 설치합니다.

## 무엇을 확인하나

| 파일 | 확인 내용 |
|---|---|
| `local-basic` | 일지 작성·이미지 첨부·수정·삭제·검색·백업, 새로고침 후 유지 |
| `local-views` | 일별/주별/월간/통계 전환, 라이트·다크, 전체 삭제, 빈 상태 |
| `market-tab` | 장중 배열 전환 기록, 전환 매트릭스, 필터, 통계 미오염 (3개 모드) |
| `lessons-tab` | 시사점 누적·검색·수정, 마크다운 내보내기 (3개 모드) |
| `image-size` | 차트 원본 해상도 표시, 크게/작게 토글, 라이트박스 |
| `quality-ux` | 삭제 되돌리기, 라이트박스 확대·이동, 빈 상태 버튼, PWA 매니페스트 |
| `performance` | 2,300건 주입 후 각 화면 렌더 시간과 목록 페이징 |
| `account-delete` | 회원탈퇴 시 계정·일지·이미지 완전 삭제, 재로그인 거부 |
| `server-mode` | 자체 서버 가입·로그인, 다른 기기 동기화, 권한 격리 |
| `cloud-mode` | Supabase(목 서버) 가입·로그인, 토큰 갱신, 기기 간 동기화 |
| `embed-themes` | 아티팩트 임베드 환경에서 시스템 라이트/다크 대응 |
| `embed-downloads` | 임베드 환경의 파일 저장 경로(호스트 API) 폴백 |
| `standalone-tree` | 독립 저장소 트리에서 화면만 서빙되고 소스가 노출되지 않음 |

`standalone-tree` 는 `python tools/make-standalone.py` 로 생성한 트리에 별도 서버를 띄워야 하므로
기본 실행에서 제외됩니다.

## 참고

- `tests/mock-supabase.py` 는 Supabase의 인증·PostgREST·스토리지 응답을 최소한으로 흉내 내는
  테스트용 서버입니다. 실제 Supabase 프로젝트 없이 클라이언트 코드 경로를 검증합니다.
- 생성물(스크린샷·임시 DB·픽스처)은 `tests/.tmp/` 에 쌓이며 커밋되지 않습니다.
- 미로그인 401, 오답 로그인 400 같은 **의도된 오류는 실패로 보지 않습니다**
  (`tests/lib/env.mjs` 의 `BENIGN` 목록).
