# 🚀 Streamlit Cloud 배포 가이드 (5분 완성)

이 문서는 **초보자도 따라하면 공개 URL이 만들어지는** 단계별 가이드입니다.

---

## 📋 전체 흐름

```
[1] GitHub에 코드 업로드  →  [2] Streamlit Cloud 연결  →  [3] 시크릿 입력  →  [4] 배포 완료 🎉
```

---

## 1️⃣ GitHub에 코드 업로드

### ① GitHub 계정 준비
- 계정 없으면 [github.com/signup](https://github.com/signup) 에서 가입 (무료)

### ② 빈 저장소 만들기
1. [github.com](https://github.com) 로그인 → 우측 상단 **`+` → New repository**
2. 입력:
   - **Repository name**: `posco-ppi-agent`
   - **Public** 선택 (⚠️ Streamlit Cloud 무료 플랜은 Public만 지원)
   - README, .gitignore, license **체크하지 말기** (우리는 이미 있음)
3. **Create repository** 클릭

### ③ 로컬에서 GitHub로 푸시

프로젝트 폴더에서 터미널 열고:

```bash
git init
git add .
git commit -m "Initial commit: PPI adjustment AI agent"
git branch -M main
git remote add origin https://github.com/<YOUR_ID>/posco-ppi-agent.git
git push -u origin main
```

처음 푸시 시 GitHub 로그인 창이 뜨면:
- 사용자명: GitHub ID
- **비밀번호 대신 Personal Access Token(PAT) 입력**
  - PAT 발급: [github.com/settings/tokens](https://github.com/settings/tokens) → Generate new token (classic) → `repo` 권한 체크 → 토큰 복사

완료되면 브라우저에서 저장소 새로고침 → 파일들이 올라온 것 확인!

---

## 2️⃣ Streamlit Cloud 연결

### ① 로그인
[share.streamlit.io](https://share.streamlit.io) 접속 → **Sign in with GitHub** 클릭 → GitHub 계정으로 바로 로그인 (별도 가입 X)

### ② 새 앱 생성
1. 우측 상단 **Create app** 또는 **New app** 클릭
2. 입력:
   - **Repository**: `<YOUR_ID>/posco-ppi-agent`
   - **Branch**: `main`
   - **Main file path**: `app.py`
   - **App URL** (선택): 원하는 서브도메인 입력 (예: `posco-ppi-agent`)

---

## 3️⃣ 시크릿 입력 (LIVE 모드 사용 시)

배포 화면 하단 **Advanced settings** 클릭 → **Secrets** 영역에 TOML 형식으로 입력:

```toml
ECOS_API_KEY = "발급받은_ECOS_키"
OPENAI_API_KEY = "발급받은_OpenAI_키"
```

> 💡 **DEMO 모드만 쓰실 경우 이 단계는 건너뛰어도 됩니다.**
> 앱 내에서 "🎬 DEMO 모드"를 선택하면 API 키 없이 전체 기능 동작.

---

## 4️⃣ 배포!

**Deploy** 버튼 클릭 → 2~3분 대기 → 다음과 같은 URL이 생성됩니다:

```
https://<your-app-name>.streamlit.app
```

🎉 이 URL을 교육 참가자들에게 공유하면 브라우저만 있으면 누구나 접속 가능!

---

## 🔄 코드 수정 후 업데이트

로컬에서 코드 수정 → 저장 → 터미널에서:

```bash
git add .
git commit -m "Update: 기능 추가/수정"
git push
```

Streamlit Cloud가 **자동으로 감지**하고 몇 초 내에 재배포합니다. 별도 작업 불필요!

---

## ❓ 자주 발생하는 문제

### Q1. "ModuleNotFoundError: No module named 'xxx'" 에러
→ `requirements.txt` 누락. 필요한 라이브러리 추가 후 git push.

### Q2. Streamlit Cloud에서 배포 실패
→ **Manage app** → **Logs** 탭에서 에러 메시지 확인.
- 보통 라이브러리 버전 충돌이거나 파일 경로 오타.

### Q3. API 키가 적용되지 않음
→ Streamlit Cloud의 **Settings → Secrets** 에 입력했는지 확인.
→ secrets.toml 형식 주의 (값은 반드시 따옴표 `" "` 로 감싸기).

### Q4. GitHub push 시 "Permission denied"
→ Personal Access Token이 만료됐거나 `repo` 권한 누락.
→ [github.com/settings/tokens](https://github.com/settings/tokens) 에서 재발급.

### Q5. Private 저장소로 배포하고 싶음
→ Streamlit Cloud 무료 플랜은 Public만 지원. Team 플랜(유료) 필요.
→ 대안: [Hugging Face Spaces](https://huggingface.co/spaces) 도 무료로 Private 지원.

---

## 🏢 사내 배포 대안 (보안 중시 환경)

GitHub/Streamlit Cloud가 외부 서비스라 사내 정책상 사용이 어렵다면:

### 옵션 1: 사내 서버에 직접 배포
```bash
# 사내 리눅스 서버에서
git clone <사내_GitLab>/posco-ppi-agent.git
cd posco-ppi-agent
pip install -r requirements.txt
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```
사내망에서 `http://<서버IP>:8501` 로 접속.

### 옵션 2: Docker 컨테이너화
```dockerfile
# Dockerfile 예시
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0"]
```

### 옵션 3: 사내 GitLab CI/CD 연동
GitLab Runner로 자동 빌드/배포 파이프라인 구축.

---

## 🎬 배포 완료 후 시연 시나리오

교육 시 추천 시연 순서:

1. **모드 전환 시연** — 사이드바에서 DEMO ↔ LIVE 전환
2. **Tab 1 AI Agent** — "2020년 1월 800억원 압연기를 2026년 1월로 환산" 입력
3. **Tab 2 설비별 조회** — 기계 > 특수목적용 > 금속가공기계 선택
4. **Tab 3 다중 비교** — 철강1차제품 vs 변압기 vs 시멘트 비교 (정규화 ON)
5. **Tab 4 수동 계산기** — 빠른 환산 시연

---

## 📞 도움이 필요하면

- 이 앱 관련 문의: 교육 담당자
- Streamlit 공식 문서: [docs.streamlit.io](https://docs.streamlit.io)
- ECOS API 문의: [ecos.bok.or.kr](https://ecos.bok.or.kr/api/)

---

배포 완료되면 URL을 팀에 공유하고 🎉 축하하세요!
