"""
물가보정 AI Agent
- OpenAI API 키가 있으면 GPT로 자연어 파싱
- 없으면 규칙 기반 파서로 폴백 (데모 모드 지원)
"""
import os
import re
import json
from typing import Optional

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

from utils.ecos_client import ECOSClient
from utils.demo_data import DemoECOSClient
from data.ppi_categories import get_all_items, find_by_code, find_by_name


# ═══════════════════════════════════════════════════════
# 규칙 기반 폴백 파서 (OpenAI 없을 때 사용)
# ═══════════════════════════════════════════════════════

EQUIPMENT_KEYWORDS = {
    # 키워드 → 품목명
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
    "코크스": "철강 1차제품",  # 제철 부속
    "고로": "철강 1차제품",
    "제강": "금속가공기계",
}


def _extract_all_periods(text: str) -> list:
    """텍스트에서 모든 시점을 순서대로 추출 (YYYYMM 형식)"""
    results = []
    # 전체 텍스트를 한 번만 스캔하면서 연-월 또는 연도 패턴 매칭
    # 우선순위: "YYYY년 M월" > "YYYY-MM / YYYY.MM" > "YYYY년"
    pattern = re.compile(
        r'(\d{4})\s*년\s*(\d{1,2})\s*월'     # 2020년 1월
        r'|(\d{4})[-./](\d{1,2})(?![\d])'    # 2020-01, 2020.01
        r'|(\d{4})\s*년'                      # 2020년
    )
    for m in pattern.finditer(text):
        if m.group(1):  # YYYY년 M월
            y, mo = m.group(1), m.group(2).zfill(2)
        elif m.group(3):  # YYYY-MM
            y, mo = m.group(3), m.group(4).zfill(2)
        else:  # YYYY년
            y, mo = m.group(5), "01"
        results.append(f"{y}{mo}")
    return results


def _extract_cost(text: str) -> Optional[float]:
    """금액 추출 (억원 단위)"""
    # "1,200억", "800억원", "1200억", "1.5조"
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
    # 기본값: 기계및장비 전체
    return {
        "code": "42",
        "keyword": "일반 설비",
        "reasoning": "특정 키워드 미발견 → 기계및장비 종합지수 적용",
    }


def parse_query_rule_based(user_query: str) -> dict:
    """규칙 기반 파서 (OpenAI 미사용)"""
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
# OpenAI 기반 파서
# ═══════════════════════════════════════════════════════

def parse_query_openai(user_query: str, model: str = "gpt-4o-mini") -> dict:
    """OpenAI로 자연어 파싱 + 품목 자동 선택"""
    if not HAS_OPENAI:
        raise RuntimeError("openai 패키지가 설치되지 않았습니다.")

    client = OpenAI()
    items = get_all_items()
    items_text = "\n".join([
        f"- {it['code']}: {it['full_path']} ({it['desc']})"
        for it in items
    ])

    system = f"""당신은 포스코 투자엔지니어링실의 분석가입니다.
사용자 요청에서 정보를 추출하고 가장 적합한 PPI 품목 코드를 선택하세요.

[사용 가능한 PPI 품목 목록]
{items_text}

응답은 반드시 다음 JSON 형식:
{{
  "base_period": "YYYYMM",
  "target_period": "YYYYMM",
  "original_cost": 숫자(억원 단위),
  "equipment_keyword": "추출한 설비 키워드",
  "recommended_code": "선택한 품목코드",
  "reasoning": "왜 이 코드를 선택했는지 1-2문장"
}}"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_query},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(response.choices[0].message.content)


# ═══════════════════════════════════════════════════════
# 보고서 생성
# ═══════════════════════════════════════════════════════

def generate_report_openai(
    parsed: dict,
    base_ppi: float,
    target_ppi: float,
    item_info: dict,
    model: str = "gpt-4o-mini",
) -> str:
    """OpenAI로 보고서 생성"""
    client = OpenAI()
    factor = target_ppi / base_ppi
    adjusted = parsed["original_cost"] * factor
    pct = (factor - 1) * 100

    prompt = f"""다음 물가보정 분석 결과를 한국어 마크다운 보고서로 작성하세요.

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

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return response.choices[0].message.content


def generate_report_template(
    parsed: dict,
    base_ppi: float,
    target_ppi: float,
    item_info: dict,
) -> str:
    """템플릿 기반 보고서 (OpenAI 미사용, 데모 모드)"""
    factor = target_ppi / base_ppi
    adjusted = parsed["original_cost"] * factor
    pct = (factor - 1) * 100

    # 변동률 기반 코멘트
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

def run_ppi_agent(
    user_query: str,
    use_demo: bool = False,
    model: str = "gpt-4o-mini",
) -> dict:
    """
    전체 Agent 파이프라인 실행

    Parameters
    ----------
    user_query : str
        자연어 요청
    use_demo : bool
        True면 ECOS/OpenAI 모두 데모 모드 (API 키 불필요)
    """
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    use_openai = bool(openai_key) and HAS_OPENAI and not use_demo

    # 1. 파싱
    if use_openai:
        try:
            parsed = parse_query_openai(user_query, model)
        except Exception as e:
            print(f"⚠️ OpenAI 파싱 실패, 규칙 기반으로 폴백: {e}")
            parsed = parse_query_rule_based(user_query)
            use_openai = False
    else:
        parsed = parse_query_rule_based(user_query)

    # 2. ECOS 조회 (데모 모드 분기)
    ecos_key = os.getenv("ECOS_API_KEY", "").strip()
    if use_demo or not ecos_key:
        ecos = DemoECOSClient()
        data_source = "📦 DEMO DATA (가상 시계열)"
    else:
        ecos = ECOSClient()
        data_source = "🏦 한국은행 ECOS API"

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
    if use_openai:
        try:
            report = generate_report_openai(parsed, base_ppi, target_ppi, item_info, model)
        except Exception as e:
            print(f"⚠️ OpenAI 보고서 실패, 템플릿 사용: {e}")
            report = generate_report_template(parsed, base_ppi, target_ppi, item_info)
    else:
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
        "used_openai": use_openai,
    }
