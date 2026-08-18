# 🗄 매매일지 서버 (FastAPI + SQLite)

브라우저에만 저장되던 매매일지를 **계정 기반 서버 저장**으로 바꿔주는 백엔드입니다.
서버를 켜고 그 주소로 접속하면 프런트엔드가 자동으로 **서버 모드**로 전환되어,
PC·노트북·휴대폰 어디서 접속해도 같은 일지가 보입니다.

- 프레임워크: FastAPI + Uvicorn / 저장소: SQLite 파일 1개 (`data/journal.db`)
- 이미지도 DB에 함께 저장 → **백업은 이 파일 하나만 복사하면 끝**
- 로그인: 아이디 + 비밀번호 (PBKDF2-SHA256 20만 회 해시), HttpOnly 세션 쿠키
- 프런트엔드(`trading-journal/`)도 이 서버가 함께 서빙합니다

---

## 🚀 실행

### 로컬에서 바로
```bash
pip install -r server/requirements.txt

# 세션 서명 키 (필수는 아니지만 없으면 재시작 시 로그인이 풀립니다)
export TJ_SECRET="$(python -c 'import secrets;print(secrets.token_hex(32))')"

uvicorn server.main:app --host 0.0.0.0 --port 8000
# → http://localhost:8000  (같은 공유기의 휴대폰은 http://<PC의 IP>:8000)
```
첫 접속 시 **회원가입** 버튼으로 관리자 계정을 하나 만들면, 그 뒤로는 가입이 자동으로 닫힙니다.

### Docker
```bash
docker build -f server/Dockerfile -t maemae-journal .
docker run -d --name maemae -p 8000:8000 \
  -v "$PWD/data:/app/data" \
  -e TJ_SECRET="$(openssl rand -hex 32)" \
  maemae-journal
```

### 클라우드 (Render / Railway / Fly.io 등)
- **Build**: `pip install -r server/requirements.txt`
- **Start**: `uvicorn server.main:app --host 0.0.0.0 --port $PORT`
- 환경변수 `TJ_SECRET` 설정, `TJ_DB`는 **재배포해도 지워지지 않는 디스크**(퍼시스턴트 볼륨) 경로로 지정
  예: `TJ_DB=/var/data/journal.db`
- 무료 등급은 디스크가 초기화되는 경우가 많습니다. 볼륨을 붙이거나, 주기적으로 `/api/export` 백업을 받아두세요.

> ⚠️ 외부에 공개할 때는 **반드시 HTTPS**로 서비스하세요(리버스 프록시 또는 플랫폼 제공 TLS).
> HTTPS로 들어오면 세션 쿠키에 `Secure` 플래그가 자동으로 붙습니다.

---

## ⚙️ 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `TJ_SECRET` | (임시 생성) | 세션 쿠키 서명 키. **운영 시 필수** — 없으면 재시작마다 로그인 해제 |
| `TJ_DB` | `server/data/journal.db` | SQLite 파일 경로 |
| `TJ_ALLOW_REGISTER` | `auto` | `auto`=첫 계정만 가입 허용 / `1`=항상 허용 / `0`=차단 |
| `TJ_SESSION_DAYS` | `30` | 로그인 유지 기간(일) |
| `TJ_MAX_IMAGE_MB` | `8` | 이미지 1장 최대 용량(MB) |

`server/.env.example` 참고.

---

## 🔌 API

인증은 로그인 시 발급되는 HttpOnly 쿠키(`tj_session`)로 처리됩니다.
대화형 문서: **`/api/docs`**

| 메서드 | 경로 | 설명 |
|---|---|---|
| `GET` | `/api/health` | 서버 여부·가입 개방 상태 (프런트의 모드 자동 감지에 사용) |
| `POST` | `/api/auth/register` | 회원가입 `{username, password}` |
| `POST` | `/api/auth/login` | 로그인 |
| `POST` | `/api/auth/logout` | 로그아웃 |
| `POST` | `/api/auth/password` | 비밀번호 변경 (`username` 자리에 현재 비밀번호) |
| `GET` | `/api/me` | 로그인한 계정 정보 |
| `GET` | `/api/entries` | 내 일지 전체 |
| `PUT` | `/api/entries/{id}` | 일지 생성/수정 (upsert) |
| `DELETE` | `/api/entries/{id}` | 일지 삭제 (연결된 이미지도 함께 삭제) |
| `DELETE` | `/api/entries` | 내 일지 전체 삭제 |
| `POST` | `/api/images` | 이미지 업로드 (`file`, 선택 `thumb`) |
| `GET` | `/api/images/{id}` · `/api/images/{id}/thumb` | 원본 · 썸네일 (본인 것만) |
| `GET` | `/api/export` | 전체 백업 JSON (이미지 base64 포함) |
| `POST` | `/api/import` | 백업 JSON 복원 (같은 ID는 덮어쓰기) |

모든 데이터 API는 **로그인한 사용자 본인의 행만** 조회·수정합니다.

---

## 💾 백업

- 파일 통째로: 서버를 잠시 멈추고 `server/data/journal.db*` 복사 (WAL 파일 포함)
- 앱에서: `⋯ → 백업 내보내기(JSON)` — 서버 모드에서는 서버가 만든 백업을 내려받습니다
- 복원: `⋯ → 백업 불러오기` (또는 `POST /api/import`)

브라우저 저장 모드에서 쓰던 기록도 같은 JSON 백업으로 그대로 서버에 옮길 수 있습니다.

---

## 🔎 동작 방식 (프런트엔드 연동)

`trading-journal/index.html` 은 시작할 때 `GET /api/health` 를 한 번 호출합니다.

- 응답이 오면 → **서버 모드** (로그인 화면 표시, 이후 모든 저장/조회가 API 경유)
- 응답이 없으면(파일로 직접 열기, GitHub Pages 등) → **브라우저 저장 모드** (IndexedDB)

로그인 화면 아래의 *"서버 없이 이 브라우저에만 저장하며 쓰기"* 로 언제든 로컬 모드로 쓸 수도 있습니다.
