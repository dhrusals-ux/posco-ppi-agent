"""
철강 플랜트 공정별 설비비 물가보정 관심 품목 (모니터링용)

★ 설계 원칙: ECOS 품목코드를 하드코딩하지 않는다.
  아래는 '품목명 검색 키워드'이며, 실행 시 ECOS 카탈로그(런타임 로드)에서
  실제 ITEM_CODE를 자동 매칭한다. → 통계표 개편·코드 변경에 영향받지 않음.

각 항목:
  label    : 화면에 표시할 이름
  keywords : ECOS 품목명에 포함될 것으로 기대되는 단어(우선순위 순)
  note     : 해당 공정에서 왜 보는지

⚠️ 프로토타입 단계입니다. 실제 투엔1실 보정 기준 품목으로 계속 보완하세요.
"""

STEEL_PLANT_ITEMS = {
    "🔥 제선": [
        {"label": "내화물(내화벽돌)", "keywords": ["내화", "내화물"], "note": "고로 내장재"},
        {"label": "펌프 및 압축기", "keywords": ["펌프및압축기", "압축기", "펌프"], "note": "송풍·냉각 설비"},
        {"label": "내연기관 및 터빈", "keywords": ["내연기관및터빈", "터빈", "원동기"], "note": "송풍기 구동"},
        {"label": "운반하역기계", "keywords": ["운반하역", "운반", "크레인", "컨베이어"], "note": "원료 이송"},
        {"label": "철구조물", "keywords": ["철구조물", "구조용금속"], "note": "고로 철피·철골"},
    ],
    "⚙️ 제강": [
        {"label": "내화물(내화벽돌)", "keywords": ["내화", "내화물"], "note": "전로·래들 내장재"},
        {"label": "특수목적용기계", "keywords": ["특수목적용기계", "특수목적"], "note": "전로·연주 설비"},
        {"label": "변압기", "keywords": ["변압기"], "note": "전기로·수전 설비"},
        {"label": "운반하역기계", "keywords": ["운반하역", "크레인"], "note": "래들 크레인"},
        {"label": "산업용 가스", "keywords": ["산업용가스", "가스"], "note": "산소·질소·아르곤"},
    ],
    "🔴 열연": [
        {"label": "금속가공기계", "keywords": ["금속가공기계", "금속가공"], "note": "압연기 본체"},
        {"label": "일반목적용기계", "keywords": ["일반목적용기계", "일반목적"], "note": "부대 기계설비"},
        {"label": "전동기 및 발전기", "keywords": ["전동기및발전기", "전동기", "발전기"], "note": "압연 구동 모터"},
        {"label": "펌프 및 압축기", "keywords": ["펌프및압축기", "펌프"], "note": "냉각수·유압"},
        {"label": "배전 및 제어기기", "keywords": ["배전및제어", "배전", "제어기기"], "note": "전기실·MCC"},
    ],
    "🔵 냉연": [
        {"label": "금속가공기계", "keywords": ["금속가공기계", "금속가공"], "note": "냉간압연·조질"},
        {"label": "특수목적용기계", "keywords": ["특수목적용기계", "특수목적"], "note": "도금·소둔 라인"},
        {"label": "일반목적용기계", "keywords": ["일반목적용기계", "일반목적"], "note": "부대 설비"},
        {"label": "전동기 및 발전기", "keywords": ["전동기및발전기", "전동기"], "note": "라인 구동"},
        {"label": "기초화학물질", "keywords": ["기초화학", "화학물질"], "note": "산세·도금 약품"},
    ],
    "🏗️ 인프라/공통": [
        {"label": "형강", "keywords": ["형강"], "note": "구조 철골"},
        {"label": "강판", "keywords": ["강판", "후판", "열연강판"], "note": "구조·배관재"},
        {"label": "강관", "keywords": ["강관", "관"], "note": "배관 공사"},
        {"label": "시멘트", "keywords": ["시멘트"], "note": "기초 토목"},
        {"label": "레미콘", "keywords": ["레미콘", "콘크리트"], "note": "기초 타설"},
        {"label": "절연선 및 케이블", "keywords": ["절연선및케이블", "케이블", "전선"], "note": "전력 인프라"},
    ],
    "📊 상위 지수": [
        {"label": "생산자물가 총지수", "keywords": ["총지수"], "note": "전체 물가 흐름"},
        {"label": "공산품", "keywords": ["공산품"], "note": "제조업 전반"},
        {"label": "제1차 금속제품", "keywords": ["제1차금속", "1차금속"], "note": "철강 소재"},
        {"label": "기계 및 장비", "keywords": ["기계및장비", "기계 및 장비"], "note": "설비 전반"},
        {"label": "전기장비", "keywords": ["전기장비"], "note": "전기 설비 전반"},
    ],
}


def get_processes():
    """공정 목록 반환"""
    return list(STEEL_PLANT_ITEMS.keys())


def get_items(process: str):
    """특정 공정의 품목 목록"""
    return STEEL_PLANT_ITEMS.get(process, [])


def get_all_items_flat():
    """전체 품목을 (공정, 항목) 평면 리스트로"""
    out = []
    for proc, items in STEEL_PLANT_ITEMS.items():
        for it in items:
            out.append({"process": proc, **it})
    return out
