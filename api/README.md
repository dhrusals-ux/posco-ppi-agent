# 투자비 물가보정 API

Streamlit UI와 **동일한 계산 로직**(`utils/`)을 REST로 노출하는 레이어입니다.
프론트엔드를 Next.js로 만들든 사내 표준 스택으로 만들든 이 API는 그대로 씁니다.

두 곳이 같은 `utils/`를 쓰므로 **Streamlit 화면과 웹 화면의 숫자가 갈라지지 않습니다.**

## 실행

```bash
pip install -r requirements.txt -r api/requirements.txt
```

키를 환경변수로 넣습니다. 키가 없으면 명확히 503으로 실패합니다 (데모 폴백 없음).

```bash
export ECOS_API_KEY="발급받은키"
export KOSIS_API_KEY="발급받은키"
export ALLOWED_ORIGINS="http://localhost:3000"
uvicorn api.main:app --reload --port 8000
```

Windows PowerShell이면:

```bash
$env:ECOS_API_KEY="발급받은키"; $env:KOSIS_API_KEY="발급받은키"; uvicorn api.main:app --reload --port 8000
```

띄운 뒤 <http://localhost:8000/docs> 에서 모든 엔드포인트를 브라우저로 직접 시험할 수 있습니다
(FastAPI가 자동 생성하는 문서라 별도 작업이 필요 없습니다).

## 엔드포인트

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/health` | 상태 · 키 설정 여부 (키 값은 노출하지 않음) |
| GET | `/meta` | 환산 공식 · 면책 문구 · 기본 목표시점 · 각종 상한 |
| GET | `/catalog/equipment?q=` | ECOS 품목 카탈로그 (1,577건) |
| GET | `/catalog/construction` | KOSIS 건설공사비지수 공종 분류 |
| GET | `/series/equipment/{code}` | 설비 PPI 시계열 |
| GET | `/series/construction/{code}` | 건설공사비지수 시계열 |
| POST | `/adjust/equipment` | 설비비 단일 환산 |
| POST | `/adjust/construction` | 공사비 단일 환산 |
| POST | `/batch/parse` | 견적 엑셀 업로드 → 컬럼 추정 |
| POST | `/batch/suggest` | 품목명 → ECOS 품목 자동 제안 + 신뢰도 |
| POST | `/batch/adjust` | 승인된 매칭표 일괄 환산 |
| GET | `/forecast/equipment/{code}` | 예측 (신뢰구간 밴드) |
| GET | `/forecast/construction/{code}` | 예측 (신뢰구간 밴드) |

`/meta`를 두는 이유: 목표시점 기본값이나 행 수 상한 같은 값을 프론트엔드가
따로 하드코딩하면 서버와 어긋납니다. 서버가 알려주는 값을 쓰세요.

## 일괄 보정 흐름

프론트엔드는 반드시 이 순서로 호출해야 합니다.

```
1. POST /batch/parse    엑셀 업로드 → 컬럼 목록 + 추정값
2. (사용자가 품목명·금액 컬럼 확정)
3. POST /batch/suggest  행별 자동 제안 + 신뢰도 + 판단근거 + 후보목록
4. (사용자가 매칭 수정 · 확인 체크)
5. POST /batch/adjust   일괄 환산
```

### ⚠️ 승인 게이트는 서버가 강제합니다

Streamlit에서는 게이트가 UI에 있었지만, 웹 API는 프론트엔드를 우회할 수 있습니다.
그래서 `POST /batch/adjust`는 다음 경우 **409**로 거부합니다.

- 신뢰도가 `높음`이 아닌데 `confirmed: false`인 행
- `code`가 비어 있는 행
- `amount`가 비어 있는 행
- 행 수가 상한(300) 초과

```json
{
  "detail": {
    "detail": "승인되지 않은 항목이 있어 일괄 보정을 실행할 수 없습니다.",
    "blockers": ["신뢰도 '중간·낮음·실패'인데 확인되지 않은 행 1건 (행 5) — ..."]
  }
}
```

**프론트엔드에서 `confirmed: true`를 일괄로 채워 보내지 마세요.** 게이트가 존재하는
이유는 틀린 매칭이 에러 없이 조용히 틀린 금액을 만들어 투자 품의서에 들어가는 것을
막기 위한 것입니다. 사람이 실제로 본 행만 체크되어야 합니다.

## 프론트엔드가 지켜야 할 것

1. **면책 문구를 반드시 표시하세요.** `/adjust/*`, `/batch/adjust`, `/forecast/*` 응답의
   `disclaimer` 필드에 담겨 옵니다. 「국가계약법」상 계약금액조정 산식과 다르므로
   공식 계약 근거로 쓰면 안 된다는 내용입니다.
2. **`판단근거`(`reason`)를 화면에 노출하세요.** 신뢰도 등급만 보여주면 검토자가
   그대로 믿습니다. 근거를 읽고 스스로 판단할 수 있어야 합니다.
3. **예측은 점 추정으로 그리지 마세요.** `forecast[].lower`/`upper`로 밴드를 그리고,
   `method`와 `warning`을 함께 표시해야 합니다. "AI 예측"이라 부르지 않습니다.
4. **실패 행을 합계에 섞지 마세요.** `summary`는 이미 실패 행을 제외한 값이고,
   그 사실이 `warning`에 담겨 옵니다. 이 경고를 숨기면 총액이 견적 전체와 다른데도
   맞는 것처럼 보입니다.
5. **금액을 억 단위로만 보여주지 마세요.** 반올림되므로 근거 화면에는 원 단위를 병기하세요.

## 오류 코드

| 상태 | 의미 |
|---|---|
| 404 | 요청한 품목·기간의 데이터 없음 (미발표 시점 포함) |
| 409 | 승인 게이트 위반 |
| 422 | 입력 형식 오류 · 데이터 부족 · 상한 초과 |
| 429 | ECOS/KOSIS 호출 한도 초과 — 재시도 가능 |
| 502 | 상위 API 오류 |
| 503 | 서버에 API 키가 설정되지 않음 |

## 배포 시 주의

- `ALLOWED_ORIGINS`를 실제 프론트엔드 도메인으로 지정하세요. 와일드카드를 쓰지 않습니다.
- **Vercel Python 함수는 권장하지 않습니다.** statsmodels 콜드스타트가 무겁습니다.
  Railway · Render · Cloud Run 같은 상시 실행 환경이 적합합니다.
- 카탈로그는 프로세스 메모리에 1시간 캐시됩니다. 인스턴스를 여러 개 띄우면
  각각 별도로 캐시하므로 상위 API 호출이 인스턴스 수만큼 늘어납니다.
  인스턴스를 늘릴 때는 공용 캐시(Redis 등)를 검토하세요.
- 사내 데이터를 저장하기 시작하면 정보보안 심의 대상이 될 수 있습니다.
  현재 이 API는 **아무것도 저장하지 않습니다** (공개 통계 조회 + 계산만).
