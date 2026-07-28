"""
철강 플랜트 공정별 설비비 물가보정 관심 품목 (모니터링·월간 리포트용)

★ 설계 원칙 1: ECOS 품목코드를 하드코딩하지 않는다.
  아래는 '품목명 검색 키워드'이며, 실행 시 ECOS 카탈로그(런타임 로드)에서
  실제 ITEM_CODE를 자동 매칭한다. → 통계표 개편·코드 변경에 영향받지 않음.

키워드는 **구체적인 것부터 일반적인 것 순서**로 적는다.
  utils/monitor.py의 resolve_item()이 앞에서부터 시도하고, 완전일치를 우선한다.
  예: ["펌프및압축기", "압축기", "펌프"] → 정확한 PPI 품목명이 있으면 그걸 쓰고,
      통계표가 개편돼 이름이 바뀌면 "펌프"로라도 잡힌다.

⚠️ 이 키워드가 실제 ECOS 품목에 매칭되는지는 **인증키로 카탈로그를 받아봐야** 확인된다.
   확인 명령:
       python -m scripts.verify_items
   실제로 매칭된 ECOS 품목명·코드를 출력하고, 실패한 키워드를 알려준다.
   매칭이 틀렸거나 실패하면 그 항목의 keywords를 고쳐야 한다.
   실제 품목명은 앱의 '설비별 PPI 조회' 탭에서 검색할 수 있다.
"""

STEEL_PLANT_ITEMS = {
    "제선": [
        {"label": "내화물", "keywords": ["내화물", "내화"], "note": "고로 내장재"},
        {"label": "코크스", "keywords": ["코크스"], "note": "고로 환원제"},
        {"label": "유연탄", "keywords": ["유연탄", "연료용탄", "석탄"], "note": "원료탄"},
        {"label": "펌프 및 압축기", "keywords": ["펌프및압축기", "압축기", "펌프"], "note": "송풍·냉각"},
        {"label": "내연기관 및 터빈", "keywords": ["내연기관및터빈", "터빈", "원동기"], "note": "송풍기 구동"},
        {"label": "운반하역기계", "keywords": ["운반하역기계", "운반하역"], "note": "원료 이송"},
        {"label": "컨베이어", "keywords": ["컨베이어"], "note": "원료 벨트"},
        {"label": "철구조물", "keywords": ["철구조물", "구조용금속제품"], "note": "고로 철피·철골"},
        {"label": "산업용 전력", "keywords": ["산업용전력", "전력"], "note": "조업 전력비"},
    ],
    "제강": [
        {"label": "내화물", "keywords": ["내화물", "내화"], "note": "전로·래들 내장재"},
        {"label": "특수목적용기계", "keywords": ["특수목적용기계", "특수목적"], "note": "전로·연주 설비"},
        {"label": "변압기", "keywords": ["변압기"], "note": "전기로·수전"},
        {"label": "운반하역기계", "keywords": ["운반하역기계", "크레인"], "note": "래들 크레인"},
        {"label": "산업용 가스", "keywords": ["산업용가스", "산소"], "note": "산소·질소·아르곤"},
        {"label": "합금철", "keywords": ["합금철", "페로망간", "페로실리콘"], "note": "성분 조정"},
        {"label": "흑연전극", "keywords": ["흑연전극", "전극"], "note": "전기로 전극"},
        {"label": "생석회", "keywords": ["생석회", "석회"], "note": "정련 부원료"},
    ],
    "열연": [
        {"label": "금속가공기계", "keywords": ["금속가공기계", "금속가공"], "note": "압연기 본체"},
        {"label": "일반목적용기계", "keywords": ["일반목적용기계", "일반목적"], "note": "부대 기계설비"},
        {"label": "전동기 및 발전기", "keywords": ["전동기및발전기", "전동기"], "note": "압연 구동"},
        {"label": "펌프 및 압축기", "keywords": ["펌프및압축기", "펌프"], "note": "냉각수·유압"},
        {"label": "배전 및 제어기기", "keywords": ["배전및제어기기", "배전", "제어기기"], "note": "전기실·MCC"},
        {"label": "베어링", "keywords": ["베어링"], "note": "롤 초크"},
        {"label": "기어 및 동력전달장치", "keywords": ["동력전달장치", "기어"], "note": "감속기"},
        {"label": "열연강판", "keywords": ["열연강판", "열연"], "note": "제품 가격 참고"},
    ],
    "냉연·도금": [
        {"label": "금속가공기계", "keywords": ["금속가공기계", "금속가공"], "note": "냉간압연·조질"},
        {"label": "특수목적용기계", "keywords": ["특수목적용기계", "특수목적"], "note": "도금·소둔 라인"},
        {"label": "일반목적용기계", "keywords": ["일반목적용기계", "일반목적"], "note": "부대 설비"},
        {"label": "전동기 및 발전기", "keywords": ["전동기및발전기", "전동기"], "note": "라인 구동"},
        {"label": "기초화학물질", "keywords": ["기초화학물질", "기초화학"], "note": "산세 약품"},
        {"label": "아연", "keywords": ["아연"], "note": "도금 원료"},
        {"label": "도료", "keywords": ["도료", "페인트"], "note": "컬러강판 도장"},
        {"label": "냉연강판", "keywords": ["냉연강판", "냉연"], "note": "제품 가격 참고"},
    ],
    "발전·유틸리티": [
        {"label": "보일러", "keywords": ["보일러"], "note": "발전·스팀"},
        {"label": "내연기관 및 터빈", "keywords": ["내연기관및터빈", "터빈"], "note": "발전 터빈"},
        {"label": "공기조화장치", "keywords": ["공기조화장치", "공기조화", "냉동공조"], "note": "전기실 공조"},
        {"label": "산업용 도시가스", "keywords": ["산업용도시가스", "도시가스"], "note": "연료비"},
        {"label": "산업용 수도", "keywords": ["산업용수도", "수도"], "note": "공업용수"},
        {"label": "축전지", "keywords": ["축전지", "전지"], "note": "비상 전원"},
        {"label": "발전기", "keywords": ["발전기"], "note": "비상 발전"},
    ],
    "인프라·토건": [
        {"label": "형강", "keywords": ["형강"], "note": "구조 철골"},
        {"label": "후판", "keywords": ["후판"], "note": "구조·압력용기"},
        {"label": "강판", "keywords": ["강판"], "note": "구조·배관재"},
        {"label": "철근", "keywords": ["철근"], "note": "철근 콘크리트"},
        {"label": "선재", "keywords": ["선재"], "note": "와이어·볼트 소재"},
        {"label": "강관", "keywords": ["강관"], "note": "배관 공사"},
        {"label": "시멘트", "keywords": ["시멘트"], "note": "기초 토목"},
        {"label": "레미콘", "keywords": ["레미콘", "콘크리트"], "note": "기초 타설"},
        {"label": "골재", "keywords": ["골재", "자갈", "모래"], "note": "토목 부자재"},
        {"label": "절연선 및 케이블", "keywords": ["절연선및케이블", "케이블", "전선"], "note": "전력 인프라"},
        {"label": "밸브", "keywords": ["밸브"], "note": "배관 부속"},
        {"label": "금속탱크 및 저장용기", "keywords": ["금속탱크", "저장용기", "탱크"], "note": "저장 설비"},
        {"label": "판유리", "keywords": ["판유리", "유리"], "note": "건축 자재"},
    ],
    "상위 지수": [
        {"label": "생산자물가 총지수", "keywords": ["총지수"], "note": "전체 물가 흐름"},
        {"label": "공산품", "keywords": ["공산품"], "note": "제조업 전반"},
        {"label": "제1차 금속제품", "keywords": ["제1차금속제품", "제1차금속", "1차금속"], "note": "철강 소재"},
        {"label": "금속가공제품", "keywords": ["금속가공제품"], "note": "가공 자재"},
        {"label": "기계 및 장비", "keywords": ["기계및장비"], "note": "설비 전반"},
        {"label": "전기장비", "keywords": ["전기장비"], "note": "전기 설비 전반"},
        {"label": "비금속광물제품", "keywords": ["비금속광물제품", "비금속광물"], "note": "시멘트·내화물류"},
        {"label": "화학제품", "keywords": ["화학제품"], "note": "약품·도료류"},
    ],
}


def get_processes():
    """공정 목록 반환"""
    return list(STEEL_PLANT_ITEMS.keys())


def get_items(process: str):
    """특정 공정의 품목 목록"""
    return STEEL_PLANT_ITEMS.get(process, [])


def get_all_items_flat(dedup: bool = False):
    """
    전체 품목을 (공정, 항목) 평면 리스트로.

    dedup=True : 같은 label이 여러 공정에 있으면 처음 것만 남긴다.
      품목마다 개별 API 호출이 발생하므로, 전체 조회나 월간 리포트처럼
      한 번에 다 받는 경우에는 중복을 없애야 호출 수가 줄고 표에 같은 품목이
      두 번 나오지 않는다.
    """
    out, seen = [], set()
    for proc, items in STEEL_PLANT_ITEMS.items():
        for it in items:
            if dedup:
                if it["label"] in seen:
                    continue
                seen.add(it["label"])
            out.append({"process": proc, **it})
    return out


def count_items(dedup: bool = True) -> int:
    """관심 품목 수 (기본은 중복 제거 기준)"""
    return len(get_all_items_flat(dedup=dedup))
