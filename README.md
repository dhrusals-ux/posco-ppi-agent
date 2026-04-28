# 📊 투자비 물가보정 AI Agent

포스코 투자엔지니어링실 교육용 **Streamlit 데모 앱**.
한국은행 ECOS API의 생산자물가지수(PPI)를 활용해 과거 투자비를 현재가치로 자동 환산합니다.

![badge](https://img.shields.io/badge/Streamlit-1.32+-FF4B4B?logo=streamlit)
![badge](https://img.shields.io/badge/Python-3.10+-blue?logo=python)

---

## ✨ 주요 기능

### 🎬 DEMO 모드 (API 키 불필요!)
- 가상 PPI 데이터로 **모든 기능을 즉시 체험**
- 교육/발표 시 네트워크 문제 없이 안정적 시연

### 🏦 LIVE 모드 (실제 API 연동)
- 한국은행 ECOS API로 실제 생산자물가지수 조회
- OpenAI GPT (선택) 로 자연어 파싱 고도화

### 📑 4개 핵심 탭
1. **🤖 AI Agent 환산** — 자연어 요청 → 자동 환산 → 마크다운 보고서 생성
2. **🔍 설비별 PPI 조회** — 기계/전기/토건/계측 설비별 세분화 PPI 추이
3. **📈 다중 설비 비교** — 여러 설비 PPI를 한 차트에서 비교 (정규화 지원)
4. **🧮 수동 계산기** — API 호출 없이 빠른 환산

### 🏭 설비 카테고리 (18개 세부 품목)
- 🏭 **기계 설비**: 일반목적용(펌프·크레인·냉동), 특수목적용(압연기·로봇·건설기계)
- ⚡ **전기 설비**: 변압기, 전동기, 배전반, 케이블, 조명
- 🏗️ **토건/구조**: 철강1차제품, 구조용강재, 시멘트, 내화재
- 🔧 **계측/제어**: 계측기, 분석기, PLC/DCS
- 📊 **종합 지수**: 총지수, 공산품, 카테고리별 종합

---

## 🚀 빠른 시작

### 방법 1: Streamlit Cloud (권장, 무료 웹 배포)

아래 **배포 가이드(DEPLOY.md)** 를 따라 5분 만에 공개 URL 생성 가능.

### 방법 2: 로컬 실행

```bash
# 1. 저장소 클론
git clone https://github.com/<YOUR_ID>/posco-ppi-agent.git
cd posco-ppi-agent

# 2. 가상환경
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. 의존성 설치
pip install -r requirements.txt

# 4. 실행
streamlit run app.py
```

브라우저에서 `http://localhost:8501` 접속 → 사이드바에서 **🎬 DEMO 모드** 선택하면 바로 체험 가능!

---

## 🔑 API 키 (LIVE 모드용)

DEMO 모드는 API 키가 필요 없습니다. LIVE 모드 사용 시에만 발급:

| 서비스 | 발급 링크 | 비용 |
|--------|-----------|------|
| 한국은행 ECOS | [ecos.bok.or.kr/api](https://ecos.bok.or.kr/api/) | 무료 (1일 10만건) |
| OpenAI API (선택) | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | 유료 ($5 충전 권장) |

키는 두 가지 방법 중 하나로 등록:
- 사이드바 입력란에 직접 입력 (세션 단위, 가장 간단)
- `.streamlit/secrets.toml` 파일에 저장 (Streamlit Cloud 배포 시)

---

## 🏛️ 아키텍처

```
사용자 입력 (자연어)
       ↓
 ┌─────────────────┐
 │ 1. 파싱 Agent   │  ← OpenAI GPT (있으면) / 규칙 기반 (없으면)
 └─────────────────┘
       ↓
 ┌─────────────────┐
 │ 2. 품목 분류     │  ← 18개 PPI 품목 중 자동 선택
 └─────────────────┘
       ↓
 ┌─────────────────┐
 │ 3. ECOS API 조회 │  ← 실제 API (LIVE) / 가상 데이터 (DEMO)
 └─────────────────┘
       ↓
 ┌─────────────────┐
 │ 4. 환산 계산     │  ← 원금 × (목표 PPI / 기준 PPI)
 └─────────────────┘
       ↓
 ┌─────────────────┐
 │ 5. 보고서 생성   │  ← 마크다운 자동 작성
 └─────────────────┘
       ↓
     결과 출력
```

---

## 📁 프로젝트 구조

```
posco-ppi-agent/
├── app.py                      # Streamlit 메인 앱
├── requirements.txt            # 의존성
├── README.md
├── DEPLOY.md                   # 배포 가이드
├── .env.example
├── .gitignore
├── .streamlit/
│   ├── config.toml             # 테마 설정
│   └── secrets.toml.example
├── data/
│   └── ppi_categories.py       # 설비 카테고리 정의
├── agents/
│   └── ppi_agent.py            # AI Agent 로직 (파싱/환산/보고서)
└── utils/
    ├── ecos_client.py          # ECOS API 클라이언트
    └── demo_data.py            # DEMO 모드용 가상 데이터 생성기
```

---

## 🎓 교육 활용 가이드

### 추천 교육 흐름
1. **오프닝 시연 (10분)** — 강사가 DEMO 모드로 자연어 요청 → 5초 보고서 생성 시연
2. **실습 1 (20분)** — 참가자별 설비 카테고리 선택해 PPI 추이 관찰
3. **실습 2 (20분)** — 다중 비교 탭에서 "기계 vs 전기 vs 토건 중 어느 설비가 가장 물가에 민감한가" 토론
4. **심화 (30분)** — GitHub Fork → 본인 부서 특화 품목 추가 → PR 제출

### 학습 목표
- ✅ 공공 API 활용법 (ECOS, OpenAI)
- ✅ AI Agent 설계 패턴 (파싱 → 분류 → 조회 → 계산 → 보고)
- ✅ Streamlit으로 웹 앱 만들기
- ✅ Plotly 인터랙티브 시각화
- ✅ GitHub + Streamlit Cloud 배포

---

## ⚠️ 주의사항

- 본 도구는 교육/참고용 데모입니다. 실제 투자 의사결정 시 사내 표준 절차를 따르세요.
- **DEMO 모드의 데이터는 실제 PPI가 아닌 가상 시계열**입니다. 실제 분석에는 LIVE 모드 사용.
- ECOS 품목 코드(ITEM_CODE)는 한국은행이 개편할 수 있습니다. `data/ppi_categories.py`를 최신 코드로 갱신하세요.
- OpenAI API 사용 시 토큰 비용 발생. 교육용은 `gpt-4o-mini` 권장.

---

## 📄 라이선스

MIT License (교육용)
