# ☁️ 무료 클라우드로 매매일지 쓰기 (Supabase + GitHub Pages)

**비용 0원 · 신용카드 불필요 · 어느 기기에서든 같은 기록.**
서버를 직접 돌리지 않고, 무료 서비스 두 개만 연결하면 됩니다.

```
[ 내 브라우저 ] ──HTTPS──> [ Supabase ]  로그인 · 일지 DB · 차트 이미지 저장
       ↑
   화면(정적 파일)은 GitHub Pages 가 무료로 서빙
```

소요 시간 약 10분. 아래 순서대로 따라 하시면 됩니다.

---

## 1단계 — Supabase 프로젝트 만들기 (3분)

1. https://supabase.com 에서 GitHub 계정 등으로 로그인 (카드 등록 없음)
2. **New project** 클릭
   - Name: `trading-journal` (아무 이름이나 가능)
   - Database Password: 아무 값이나 지정하고 **따로 보관** (앱에서는 쓰지 않지만 DB 직접 접속 시 필요)
   - Region: **Northeast Asia (Seoul)** 을 고르면 가장 빠릅니다
3. 프로젝트 생성이 끝날 때까지 1~2분 기다립니다

## 2단계 — 테이블·이미지 저장소 만들기 (1분)

1. 왼쪽 메뉴 **SQL Editor** → **New query**
2. 이 저장소의 [`supabase/schema.sql`](schema.sql) 내용을 통째로 붙여넣고 **Run**
3. `Success. No rows returned` 이 나오면 완료입니다
   (일지 테이블 + 본인 것만 보이게 하는 보안 정책 + 비공개 이미지 버킷이 한 번에 만들어집니다)

## 3단계 — 이메일 로그인 바로 쓰게 하기 (1분)

1. 왼쪽 메뉴 **Authentication** → **Sign In / Providers** → **Email**
2. **Confirm email** 을 **끕니다** (혼자 쓰는 용도라 메일 확인 절차가 필요 없습니다)
3. 저장

> 메일 확인을 켜둔 채로 쓰고 싶다면 그대로 두어도 됩니다. 가입 후 메일함의 링크를 눌러야 로그인됩니다.

## 4단계 — 연결 정보 확인 (1분)

**Project Settings → API** 에서 두 값을 복사합니다.

| 항목 | 예시 |
|---|---|
| **Project URL** | `https://abcdefghijkl.supabase.co` |
| **anon public** key | `eyJhbGciOiJIUzI1NiIsInR5cCI6...` |

> `anon` 키는 공개되어도 되는 값입니다. 실제 데이터 접근은 2단계에서 만든 RLS 정책이 막습니다.
> 반면 `service_role` 키는 **절대** 앱이나 저장소에 넣지 마세요.

## 5단계 — 앱에 연결 (1분)

두 가지 방법 중 하나를 고르면 됩니다.

**(A) 저장소에 적어두기 — 모든 기기에서 자동 연결 (추천)**
[`trading-journal/config.js`](../trading-journal/config.js) 를 열어 값을 채우고 커밋합니다.

```js
window.TJ_CONFIG = {
  supabaseUrl: "https://abcdefghijkl.supabase.co",
  supabaseAnonKey: "eyJhbGciOiJIUzI1NiIsInR5cCI6..."
};
```

**(B) 앱 화면에서 입력 — 저장소를 건드리지 않음**
앱 우측 상단 `⋯` → **☁️ 클라우드 연결 설정** 에서 두 값을 붙여넣습니다.
(입력한 기기에만 저장되므로, 새 기기에서는 한 번씩 입력해야 합니다.)

## 6단계 — 화면을 웹에 올리기 (GitHub Pages, 2분)

1. 이 저장소 **Settings → Pages**
2. **Source: GitHub Actions** 선택 (포함된 워크플로가 `trading-journal/` 폴더를 배포합니다)
3. 잠시 후 `https://<사용자명>.github.io/posco-ppi-agent/` 로 접속됩니다

이제 그 주소를 휴대폰·회사 PC 어디서 열어도 **이메일 + 비밀번호로 로그인**하면 같은 일지가 보입니다.
첫 접속 시 **회원가입** 버튼으로 계정을 만드세요.

---

## 무료 한도와 주의점

| 항목 | 무료 한도 | 체감 |
|---|---|---|
| 데이터베이스 | 500 MB | 일지 텍스트는 사실상 무제한 |
| 이미지 저장소 | 1 GB | 압축된 차트 캡처 기준 약 3,000장 |
| 전송량 | 월 5 GB | 혼자 쓰기에 충분 |

- **7일간 접속이 없으면 프로젝트가 일시정지**됩니다. 데이터는 지워지지 않고, Supabase 대시보드에서
  한 번 눌러 되살리면 됩니다. 자동으로 막고 싶다면 저장소 Settings → Secrets 에
  `SUPABASE_URL`, `SUPABASE_ANON_KEY` 를 등록하세요 —
  [`.github/workflows/supabase-keepalive.yml`](../.github/workflows/supabase-keepalive.yml) 가 주 1회 깨워줍니다.
- 이미지는 업로드 전 최대 2000px JPEG로 자동 압축되어 올라갑니다.
- 백업은 앱의 `⋯ → 백업 내보내기(JSON)` 로 언제든 받아둘 수 있습니다 (이미지 포함).

## 문제가 생기면

| 증상 | 원인과 해결 |
|---|---|
| 로그인 시 `Invalid login credentials` | 이메일/비밀번호 오타, 또는 아직 가입 전 → **회원가입** 버튼 사용 |
| 가입 후 "메일함에서 확인 링크를…" | 3단계의 **Confirm email** 이 켜져 있음 → 끄거나 메일 확인 |
| 일지는 보이는데 이미지가 안 뜸 | 2단계 SQL 중 storage 정책 부분이 실행되지 않음 → `schema.sql` 다시 실행 |
| `relation "entries" does not exist` | 2단계 SQL을 실행하지 않음 |
| 며칠 만에 접속했더니 오류 | 프로젝트 일시정지 → Supabase 대시보드에서 **Restore** |

## 자체 서버로 옮기고 싶다면

`server/` 의 FastAPI + SQLite 서버도 그대로 남아 있습니다. 그 주소로 접속하면 앱이 자동으로
서버 모드로 전환됩니다. 데이터 이동은 `백업 내보내기` → 다른 쪽에서 `백업 불러오기` 로 하면 됩니다.
자세한 내용은 [`server/README.md`](../server/README.md).
