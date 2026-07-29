"""
플랜트 설비비 물가보정 관심 품목 (모니터링·월간 리포트 기본 목록)

구분 축은 **기계 / 전기 / 계측·제어 / 토건·구조 / 내화·건자재 / 화학·유틸리티**다.
투자비를 기전토(기계·전기·토건)로 나누는 실무 구분에 맞춘 것이고, 담당자가
자기 분야만 보면 되도록 했다. 기계·전기는 각각 15개 이상 담는다.

★ 설계 원칙 1: ECOS 품목코드를 하드코딩하지 않는다.
  아래는 '품목명 검색 키워드'이며, 실행 시 ECOS 카탈로그(런타임 로드)에서
  실제 ITEM_CODE를 자동 매칭한다. → 통계표 개편·코드 변경에 영향받지 않음.

키워드는 **구체적인 것부터 일반적인 것 순서**로 적는다.
  utils/monitor.py의 resolve_item()이 앞에서부터 시도하고 완전일치를 우선한다.
  예: ["펌프및압축기", "압축기", "펌프"] → 정확한 PPI 품목명이 있으면 그걸 쓰고,
      통계표가 개편돼 이름이 바뀌면 "펌프"로라도 잡힌다.

⚠️ 이 키워드가 실제 ECOS 품목에 매칭되는지는 **인증키로 카탈로그를 받아봐야** 확인된다.
   확인:  python -m scripts.verify_items
   목록:  python -m scripts.dump_catalog --preset machinery --tree

   더 확실한 방법은 앱의 '관심 품목 설정' 탭에서 카탈로그를 보고 직접 체크하는 것이다.
   그렇게 고르면 실제 코드가 저장되어 매칭 단계 자체가 없어진다.
   이 파일은 그 선택이 없을 때 쓰이는 **기본값**이다.
"""

STEEL_PLANT_ITEMS = {
    # ── 기계 (22개) ──
    "기계": [
        {"label": "일반목적용기계", "keywords": ["일반목적용기계", "일반목적"], "note": "기계 대분류"},
        {"label": "특수목적용기계", "keywords": ["특수목적용기계", "특수목적"], "note": "기계 대분류"},
        {"label": "펌프 및 압축기", "keywords": ["펌프및압축기", "펌프"], "note": "냉각수·유압·송풍"},
        {"label": "압축기", "keywords": ["압축기"], "note": "공압·산소 플랜트"},
        {"label": "송풍기", "keywords": ["송풍기", "송풍"], "note": "고로 송풍"},
        {"label": "내연기관 및 터빈", "keywords": ["내연기관및터빈", "터빈", "원동기"], "note": "발전·송풍 구동"},
        {"label": "보일러", "keywords": ["보일러"], "note": "발전·스팀 공급"},
        {"label": "열교환기", "keywords": ["열교환", "열교환기"], "note": "냉각·회수 설비"},
        {"label": "운반하역기계", "keywords": ["운반하역기계", "운반하역"], "note": "원료·제품 이송"},
        {"label": "크레인", "keywords": ["크레인", "기중기"], "note": "래들·코일 크레인"},
        {"label": "컨베이어", "keywords": ["컨베이어"], "note": "원료 벨트"},
        {"label": "승강기", "keywords": ["승강기", "엘리베이터"], "note": "설비 승강"},
        {"label": "금속가공기계", "keywords": ["금속가공기계", "금속가공"], "note": "압연기·전단"},
        {"label": "공기조화장치", "keywords": ["공기조화장치", "공기조화"], "note": "전기실 공조"},
        {"label": "냉동·냉장기계", "keywords": ["냉동", "냉장"], "note": "냉각 설비"},
        {"label": "베어링", "keywords": ["베어링"], "note": "롤 초크"},
        {"label": "기어 및 동력전달장치", "keywords": ["동력전달장치", "기어"], "note": "감속기"},
        {"label": "밸브", "keywords": ["밸브"], "note": "배관 부속"},
        {"label": "유압·공압기기", "keywords": ["유압", "공압"], "note": "압연 유압 시스템"},
        {"label": "산업용 로 및 노", "keywords": ["산업용로", "로및노"], "note": "가열로·소둔로"},
        {"label": "건설·광산기계", "keywords": ["건설광산기계", "건설기계", "굴삭"], "note": "토목 장비"},
        {"label": "금속탱크 및 저장용기", "keywords": ["금속탱크", "저장용기", "탱크"], "note": "저장 설비"},
    ],

    # ── 전기 (16개) ──
    "전기": [
        {"label": "전기장비", "keywords": ["전기장비"], "note": "전기 대분류"},
        {"label": "변압기", "keywords": ["변압기"], "note": "수전·전기로"},
        {"label": "전동기 및 발전기", "keywords": ["전동기및발전기", "전동기"], "note": "압연·라인 구동"},
        {"label": "전동기", "keywords": ["전동기", "모터"], "note": "개별 구동 모터"},
        {"label": "발전기", "keywords": ["발전기"], "note": "자가·비상 발전"},
        {"label": "배전 및 제어기기", "keywords": ["배전및제어기기", "배전", "제어기기"], "note": "전기실·MCC"},
        {"label": "배전반", "keywords": ["배전반", "수배전"], "note": "수배전 설비"},
        {"label": "개폐기·차단기", "keywords": ["개폐기", "차단기", "개폐"], "note": "보호 기기"},
        {"label": "절연선 및 케이블", "keywords": ["절연선및케이블", "케이블"], "note": "전력 인프라"},
        {"label": "전선", "keywords": ["전선", "전력선"], "note": "배선 자재"},
        {"label": "전력변환장치", "keywords": ["전력변환", "인버터", "정류"], "note": "인버터·정류기"},
        {"label": "축전지", "keywords": ["축전지", "전지"], "note": "비상 전원·UPS"},
        {"label": "조명장치", "keywords": ["조명장치", "조명", "램프"], "note": "공장 조명"},
        {"label": "배선기구", "keywords": ["배선기구", "배선"], "note": "전기 부자재"},
        {"label": "전기용 탄소제품", "keywords": ["전기용탄소", "탄소제품", "흑연전극"], "note": "전기로 전극"},
        {"label": "산업용 전력", "keywords": ["산업용전력", "전력"], "note": "조업 전력비"},
    ],

    # ── 계측·제어 (7개) ──
    "계측·제어": [
        {"label": "측정·분석기기", "keywords": ["측정", "계측"], "note": "공정 계측"},
        {"label": "분석기", "keywords": ["분석기", "분석"], "note": "성분 분석"},
        {"label": "계량기", "keywords": ["계량기", "계량"], "note": "유량·중량 계측"},
        {"label": "자동조절기", "keywords": ["자동조절", "자동제어"], "note": "공정 제어"},
        {"label": "정밀기기", "keywords": ["정밀기기", "정밀"], "note": "계측 전반"},
        {"label": "산업용 로봇", "keywords": ["로봇"], "note": "자동화 설비"},
        {"label": "컴퓨터 및 주변장치", "keywords": ["컴퓨터", "주변장치"], "note": "제어 시스템"},
    ],

    # ── 토건·구조 (15개) ──
    "토건·구조": [
        {"label": "형강", "keywords": ["형강"], "note": "구조 철골"},
        {"label": "후판", "keywords": ["후판"], "note": "구조·압력용기"},
        {"label": "강판", "keywords": ["강판"], "note": "구조·배관재"},
        {"label": "철근", "keywords": ["철근"], "note": "철근 콘크리트"},
        {"label": "선재", "keywords": ["선재"], "note": "와이어·볼트 소재"},
        {"label": "강관", "keywords": ["강관"], "note": "배관 공사"},
        {"label": "철구조물", "keywords": ["철구조물", "구조용금속제품"], "note": "철골·철피"},
        {"label": "제1차 금속제품", "keywords": ["제1차금속제품", "제1차금속"], "note": "철강 소재 전반"},
        {"label": "금속가공제품", "keywords": ["금속가공제품"], "note": "가공 자재"},
        {"label": "시멘트", "keywords": ["시멘트"], "note": "기초 토목"},
        {"label": "레미콘", "keywords": ["레미콘", "콘크리트"], "note": "기초 타설"},
        {"label": "골재", "keywords": ["골재", "자갈", "모래"], "note": "토목 부자재"},
        {"label": "아스팔트·포장재", "keywords": ["아스팔트", "포장"], "note": "구내 도로"},
        {"label": "도금강판", "keywords": ["도금강판", "도금"], "note": "외장·덕트"},
        {"label": "스테인리스강판", "keywords": ["스테인리스"], "note": "내식 배관·설비"},
    ],

    # ── 내화·건자재 (7개) ──
    "내화·건자재": [
        {"label": "내화물", "keywords": ["내화물", "내화"], "note": "고로·전로 내장재"},
        {"label": "내화벽돌", "keywords": ["내화벽돌", "벽돌"], "note": "노 내장"},
        {"label": "비금속광물제품", "keywords": ["비금속광물제품", "비금속광물"], "note": "내화·시멘트류 전반"},
        {"label": "판유리", "keywords": ["판유리", "유리"], "note": "건축 자재"},
        {"label": "단열재", "keywords": ["단열", "보온"], "note": "배관·설비 보온"},
        {"label": "석고보드", "keywords": ["석고"], "note": "내장 자재"},
        {"label": "생석회", "keywords": ["생석회", "석회"], "note": "정련 부원료"},
    ],

    # ── 화학·유틸리티 (10개) ──
    "화학·유틸리티": [
        {"label": "기초화학물질", "keywords": ["기초화학물질", "기초화학"], "note": "산세 약품"},
        {"label": "산업용 가스", "keywords": ["산업용가스", "산소"], "note": "산소·질소·아르곤"},
        {"label": "도료", "keywords": ["도료", "페인트"], "note": "도장·컬러강판"},
        {"label": "윤활유", "keywords": ["윤활유", "윤활"], "note": "설비 윤활"},
        {"label": "화학제품", "keywords": ["화학제품"], "note": "약품 전반"},
        {"label": "코크스", "keywords": ["코크스"], "note": "고로 환원제"},
        {"label": "유연탄", "keywords": ["유연탄", "연료용탄", "석탄"], "note": "원료탄"},
        {"label": "산업용 도시가스", "keywords": ["산업용도시가스", "도시가스"], "note": "연료비"},
        {"label": "산업용 수도", "keywords": ["산업용수도", "수도"], "note": "공업용수"},
        {"label": "합금철", "keywords": ["합금철", "페로망간", "페로실리콘"], "note": "성분 조정"},
    ],

    # ── 상위 지수 (7개) ──
    "상위 지수": [
        {"label": "생산자물가 총지수", "keywords": ["총지수"], "note": "전체 물가 흐름"},
        {"label": "공산품", "keywords": ["공산품"], "note": "제조업 전반"},
        {"label": "기계 및 장비", "keywords": ["기계및장비"], "note": "기계 설비 전반"},
        {"label": "전기장비(대분류)", "keywords": ["전기장비"], "note": "전기 설비 전반"},
        {"label": "제1차 금속제품(대분류)", "keywords": ["제1차금속제품"], "note": "철강 소재"},
        {"label": "비금속광물제품(대분류)", "keywords": ["비금속광물제품"], "note": "시멘트·내화물"},
        {"label": "화학제품(대분류)", "keywords": ["화학제품"], "note": "약품·도료"},
    ],
}


def get_processes():
    """구분 목록 반환 (기계 / 전기 / 계측·제어 / 토건·구조 / …)"""
    return list(STEEL_PLANT_ITEMS.keys())


def get_items(process: str):
    """특정 구분의 품목 목록"""
    return STEEL_PLANT_ITEMS.get(process, [])


def get_all_items_flat(dedup: bool = False):
    """
    전체 품목을 (구분, 항목) 평면 리스트로.

    dedup=True : 같은 label이 여러 구분에 있으면 처음 것만 남긴다.
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


def counts_by_process() -> dict:
    """구분별 품목 수"""
    return {p: len(items) for p, items in STEEL_PLANT_ITEMS.items()}
