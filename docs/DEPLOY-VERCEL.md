# 🔗 짧은 주소로 배포하기 (Vercel)

목표 주소: **`https://chuse.vercel.app`**
(이름이 이미 쓰이고 있으면 `chuse-journal`, `chuse-log` 처럼 바꾸면 됩니다)

이 앱의 화면은 정적 파일 하나(`trading-journal/index.html`)라서 빌드 과정 없이 그대로 올라갑니다.
데이터(로그인·일지·이미지)는 Supabase가 맡으므로, Vercel에는 **화면만** 올립니다.

```
접속 주소   https://chuse.vercel.app        ← Vercel (정적 호스팅, 무료)
데이터      Supabase 무료 프로젝트           ← 로그인 · DB · 차트 이미지
```

---

## 1. Vercel 가입 (1분)

https://vercel.com → **Continue with GitHub** (신용카드 불필요, Hobby 플랜 무료)

## 2. 프로젝트 만들기 (2분)

1. **Add New… → Project**
2. `posco-ppi-agent` 저장소 **Import**
3. 설정 화면에서 아래 두 가지만 바꿉니다

   | 항목 | 값 |
   |---|---|
   | **Project Name** | `chuse` ← 이 이름이 그대로 `chuse.vercel.app` 이 됩니다 |
   | **Root Directory** | `trading-journal` ← **꼭 지정하세요** |

   > Root Directory를 지정하지 않으면 저장소 루트의 `requirements.txt`(Streamlit 앱용)를 보고
   > Python 프로젝트로 잘못 인식합니다. `trading-journal` 폴더만 올리면 정적 사이트로 처리됩니다.
   > Framework Preset은 **Other**(자동으로 잡힙니다), Build Command·Install Command는 비워 둡니다.

4. **Deploy** → 30초쯤 뒤 `https://chuse.vercel.app` 완성

## 3. 배포할 브랜치 지정

지금 코드는 `claude/trading-journal-website-wo5tru` 브랜치에 있습니다. 둘 중 하나를 선택하세요.

- **간단**: Vercel → Settings → **Git** → *Production Branch* 를
  `claude/trading-journal-website-wo5tru` 로 변경 (병합 없이 바로 배포)
- **정석**: 이 브랜치를 `main` 으로 병합 → 기본값(main) 그대로 사용

이후에는 해당 브랜치에 푸시할 때마다 Vercel이 자동으로 다시 배포합니다.

## 4. Supabase 연결

[`supabase/README.md`](../supabase/README.md) 대로 프로젝트를 만든 뒤, 둘 중 하나로 연결합니다.

- **저장소에 적어두기(권장)**: `trading-journal/config.js` 에 Project URL과 anon key를 넣고 푸시
  → 접속하는 모든 기기에서 자동 연결
- **앱에서 입력**: 접속 후 `⋯ → ☁️ 클라우드 연결 설정` 에 붙여넣기 (그 기기에만 적용)

이메일+비밀번호 로그인은 리디렉션을 쓰지 않으므로 Supabase 쪽에 도메인을 따로 등록할 필요가 없습니다.

---

## 확인 사항

| 증상 | 해결 |
|---|---|
| 배포 로그에 `pip install` 이 보임 | Root Directory가 `trading-journal` 로 지정되지 않음 → Settings → General 에서 수정 후 Redeploy |
| 주소가 `chuse-xxxx.vercel.app` | 프로젝트 이름이 다르게 잡힘 → Settings → General → Project Name 을 `chuse` 로 변경 |
| `chuse` 이름을 쓸 수 없음 | 이미 선점된 이름 → `chuse-journal`, `chuse-log` 등으로 지정 |
| 접속은 되는데 로그인 화면이 안 나옴 | Supabase 연결 정보 없음 → 4번 단계 확인 (연결 전에는 브라우저 저장 모드로 동작) |
| 수정했는데 화면이 그대로 | 브라우저 강력 새로고침(Ctrl/⌘+Shift+R). 캐시는 `vercel.json` 에서 이미 매 요청 재검증으로 설정해 두었습니다 |

## 나중에 진짜 내 도메인을 쓰고 싶다면

도메인(연 1~2만원대)을 사서 Vercel → Settings → **Domains** 에 추가하면
`https://내도메인.com` 으로 접속됩니다. 도메인 구입비 외 호스팅 비용은 계속 무료입니다.
