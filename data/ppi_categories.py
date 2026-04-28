"""
포스코 투자엔지니어링 관점의 설비 카테고리 힌트
⚠️ ECOS 실제 품목명은 런타임에 API로 받아옵니다. 이 파일은 '카테고리 필터 힌트'로만 사용.

각 카테고리의 KEYWORDS는 ECOS 품목명에 포함된 한글 단어 기준으로 매칭됩니다.
(예: KEYWORDS=['펌프', '크레인']이면 ECOS 품목명에 '펌프' 또는 '크레인'이 들어간 것만 필터)
"""

# 대분류별 ECOS 품목명 필터 키워드
# (ECOS 품목명에 이 단어들 중 하나라도 포함되면 그 카테고리로 분류)
CATEGORY_FILTERS = {
    "🏭 기계 설비": {
        "icon": "🏭",
        "keywords": [
            "펌프", "압축기", "기관", "터빈", "보일러",
            "크레인", "컨베이어", "승강기", "권양", "운반",
            "공조", "냉동", "냉장", "환기",
            "공작기계", "가공기계", "성형",
            "로봇",
            "건설기계", "광업", "굴삭",
            "기계",  # 일반
        ],
        "desc": "펌프·크레인·공작기계·공조설비 등",
    },
    "⚡ 전기 설비": {
        "icon": "⚡",
        "keywords": [
            "변압기", "전동기", "발전기", "모터",
            "배전", "개폐", "배선",
            "케이블", "전선", "전력선",
            "축전지", "전지",
            "조명", "램프",
            "전기", "전자",
        ],
        "desc": "변압기·전동기·케이블·배전반 등",
    },
    "🏗️ 토건/구조 설비": {
        "icon": "🏗️",
        "keywords": [
            "철근", "형강", "강판", "철강", "강재", "후판",
            "시멘트", "콘크리트", "레미콘", "골재",
            "내화", "벽돌", "단열",
            "유리", "타일",
            "페인트", "도료",
        ],
        "desc": "철강재·시멘트·내화재·건축자재 등",
    },
    "🔧 계측/제어 설비": {
        "icon": "🔧",
        "keywords": [
            "계측", "계량", "측정",
            "분석",
            "제어", "자동",
        ],
        "desc": "계측기·분석기·제어시스템 등",
    },
    "📊 상위 지수": {
        "icon": "📊",
        "keywords": [
            "총지수", "공산품", "1차금속", "금속제품",
            "기계 및 장비", "전기장비", "비금속광물",
        ],
        "desc": "상위 카테고리 종합 지수",
    },
}


def filter_catalog_by_category(catalog_df, category_name: str):
    """
    ECOS 카탈로그 DataFrame을 대분류 키워드로 필터링
    """
    if catalog_df is None or len(catalog_df) == 0:
        return catalog_df
    if category_name not in CATEGORY_FILTERS:
        return catalog_df

    keywords = CATEGORY_FILTERS[category_name]["keywords"]
    name_col = "ITEM_NAME" if "ITEM_NAME" in catalog_df.columns else None
    if name_col is None:
        return catalog_df

    mask = catalog_df[name_col].astype(str).apply(
        lambda n: any(kw in n for kw in keywords)
    )
    return catalog_df[mask].reset_index(drop=True)


# ─────────────────────────────────────────────
# 이전 버전 호환용 (하드코딩 이름 제거된 상태로 최소 지원)
# ─────────────────────────────────────────────
EQUIPMENT_CATEGORIES = {}  # 더 이상 사용되지 않음 — Tab 2/3은 ECOS 카탈로그 직접 조회로 전환


def get_all_items():
    """이전 버전 호환 — 빈 리스트 반환 (실제 품목은 ECOS 카탈로그 사용)"""
    return []


def find_by_code(code: str):
    """이전 버전 호환 — 카탈로그에서 찾아야 하므로 None 반환"""
    return None


def find_by_name(name: str):
    """이전 버전 호환 — 카탈로그에서 찾아야 하므로 None 반환"""
    return None
