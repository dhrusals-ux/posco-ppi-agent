# 🚀 서버 배포 + DB 구축 가이드

매매일지를 **어디서든 접속 가능한 서비스**로 올리는 방법입니다.
세 가지 방식이 있고, 셋 다 이 저장소 안에 설정 파일이 준비돼 있습니다.

| 방식 | DB | 서버 | 월 비용 | 이럴 때 |
|---|---|---|---|---|
| **A. Supabase 직결** | Supabase PostgreSQL | 없음 (정적 호스팅) | 0원 | **지금 쓰는 방식.** 가장 단순, 서버 관리 불필요 |
| **B. Render + PostgreSQL** | Render 또는 Supabase PostgreSQL | Render (Docker) | 0원 | 자체 계정 시스템·API가 필요할 때 |
| **C. 내 서버 (docker compose)** | PostgreSQL 컨테이너 | 내 VPS/PC | 서버값만 | 데이터를 완전히 내 손에 두고 싶을 때 |

> 어느 방식이든 화면(`index.html`)은 그대로입니다. 프런트는 `/api/health` 응답 유무로
> **서버 모드 / 브라우저 저장 모드**를 스스로 판단합니다.

---

## A. Supabase 직결 (서버 없이)

프런트가 Supabase의 인증·DB·스토리지 REST API를 직접 호출합니다. 서버 코드를 띄우지 않습니다.

1. https://supabase.com 에서 프로젝트 생성 (Region: **Northeast Asia (Seoul)**)
2. SQL Editor 에 [`supabase/schema.sql`](../supabase/schema.sql) 전체를 붙여넣고 실행
   → `entries` 테이블 + RLS 정책 + 비공개 `charts` 버킷이 한 번에 만들어집니다
3. Project Settings → API 에서 **Project URL** 과 **anon public key** 복사
4. [`trading-journal/config.js`](../trading-journal/config.js) 에 붙여넣기
5. Vercel / GitHub Pages 등 정적 호스팅에 올리기 → [`DEPLOY-VERCEL.md`](DEPLOY-VERCEL.md)

**RLS(행 수준 보안)** 덕분에 anon key 가 공개돼도 남의 일지는 읽히지 않습니다.
정책은 `auth.uid() = user_id` 한 줄이고, 차트 이미지도 `charts/<내 uid>/...` 경로만 접근됩니다.

---

## B. Render + PostgreSQL (자체 서버)

[`render.yaml`](../render.yaml) 블루프린트가 **웹 서비스 + PostgreSQL** 을 한 번에 만듭니다.

1. https://dashboard.render.com/blueprints → **New Blueprint Instance**
2. 이 저장소를 고르면 `render.yaml` 이 자동 인식됨 → **Apply**
3. 3~5분 뒤 `https://ch-trading.onrender.com` 같은 주소가 나옵니다
4. 첫 접속에서 만든 계정이 **관리자 계정**이 되고, 이후 가입은 자동으로 닫힙니다

`TJ_SECRET` 은 Render 가 자동 생성하고, `DATABASE_URL` 은 함께 만들어진 DB가 자동 주입합니다.

> **무료 플랜 주의 2가지**
> - 15분간 요청이 없으면 서버가 잠듭니다 → 다음 접속이 30초쯤 느립니다.
> - Render 무료 PostgreSQL 은 **30일 뒤 만료**됩니다. 계속 쓸 거라면 `render.yaml` 의
>   `databases:` 블록을 지우고, `DATABASE_URL` 에 **Supabase/Neon 무료 PostgreSQL URL** 을 직접 넣으세요.

### Supabase PostgreSQL 을 서버의 DB로 쓰기
Supabase 대시보드 → Project Settings → **Database** → Connection string → **URI** 복사
(연결 수가 적은 무료 플랜이라 **6543 포트 Connection pooler** 를 권장)

```
DATABASE_URL=postgresql://postgres.xxxx:비밀번호@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres?sslmode=require
```

이 값을 Render(또는 Fly) 환경변수에 넣으면 끝입니다. 테이블은 서버가 처음 뜰 때 스스로 만듭니다.

### Fly.io 로 할 때
[`fly.toml`](../fly.toml) 이 준비돼 있습니다. 도쿄 리전, 미사용 시 자동 정지 설정입니다.
```bash
fly launch --no-deploy --copy-config
fly secrets set TJ_SECRET="$(openssl rand -hex 32)"
fly postgres create --name ch-trading-db --region nrt
fly postgres attach ch-trading-db     # DATABASE_URL 자동 주입
fly deploy
```

---

## C. 내 서버에서 (docker compose)

[`docker-compose.yml`](../docker-compose.yml) 하나로 **앱 + PostgreSQL 16 + 데이터 볼륨**이 뜹니다.

```bash
git clone <이 저장소> && cd <저장소>
echo "TJ_SECRET=$(openssl rand -hex 32)"      >> .env
echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)" >> .env
docker compose up -d
# → http://localhost:8000
```

외부 공개 시에는 앞단에 Caddy/Nginx 를 두고 **HTTPS** 를 붙이세요.
(HTTPS 로 들어오면 세션 쿠키에 `Secure` 플래그가 자동으로 붙습니다.)

```bash
docker compose logs -f app                     # 로그
docker compose exec db pg_dump -U tj tjdb > backup.sql   # 백업
docker compose down                            # 중지 (데이터는 볼륨에 남음)
```

---

## 🗄 DB 스키마

서버 모드(B·C)에서 서버가 기동할 때 자동으로 만드는 테이블입니다. 수동 마이그레이션은 필요 없습니다.

| 테이블 | 내용 | 핵심 컬럼 |
|---|---|---|
| `users` | 계정 | `id`(PK), `username`(unique), `pw_hash`(PBKDF2-SHA256 20만 회), `created_at` |
| `entries` | 일지 | `id`(PK), `user_id`(FK, CASCADE), `date`, `symbol`, `pnl`, `pnl_pct`, `tags`, `comment`, `lesson`, `is_lesson`, `is_market`, `align_from`, `align_to`, `rating`, `images` |
| `images` | 차트 이미지 | `id`(PK), `user_id`(FK, CASCADE), `mime`, `data`(BYTEA/BLOB), `thumb`, `created_at` |

- 인덱스: `idx_entries_user_date (user_id, date)`, `idx_images_user (user_id)`
- 모든 조회·수정 쿼리에 `WHERE user_id = ?` 가 붙습니다 → **계정 간 데이터 격리**
- 컬럼이 늘어나면 `migrate_db()` 가 기존 DB에 `ALTER TABLE ... ADD COLUMN` 으로 더합니다
- A 방식(Supabase 직결)은 같은 구조를 `entries` 테이블 + `charts` 스토리지 버킷으로 씁니다

DB 종류는 코드가 아니라 **환경변수 하나**로 정해집니다.

| `DATABASE_URL` | 동작 |
|---|---|
| 없음 | SQLite 파일 (`TJ_DB`, 기본 `server/data/journal.db`) |
| `postgresql://...` | PostgreSQL (커넥션 풀 사용) |

지금 어떤 DB로 돌고 있는지는 이렇게 확인합니다:
```bash
curl -s https://내주소/api/health
# {"ok":true,"mode":"server","db":"postgres","registrationOpen":false}
```

---

## 🔁 이사 / 백업

- **브라우저 → 서버**, **SQLite → PostgreSQL**, **서버 → 서버** 모두 같은 방법입니다.
  옛 쪽에서 `⋯ → 백업 내보내기(JSON)`, 새 쪽에서 `⋯ → 백업 불러오기`.
  (API로는 `GET /api/export` → `POST /api/import`. 이미지도 base64로 함께 실려 갑니다.)
- PostgreSQL 통째 백업: `pg_dump "$DATABASE_URL" > backup.sql`
- 복원: `psql "$DATABASE_URL" < backup.sql`

---

## ✅ 공개 전 점검

- [ ] `TJ_SECRET` 을 **직접** 설정했다 (없으면 재시작마다 로그인이 풀림)
- [ ] HTTPS 로 서비스한다
- [ ] 관리자 계정을 만든 뒤 `TJ_ALLOW_REGISTER` 가 닫혀 있다 (`auto` 기본값이면 자동)
- [ ] 백업을 한 번 받아 **복원까지** 해봤다
- [ ] `DATABASE_URL`·비밀번호를 저장소에 커밋하지 않았다 (`.env` 는 `.gitignore` 대상)
- [ ] 유료로 판매한다면 [`docs/legal/`](legal/) 의 약관·개인정보처리방침을 **변호사 검토 후** 게시했다
