"""
건설공사비지수(KOSIS DT_39701_A003) 공종 분류 정의

⚠️ objL1(분류) 코드는 KOSIS 통계표 개편 시 바뀔 수 있습니다.
   실제 LIVE 연동 시 KOSISClient 로 분류 목록을 받아 코드를 갱신하세요.
   아래 코드는 '포스코 투자엔지니어링에서 자주 쓰는 핵심 공종' 위주의 시작 세트이며,
   DEMO 모드는 이 코드들로 가상 시계열을 생성합니다.

각 항목: (objL1 코드, 표시명, 설명, DEMO 변동 프로파일 힌트)
"""

# 핵심 공종 세트 — code 는 임시값(LIVE 연동 시 실제 KOSIS objL1로 교체)
CONSTRUCTION_CATEGORIES = {
    "C_TOTAL": {
        "name": "건설공사비지수 (종합)",
        "desc": "전체 건설공사비 종합 지수",
        "icon": "🏗️",
    },
    "C_CIVIL": {
        "name": "토목 부문",
        "desc": "도로·교량·터널·항만 등 토목 공종 종합",
        "icon": "🛣️",
    },
    "C_BUILD": {
        "name": "건축 부문",
        "desc": "주거·비주거 건축물 공종 종합",
        "icon": "🏢",
    },
    "C_RESID": {
        "name": "주거용 건물",
        "desc": "아파트·주택 등 주거용 건축",
        "icon": "🏠",
    },
    "C_NONRESID": {
        "name": "비주거용 건물",
        "desc": "공장·창고·사무소 등 비주거 건축 (플랜트 관련)",
        "icon": "🏭",
    },
    "C_PLANT": {
        "name": "산업플랜트/설비공사",
        "desc": "산업설비·플랜트 시공 관련 공종",
        "icon": "⚙️",
    },
    "C_STEEL": {
        "name": "철골/구조공사",
        "desc": "철골조·구조체 공사",
        "icon": "🔩",
    },
    "C_ELEC": {
        "name": "전기/계장 공사",
        "desc": "전기·계측제어 시공",
        "icon": "⚡",
    },
}


def get_all_construction_items():
    """전체 공종 목록 반환 [{code, name, desc, icon}, ...]"""
    return [
        {"code": code, **info}
        for code, info in CONSTRUCTION_CATEGORIES.items()
    ]


def find_construction_by_code(code: str):
    """코드로 공종 정보 조회"""
    info = CONSTRUCTION_CATEGORIES.get(code)
    if not info:
        return None
    return {"code": code, **info}
