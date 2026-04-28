"""
물가보정 AI Agent
- OpenAI 또는 Google Gemini API 키가 있으면 LLM으로 자연어 파싱
- 없으면 규칙 기반 파서로 폴백 (데모 모드 지원)
"""
import os
import re
import json
from typing import Optional

# OpenAI (선택)
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# Google Gemini (선택)
try:
    from google import genai
    from google.genai import types as genai_types
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

from utils.ecos_client import ECOSClient
from utils.demo_data import DemoECOSClient
from data.ppi_categories import get_all_items, find_by_code, find_by_name


# ═══════════════════════════════════════════════════════
# 규칙 기반 폴백 파서 (LLM 없을 때 사용)
# ═══════════════════════════════════════════════════════

EQUIPMENT_KEYWORDS = {
    "압연": "금속가공기계", "단조": "금속가공기계", "절단기": "금속가공기계",
    "로봇": "산업용 로봇", "용접": "산업용 로봇",
    "크레인": "운반하역장비", "컨베이어": "운반하역장비", "호이스트": "운반하역장비",
    "펌프": "원동기 및 펌프", "보일러": "원동기 및 펌프", "터빈": "원동기 및 펌프",
    "냉각": "냉동공조기계", "hvac": "냉동공조기계", "냉동": "냉동공조기계",
    "굴삭": "광업/건설기계", "천공": "광업/건설기계",
    "변압기": "변압기",
    "모터": "전동기/발전기", "전동기": "전동기/발전기", "발전기": "전동기/발전기",
    "배전반": "배전반/제어반", "mcc": "배전반/제어반", "제어반": "배전반/제어반",
    "케이블": "전선 및 케이블", "전선": "전선 및 케이블",
    "조명": "산업용 조명",
    "철강": "철강 1차제품", "철근": "철강 1차제품", "강판": "철강 1차제품", "형강": "철강 1차제품",
    "h빔": "구조용 강재", "후판": "구조용 강재",
    "시멘트": "시멘트/콘크리트", "콘크리트": "시멘트/콘크리트", "레미콘": "시멘트/콘크리트",
    "내화": "내화/단열재", "단열": "내화/단열재",
    "계측": "산업용 계측기", "센서": "산업용 계측기",
    "분석기": "분석기기",
    "plc": "PLC/DCS", "dcs": "PLC/DCS",
    "코크스": "철강 1차제품",
    "고로": "철강 1차제품",
    "제강": "금속가공기계",
}


def _extract_all_periods(text: str) -> list:
    """텍스트에서 모든 시점을 순서대로 추출 (YYYYMM 형식)"""
    results = []
    pattern = re.compile(
        r'(\d{4})\s*년\s*(\d{1,2})\s*월'
        r'|(\d{4})[-./](\d{1,2})(?![\d])'
        r'|(\d{4})\s*년'
    )
    for m in pattern.finditer(text):
        if m.group(1):
            y, mo = m.group(1), m.group(2).zfill(2)
        elif m.group(3):
            y, mo = m.group(3), m.group(4).zfill(2)
        else:
            y, mo = m.group(5), "01"
        results.append(f"{y}{mo}")
    return results


def _extract_cost(text: str) -> Optional[float]:
    """금액 추출 (억원 단위)"""
    m = re.search(r'(\d{1,3}(?:,\d{3})*|\d+(?:\.\d+)?)\s*(억|조)', text)
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    if m.group(2) == "조":
        num *= 10000
    return num


def _match_equipment(text: str) -> dict:
    """키워드 매칭으로 품목 찾기"""
    text_lower = text.lower()
    for keyword, item_name in EQUIPMENT_KEYWORDS.items():
        if keyword in text_lower:
            item = find_by_name(item_name)
            if item:
                return {
                    "code": item["code"],
                    "keyword": keyword,
                    "reasoning": f"'{keyword}' 키워드 매칭 → {item['full_path']}",
                }
    return {
        "code": "42",
        "keyword": "일반 설비",
        "reasoning": "특정 키워드 미발견 → 기계및장비 종합지수 적용",
    }


def parse_query_rule_based(user_query: str) -> dict:
    """규칙 기반 파서 (LLM 미사용)"""
    periods = _extract_all_periods(user_query)
    base = periods[0] if len(periods) >= 1 else "202001"
    target = periods[1] if len(periods) >= 2 else "202601"
    cost = _extract_cost(user_query)
    eq = _match_equipment(user_query)

    if not cost:
        cost = 100.0

    return {
        "base_period": base,
        "target_period": target,
        "original_cost": cost,
        "equipment_keyword": eq["keyword"],
        "recommended_code": eq["code"],
        "reasoning": eq["reasoning"],
    }


# ═══════════════════════════════════════════════════════
# 프롬프트 빌더 (OpenAI/Gemini 공통)
# ═══════════════════════════════════════════════════════

def _build_parse_prompt(user_query: str) -> tuple:
    """파싱용 system + user 프롬프트 생성"""
    items = get_all_items()
    items_text = "\n".join([
        f"- {it['code']}: {it['full_path']} ({it['desc']})"
        for it in items
    ])

    system = f"""당신은 포스코 투자엔지니어링실의 분석가입니다.
사용자 요청에서 정보를 추출하고 가장 적합한 PPI 품목 코드를 선택하세요.

[사용 가능한 PPI 품목 목록]
{items_text}

응답은 반드시 다음 JSON 형식만 출력하세요 (다른 설명 없이):
{{
  "base_period": "YYYYMM",
  "target_period": "YYYYMM",
  "original_cost": 숫자(억원 단위),
  "equipment_keyword": "추출한 설비 키워드",
  "recommended_code": "선택한 품목코드",
  "reasoning": "왜 이 코드를 선택했는지 1-2문장"
}}"""
    return system, user_query


def _build_report_prompt(parsed, base_ppi, target_ppi, item_info) -> str:
    """보고서 생성용 프롬프트"""
    factor = target_ppi / base_ppi
    adjusted = parsed["original_cost"] * factor
    pct = (factor - 1) * 100

    return f"""다음 물가보정 분석 결과를 한국어 마크다운 보고서로 작성하세요.

[입력]
- 원금: {parsed['original_cost']:,} 억원
- 기준시점: {parsed['base_period']}
- 비교시점: {parsed['target_period']}
- 설비유형: {parsed['equipment_keyword']}

[적용 PPI 품목]
- {item_info['full_path']}
- 코드: {item_info['code']}
- 선택 근거: {parsed['reasoning']}

[PPI 변동]
- 기준시점 PPI: {base_ppi:.2f}
- 비교시점 PPI: {target_ppi:.2f}
- 보정계수: {factor:.4f}
- 변동률: {pct:+.2f}%

[환산 결과]
- 환산금액: {adjusted:,.2f} 억원 (증감: {adjusted - parsed['original_cost']:+,.2f})

다음 구조로 작성:
## 📋 투자비 물가보정 결과
### 1. 입력 정보
### 2. 적용 PPI 품목
### 3. PPI 변동 분석
### 4. 환산 결과 (굵게 강조)
### 5. 검토 코멘트 (PPI 변동 원인 추론, 추가 검토사항)"""


# ═══════════════════════════════════════════════════════
# OpenAI 호출
# ═══════════════════════════════════════════════════════

def parse_query_openai(user_query: str, model: str = "gpt-4o-mini") -> dict:
    if not HAS_OPENAI:
        raise RuntimeError("openai 패키지가 설치되지 않았습니다.")
    client = OpenAI()
    system, user = _build_parse_prompt(user_query)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(response.choices[0].message.content)


def generate_report_openai(parsed, base_ppi, target_ppi, item_info,
                            model: str = "gpt-4o-mini") -> str:
    client = OpenAI()
    prompt = _build_report_prompt(parsed, base_ppi, target_ppi, item_info)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return response.choices[0].message.content


# ═══════════════════════════════════════════════════════
# Gemini 호출
# ═══════════════════════════════════════════════════════

def _extract_json_from_text(text: str) -> dict:
    """Gemini 응답에서 JSON 블록 추출"""
    # ```json ... ``` 블록 제거
    text = re.sub(r'^```(?:json)?\s*', '', text.strip())
    text = re.sub(r'\s*```$', '', text)
    # 첫 { 와 마지막 } 사이만 추출
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)


def parse_query_gemini(user_query: str, model: str = "gemini-2.5-flash") -> dict:
    if not HAS_GEMINI:
        raise RuntimeError("google-genai 패키지가 설치되지 않았습니다.")
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")

    client = genai.Client(api_key=api_key)
    system, user = _build_parse_prompt(user_query)

    response = client.models.generate_content(
        model=model,
        contents=user,
        config=genai_types.GenerateContentConfig(
            system_instruction=system,
            temperature=0,
            response_mime_type="application/json",
        ),
    )
    return _extract_json_from_text(response.text)


def generate_report_gemini(parsed, base_ppi, target_ppi, item_info,
                            model: str = "gemini-2.5-flash") -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")

    client = genai.Client(api_key=api_key)
    prompt = _build_report_prompt(parsed, base_ppi, target_ppi, item_info)

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(temperature=0.3),
    )
    return response.text


# ═══════════════════════════════════════════════════════
# 템플릿 기반 보고서 (LLM 미사용)
# ═══════════════════════════════════════════════════════

def generate_report_template(parsed, base_ppi, target_ppi, item_info) -> str:
    """템플릿 기반 보고서 (LLM 미사용, 데모 모드)"""
    factor = target_ppi / base_ppi
    adjusted = parsed["original_cost"] * factor
    pct = (factor - 1) * 100

    if pct > 20:
        comment = "큰 폭의 상승 — 원자재 가격 급등 및 글로벌 공급망 영향 가능성"
    elif pct > 10:
        comment = "상당한 상승 — 인플레이션 및 인건비 상승 반영"
    elif pct > 0:
        comment = "완만한 상승 — 일반적 물가 상승 수준"
    elif pct > -5:
        comment = "보합 — 시장 안정 구간"
    else:
        comment = "하락 — 경기 둔화 또는 공급 과잉 영향 검토 필요"

    return f"""## 📋 투자비 물가보정 결과

### 1. 입력 정보
- **원금**: {parsed['original_cost']:,} 억원
- **기준 시점**: {parsed['base_period'][:4]}년 {parsed['base_period'][4:]}월
- **비교 시점**: {parsed['target_period'][:4]}년 {parsed['target_period'][4:]}월
- **설비 유형**: {parsed['equipment_keyword']}

### 2. 적용 PPI 품목
- **품목 경로**: {item_info['full_path']}
- **ECOS 코드**: `{item_info['code']}`
- **선택 근거**: {parsed['reasoning']}

### 3. PPI 변동 분석
| 시점 | PPI 값 | 비고 |
|------|--------|------|
| {parsed['base_period']} | {base_ppi:.2f} | 기준 |
| {parsed['target_period']} | {target_ppi:.2f} | 비교 |

- **보정계수**: {factor:.4f}
- **누적 변동률**: **{pct:+.2f}%**

### 4. 환산 결과
> 💰 **환산 금액: {adjusted:,.2f} 억원**
>
> (원금 {parsed['original_cost']:,.0f} 억원 → {adjusted - parsed['original_cost']:+,.2f} 억원)

### 5. 검토 코멘트
- **변동 성격**: {comment}
- **추가 검토사항**:
  - 환율 변동(해외 자재 비중 시) 별도 반영 필요
  - 노무비·설치비는 PPI와 별도 지표(건설공사비지수, 노임단가) 참고
  - 사내 유사 프로젝트 실제 집행비와 교차 검증 권장
"""


# ═══════════════════════════════════════════════════════
# 메인 파이프라인
# ═══════════════════════════════════════════════════════

def _resolve_provider(provider: Optional[str] = None) -> str:
    """사용할 LLM provider 결정 (auto / openai / gemini / none)"""
    if provider and provider != "auto":
        return provider

    # auto: 환경변수 기준으로 결정
    if os.getenv("GEMINI_API_KEY", "").strip() and HAS_GEMINI:
        return "gemini"
    if os.getenv("OPENAI_API_KEY", "").strip() and HAS_OPENAI:
        return "openai"
    return "none"


def run_ppi_agent(
    user_query: str,
    use_demo: bool = False,
    llm_provider: str = "auto",
    openai_model: str = "gpt-4o-mini",
    gemini_model: str = "gemini-2.5-flash",
    override_code: Optional[str] = None,
) -> dict:
    """
    전체 Agent 파이프라인 실행

    Parameters
    ----------
    user_query : str
        자연어 요청
    use_demo : bool
        True면 ECOS/LLM 모두 데모 모드
    llm_provider : str
        'auto' | 'openai' | 'gemini' | 'none' (규칙 기반)
    override_code : str, optional
        지정 시 자연어 매칭을 무시하고 이 ITEM_CODE로 조회 (INFO-200 회피용)
    """
    provider = "none" if use_demo else _resolve_provider(llm_provider)
    used_llm = None

    # 1. 파싱
    try:
        if provider == "gemini":
            parsed = parse_query_gemini(user_query, gemini_model)
            used_llm = f"Gemini ({gemini_model})"
        elif provider == "openai":
            parsed = parse_query_openai(user_query, openai_model)
            used_llm = f"OpenAI ({openai_model})"
        else:
            parsed = parse_query_rule_based(user_query)
            used_llm = "규칙 기반 파서"
    except Exception as e:
        print(f"⚠️ LLM 파싱 실패, 규칙 기반으로 폴백: {e}")
        parsed = parse_query_rule_based(user_query)
        used_llm = "규칙 기반 파서 (LLM 실패 폴백)"
        provider = "none"

    # 2. ECOS 조회
    ecos_key = os.getenv("ECOS_API_KEY", "").strip()
    if use_demo or not ecos_key:
        ecos = DemoECOSClient()
        data_source = "📦 DEMO DATA (가상 시계열)"
    else:
        ecos = ECOSClient()
        data_source = "🏦 한국은행 ECOS API"

    # ★ 사용자가 직접 지정한 ITEM_CODE가 있으면 파서 결과를 덮어쓰기
    if override_code:
        parsed["recommended_code"] = override_code.strip()
        parsed["override_applied"] = True
        parsed["auto_matched"] = False
    elif not use_demo and ecos_key:
        # ★ LIVE 모드: ECOS 실시간 카탈로그로 자동 매칭 시도
        try:
            from utils.ecos_catalog import get_catalog, auto_match_code
            catalog = get_catalog(api_key=ecos_key)
            if catalog is not None and len(catalog) > 0:
                best, candidates = auto_match_code(user_query, catalog)
                if best and best["score"] >= 5.0:
                    parsed["recommended_code"] = best["code"]
                    parsed["auto_matched"] = True
                    parsed["auto_match_info"] = best
                    parsed["auto_match_candidates"] = candidates
        except Exception as e:
            print(f"[auto_match] 실패, 파서 결과 그대로 사용: {e}")

    base_ppi = ecos.get_ppi_at(parsed["recommended_code"], parsed["base_period"])
    target_ppi = ecos.get_ppi_at(parsed["recommended_code"], parsed["target_period"])

    # 3. 품목 정보
    item_info = find_by_code(parsed["recommended_code"])
    if not item_info:
        item_info = {
            "full_path": f"기타 ({parsed['recommended_code']})",
            "code": parsed["recommended_code"],
            "name": "기타",
        }

    # 4. 보고서 생성
    try:
        if provider == "gemini":
            report = generate_report_gemini(parsed, base_ppi, target_ppi, item_info, gemini_model)
        elif provider == "openai":
            report = generate_report_openai(parsed, base_ppi, target_ppi, item_info, openai_model)
        else:
            report = generate_report_template(parsed, base_ppi, target_ppi, item_info)
    except Exception as e:
        print(f"⚠️ LLM 보고서 실패, 템플릿 사용: {e}")
        report = generate_report_template(parsed, base_ppi, target_ppi, item_info)

    factor = target_ppi / base_ppi
    return {
        "parsed": parsed,
        "item_info": item_info,
        "base_ppi": base_ppi,
        "target_ppi": target_ppi,
        "factor": factor,
        "adjusted_cost": parsed["original_cost"] * factor,
        "report": report,
        "data_source": data_source,
        "used_llm": used_llm,
        "used_openai": provider == "openai",  # 이전 버전 호환
    }


# =========================================================
#  🆕 PPI 상승/하락 원인 해설 (Gemini)
# =========================================================

def _summarize_ppi_series(df) -> str:
    """PPI 시계열 DataFrame을 Gemini에 전달할 간결한 텍스트로 요약."""
    import pandas as pd

    if df is None or len(df) == 0:
        return "(데이터 없음)"

    # DataFrame 가정: 'date' 또는 index가 날짜, 'value' 컬럼에 PPI 값
    try:
        d = df.copy()
        if "date" in d.columns:
            d["date"] = pd.to_datetime(d["date"])
            d = d.sort_values("date")
        else:
            d = d.sort_index()
            d["date"] = pd.to_datetime(d.index)

        value_col = "value" if "value" in d.columns else d.columns[0]

        # 연도별 평균값
        d["year"] = d["date"].dt.year
        yearly = d.groupby("year")[value_col].mean().round(2)

        # 전년 대비 변동률(%)
        yoy = yearly.pct_change().mul(100).round(2)

        lines = []
        for y, v in yearly.items():
            delta = yoy.get(y)
            if pd.isna(delta):
                lines.append(f"- {int(y)}년 평균: {v}")
            else:
                arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "·")
                lines.append(f"- {int(y)}년 평균: {v} (YoY {arrow}{abs(delta)}%)")

        # 주요 급등/급락 구간(연간 |변동률| >= 5%) 강조
        big = yoy[yoy.abs() >= 5].dropna()
        if len(big) > 0:
            lines.append("")
            lines.append("[주요 변동 연도]")
            for y, delta in big.items():
                arrow = "급등 ▲" if delta > 0 else "급락 ▼"
                lines.append(f"- {int(y)}년: {arrow} {delta:+.2f}%")

        return "\n".join(lines)
    except Exception as e:
        return f"(요약 실패: {e})"


def explain_price_change_gemini(
    item_name: str,
    item_code: str,
    ppi_df,
    base_period: str,
    target_period: str,
    factor: float,
    model: str = "gemini-2.5-flash",
) -> str:
    """
    PPI 시계열과 변동 폭을 바탕으로 Gemini가 '왜 올랐/내렸는지' 거시경제 맥락으로 해설.
    반환: 마크다운 문자열
    """
    if not HAS_GEMINI:
        raise RuntimeError("google-genai 패키지가 설치되지 않았습니다.")
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")

    series_text = _summarize_ppi_series(ppi_df)
    change_pct = (factor - 1.0) * 100

    system = (
        "너는 한국 산업·거시경제에 밝은 시니어 애널리스트다. "
        "한국은행 ECOS 생산자물가지수(PPI) 시계열을 바탕으로, "
        "특정 품목의 가격 변동 원인을 3~5가지 요인으로 구조화해 설명한다. "
        "반드시 한국어 마크다운으로 답하고, 실제 발생한 거시경제 이벤트"
        "(코로나19 팬데믹 2020, 글로벌 공급망 대란 2021~2022, 러시아-우크라이나 전쟁·원자재 급등 2022, "
        "미 연준 금리 인상 2022~2023, 원/달러 환율 변동, 중국 경기 둔화, 에너지 가격, 철광석·원료탄 가격, "
        "국내 건설경기·설비투자 사이클 등)과 연결해라. "
        "추측은 최소화하고, 데이터에서 보이는 구간을 먼저 지목한 뒤 원인을 해석하라. "
        "마지막에는 '포스코 투자엔지니어링 관점의 시사점'을 2~3줄로 덧붙여라."
    )

    user = f"""
## 분석 대상
- 품목명: **{item_name}**
- ECOS 코드: `{item_code}`
- 기준 시점: {base_period}
- 목표 시점: {target_period}
- 누적 변동률: **{change_pct:+.2f}%** (보정계수 {factor:.4f})

## 연도별 PPI 요약
{series_text}

## 요청
1. 위 기간의 PPI 추이를 3~5개 **주요 구간**으로 나누어 해설해줘.
2. 각 구간마다 **당시 거시경제 이벤트**(실제 발생한 것만)와 연결해서 왜 움직였는지 설명.
3. **포스코 투자엔지니어링 실무 시사점**(설비투자·원가 보정·리스크)을 마지막에 2~3줄.

출력 형식:
### 📈 PPI 변동 요약
(한두 문장)

### 🔎 구간별 원인 분석
- **YYYY~YYYY년 (±X%)** — 원인 설명
- ...

### 🎯 포스코 투자엔지니어링 시사점
- ...
"""

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=user,
        config=genai_types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.4,
        ),
    )
    return (response.text or "").strip()


def explain_multi_comparison_gemini(
    items_info: list,
    base_period: str,
    target_period: str,
    model: str = "gemini-2.5-flash",
) -> str:
    """
    다중 설비 비교 결과를 Gemini가 해설 — 왜 품목별로 다르게 움직였는지.
    items_info: [{"name": ..., "code": ..., "factor": ..., "df": ...}, ...]
    """
    if not HAS_GEMINI:
        raise RuntimeError("google-genai 패키지가 설치되지 않았습니다.")
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")

    blocks = []
    for it in items_info:
        name = it.get("name", "?")
        code = it.get("code", "?")
        factor = it.get("factor", 1.0)
        change = (factor - 1.0) * 100
        summary = _summarize_ppi_series(it.get("df"))
        blocks.append(
            f"### [{name}] (코드 {code}) — 변동 {change:+.2f}%\n{summary}"
        )
    data_block = "\n\n".join(blocks)

    system = (
        "너는 한국 산업·거시경제 시니어 애널리스트다. "
        "여러 품목의 생산자물가지수(PPI) 변동을 비교 분석하며, "
        "같은 기간에도 품목별로 다르게 움직인 이유를 거시·산업 요인으로 설명한다. "
        "반드시 한국어 마크다운으로 답하고, 실제 발생 이벤트(팬데믹·원자재·환율·금리·산업 사이클 등)와 연결하라. "
        "마지막에 '포스코 투자엔지니어링 관점의 시사점'을 2~3줄 덧붙여라."
    )

    user = f"""
## 비교 분석 대상
- 기준 시점: {base_period}
- 목표 시점: {target_period}

## 품목별 PPI 요약
{data_block}

## 요청
1. 같은 기간임에도 품목별 변동률이 다른 **핵심 이유 3~5가지**를 짚어줘.
2. 가장 많이 오른 품목과 가장 덜 오른(또는 내린) 품목을 대조해서 설명.
3. 각 품목에 영향을 미친 **거시경제·원자재 이벤트**를 구체적으로 연결.
4. 마지막에 **포스코 투자엔지니어링 시사점**(설비 Mix 전략·원가 리스크 분산).

출력 형식:
### 📊 비교 요약
(한두 문장)

### 🔍 품목별 차별화 원인
- **품목명 (±X%)** — ...

### 🎯 포스코 투자엔지니어링 시사점
- ...
"""

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=user,
        config=genai_types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.4,
        ),
    )
    return (response.text or "").strip()
