# 🔗 Vercel로 배포하기

목표 주소: **`https://ch-trading.vercel.app`**

> 언더스코어(`_`)는 쓸 수 없습니다. `ch_trading.vercel.app` 같은 주소는 HTTPS 인증서
> (Let's Encrypt)가 발급되지 않아 Vercel이 허용하지 않습니다. 하이픈(`-`)으로 대신합니다.
> 이름이 이미 선점돼 있으면 `chtrading`, `ch-trading-log` 등으로 지정하면 됩니다.

이 저장소는 **루트가 곧 사이트**입니다 (`index.html`, `config.js`).
빌드도, Root Directory 설정도 필요 없습니다.

```
접속 주소   https://ch-trading.vercel.app     ← Vercel (정적 호스팅, 무료)
데이터      Supabase 무료 프로젝트             ← 로그인 · 일지 DB · 차트 이미지
```

---

## ⚠️ 상업 서비스라면 유료 플랜이 필수입니다

Vercel **Hobby 플랜은 약관상 상업적 이용이 금지**됩니다. 결제를 받거나 광고·유료 구독 등
수익이 발생하는 서비스는 **Pro(멤버당 월 $20)** 로 올려야 합니다.
데이터를 맡기는 Supabase도 무료 플랜은 7일 미접속 시 프로젝트 일시정지·백업 없음·SLA 없음이라
유료 서비스 인프라로는 부적합하며 **Pro(월 $25)** 가 필요합니다.
개인용으로 먼저 써보는 단계라면 무료로 시작해도 됩니다.

## 1. Vercel 가입 (1분)

https://vercel.com → **Continue with GitHub**

## 2. 프로젝트 만들기 (1분)

1. **Add New… → Project**
2. `ch-trading` 저장소 **Import**
   - 비공개 저장소도 그대로 배포됩니다. 목록에 안 보이면 *Adjust GitHub App Permissions* 에서
     이 저장소에 접근 권한을 추가하세요.
3. **Project Name** 이 `ch-trading` 인지만 확인 (이 이름이 그대로 주소가 됩니다)
4. 나머지는 **전부 기본값 그대로** — Framework Preset은 `Other`, Build/Install Command는 비움,
   Root Directory도 건드리지 않습니다
5. **Deploy** → 30초쯤 뒤 `https://ch-trading.vercel.app` 완성

이후 `main` 브랜치에 푸시하면 자동으로 다시 배포됩니다.

## 3. Supabase 연결 (기기 간 동기화)

[`supabase/README.md`](../supabase/README.md) 대로 무료 프로젝트를 만든 뒤 둘 중 하나로 연결합니다.

- **저장소에 적어두기(권장)**: [`config.js`](../config.js) 에 Project URL과 anon key를 넣고 푸시
  → 접속하는 모든 기기에서 자동 연결
- **앱에서 입력**: 접속 후 `⋯ → ☁️ 클라우드 연결 설정` 에 붙여넣기 (그 기기에만 적용)

이메일+비밀번호 로그인은 리디렉션을 쓰지 않으므로 Supabase 쪽에 도메인을 등록할 필요가 없습니다.
연결하기 전까지는 접속한 브라우저에만 저장하는 모드로 동작합니다.

---

## 확인 사항

| 증상 | 해결 |
|---|---|
| 배포 로그에 `pip install` 이 보임 | 다른 저장소를 Import 했을 가능성 → `ch-trading` 저장소인지 확인 |
| 주소가 `ch-trading-xxxx.vercel.app` | Settings → General → **Project Name** 을 `ch-trading` 으로 변경 |
| `ch-trading` 이름을 쓸 수 없음 | 이미 선점된 이름 → `chtrading`, `ch-trading-log` 등으로 지정 |
| Import 목록에 저장소가 없음 | *Adjust GitHub App Permissions* → 이 저장소 접근 허용 |
| 접속은 되는데 로그인 화면이 안 나옴 | Supabase 연결 정보가 없는 상태 (정상) → 3번 단계 진행 |
| 수정했는데 화면이 그대로 | 강력 새로고침(Ctrl/⌘+Shift+R). 캐시는 `vercel.json` 에서 매 요청 재검증으로 설정돼 있습니다 |

## 내 도메인을 쓰고 싶다면

도메인을 구입한 뒤 Vercel → Settings → **Domains** 에 추가하면 `https://내도메인.com` 으로
접속됩니다. 도메인 구입비 외 호스팅 비용은 계속 무료입니다.
