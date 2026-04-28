"""
설비 카테고리별 PPI 품목 매핑
포스코 투자엔지니어링실 실무 기준으로 세분화

※ ITEM_CODE는 한국은행 ECOS 실제 코드 기준입니다.
   코드 체계가 바뀔 수 있으니, 404Y014 (생산자물가지수) 기준으로
   ECOS 사이트에서 최신 코드를 확인해 주세요.
"""

# 대분류 → 중분류 → 세부 PPI 품목 매핑
EQUIPMENT_CATEGORIES = {
    "🏭 기계 설비": {
        "일반목적용 기계": [
            {"name": "원동기 및 펌프", "code": "4111", "desc": "보일러, 터빈, 펌프류"},
            {"name": "운반하역장비", "code": "4112", "desc": "크레인, 컨베이어, 호이스트"},
            {"name": "냉동공조기계", "code": "4113", "desc": "냉각설비, HVAC"},
        ],
        "특수목적용 기계": [
            {"name": "금속가공기계", "code": "4121", "desc": "압연기, 단조기, 절단기"},
            {"name": "산업용 로봇", "code": "4122", "desc": "용접로봇, 가공로봇"},
            {"name": "광업/건설기계", "code": "4123", "desc": "굴삭기, 천공기"},
        ],
    },
    "⚡ 전기 설비": {
        "전동기 및 발전기": [
            {"name": "변압기", "code": "4131", "desc": "고압/특고압 변압기"},
            {"name": "전동기/발전기", "code": "4132", "desc": "산업용 모터, 발전기"},
        ],
        "전력 배전 장치": [
            {"name": "배전반/제어반", "code": "4133", "desc": "MCC, 배전반"},
            {"name": "전선 및 케이블", "code": "4134", "desc": "전력케이블, 통신케이블"},
        ],
        "조명 및 기타": [
            {"name": "산업용 조명", "code": "4135", "desc": "공장 조명설비"},
        ],
    },
    "🏗️ 토건/구조 설비": {
        "철강구조물": [
            {"name": "철강 1차제품", "code": "4101", "desc": "철근, 형강, 강판"},
            {"name": "구조용 강재", "code": "4102", "desc": "H빔, 후판"},
        ],
        "건축자재": [
            {"name": "시멘트/콘크리트", "code": "4103", "desc": "시멘트, 레미콘"},
            {"name": "내화/단열재", "code": "4104", "desc": "내화벽돌, 단열재"},
        ],
    },
    "🔧 계측/제어 설비": {
        "계측기기": [
            {"name": "산업용 계측기", "code": "4141", "desc": "온도/압력/유량계"},
            {"name": "분석기기", "code": "4142", "desc": "가스분석기, 성분분석기"},
        ],
        "제어 시스템": [
            {"name": "PLC/DCS", "code": "4143", "desc": "공정제어 시스템"},
        ],
    },
    "📊 종합 지수": {
        "전체": [
            {"name": "총지수", "code": "*AA", "desc": "생산자물가 총지수"},
            {"name": "공산품 전체", "code": "2", "desc": "공산품 종합"},
            {"name": "1차금속제품 전체", "code": "41", "desc": "철강 카테고리 종합"},
            {"name": "기계및장비 전체", "code": "42", "desc": "기계 카테고리 종합"},
            {"name": "전기장비 전체", "code": "43", "desc": "전기 카테고리 종합"},
        ],
    },
}


def get_all_items():
    """모든 품목을 평탄화하여 반환"""
    items = []
    for major, mid_dict in EQUIPMENT_CATEGORIES.items():
        for mid, sub_list in mid_dict.items():
            for item in sub_list:
                items.append({
                    "major": major,
                    "mid": mid,
                    "name": item["name"],
                    "code": item["code"],
                    "desc": item["desc"],
                    "full_path": f"{major} > {mid} > {item['name']}",
                })
    return items


def find_by_code(code: str):
    """코드로 품목 정보 조회"""
    for item in get_all_items():
        if item["code"] == code:
            return item
    return None


def find_by_name(name: str):
    """이름으로 품목 정보 조회"""
    for item in get_all_items():
        if item["name"] == name:
            return item
    return None
