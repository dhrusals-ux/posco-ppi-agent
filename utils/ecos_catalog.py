"""
ECOS 품목 카탈로그 자동 로더 + 자연어 매칭
- 앱 시작 시 ECOS에서 품목 목록 전체를 한 번만 받아 캐시
- Streamlit @st.cache_data로 1시간 유효
- 동의어·부분일치 기반 자연어 → 실제 ITEM_CODE 자동 매칭
"""
from __future__ import annotations
import os
import re
from typing import Optional, List, Dict, Tuple

import pandas as pd


# ─────────────────────────────────────────────
# 동의어 사전 (자연어 키워드 → ECOS 품목명 후보)
# 왼쪽 = 사용자가 쓸 법한 표현 / 오른쪽 = ECOS에 실제 들어있을 법한 단어(부분 일치)
# ─────────────────────────────────────────────
SYNONYMS: Dict[str, List[str]] = {
    # 기계
    "압연기": ["압연", "금속가공기계", "제철"],
    "크레인": ["크레인", "기중기", "운반"],
    "펌프": ["펌프"],
    "컨베이어": ["컨베이어", "운반"],
    "로봇": ["로봇"],
    "터빈": ["터빈", "원동기"],
    "보일러": ["보일러"],
    "공조": ["공조", "냉동"],
    "굴삭기": ["굴삭", "건설기계"],

    # 전기
    "변압기": ["변압기"],
    "전동기": ["전동기", "모터"],
    "모터": ["전동기", "모터"],
    "발전기": ["발전기"],
    "배전반": ["배전반", "배전"],
    "제어반": ["배전반", "제어"],
    "케이블": ["케이블", "전선"],
    "전선": ["전선", "케이블"],
    "조명": ["조명", "램프"],

    # 토건/구조
    "철강": ["철강", "1차철강", "강재"],
    "철근": ["철근"],
    "형강": ["형강"],
    "강판": ["강판", "열연", "냉연"],
    "h빔": ["형강", "후판"],
    "후판": ["후판"],
    "시멘트": ["시멘트"],
    "콘크리트": ["콘크리트", "레미콘"],
    "레미콘": ["레미콘"],
    "내화": ["내화", "벽돌"],
    "단열": ["단열"],

    # 계측/제어
    "계측기": ["계측", "계량기"],
    "분석기": ["분석기"],
    "plc": ["제어"],
    "dcs": ["제어"],

    # 포스코 특화
    "코크스": ["코크스", "석탄"],
    "고로": ["선철", "철강"],
    "제철": ["철강", "제강"],
    "압연": ["압연"],
}


# ─────────────────────────────────────────────
# 카탈로그 로더
# ─────────────────────────────────────────────
def _load_catalog_raw(stat_code: str = "404Y014", api_key: Optional[str] = None) -> pd.DataFrame:
    """
    ECOS StatisticItemList 엔드포인트에서 전체 품목 목록을 가져옴
    네트워크/키 문제 시 빈 DataFrame 반환
    """
    from utils.ecos_client import ECOSClient
    try:
        client = ECOSClient(api_key=api_key)
        df = client.list_items(stat_code)
        if "ITEM_NAME" in df.columns:
            df["ITEM_NAME_NORM"] = df["ITEM_NAME"].astype(str).str.replace(r"\s+", "", regex=True).str.lower()
        return df
    except Exception as e:
        print(f"[ecos_catalog] 카탈로그 로드 실패: {e}")
        return pd.DataFrame()


def get_catalog(stat_code: str = "404Y014", api_key: Optional[str] = None) -> pd.DataFrame:
    """
    Streamlit 환경이면 @st.cache_data 로 1시간 캐싱,
    아니면 프로세스 전역 캐시로 1회 로드
    """
    try:
        import streamlit as st

        @st.cache_data(ttl=3600, show_spinner=False)
        def _cached(stat_code: str, api_key: str):
            return _load_catalog_raw(stat_code, api_key)

        return _cached(stat_code, api_key or os.getenv("ECOS_API_KEY", ""))
    except Exception:
        # Streamlit 미설치 / 런타임 외 환경
        global _PROCESS_CACHE
        if "_PROCESS_CACHE" not in globals():
            _PROCESS_CACHE = {}
        key = (stat_code, api_key or os.getenv("ECOS_API_KEY", ""))
        if key not in _PROCESS_CACHE:
            _PROCESS_CACHE[key] = _load_catalog_raw(stat_code, api_key)
        return _PROCESS_CACHE[key]


# ─────────────────────────────────────────────
# 자연어 → 실제 ITEM_CODE 매칭
# ─────────────────────────────────────────────
def _score_candidate(row, keyword: str, synonyms: List[str]) -> float:
    """한 품목 행과 키워드의 매칭 점수"""
    name = str(row.get("ITEM_NAME_NORM", "") or "")
    if not name:
        return 0.0

    kw = keyword.replace(" ", "").lower()
    score = 0.0

    # 1) 키워드 자체 포함 (가장 강함)
    if kw and kw in name:
        score += 10.0
        if name == kw:
            score += 20.0  # 완전 일치 보너스

    # 2) 동의어 포함
    for syn in synonyms:
        syn_norm = syn.replace(" ", "").lower()
        if syn_norm and syn_norm in name:
            score += 3.0

    # 3) 하위 레벨 우선 (구체적 품목일수록 높은 LEVEL)
    try:
        lvl = int(row.get("ITEM_LEVEL") or 1)
        score += lvl * 0.5
    except (ValueError, TypeError):
        pass

    # 4) 가중치(WGT)가 크면 대표 품목일 가능성 ↑
    try:
        wgt = float(row.get("WGT") or 0)
        score += min(wgt * 0.01, 2.0)  # 가중치 상한
    except (ValueError, TypeError):
        pass

    return score


def auto_match_code(
    user_text: str,
    catalog_df: Optional[pd.DataFrame] = None,
    min_score: float = 5.0,
    top_n: int = 5,
) -> Tuple[Optional[Dict], List[Dict]]:
    """
    자연어 텍스트에서 품목 키워드를 뽑아 ECOS 실제 코드로 매칭

    Returns
    -------
    (best_match, candidates)
        best_match: {"code": "6114", "name": "압연강재", "score": 13.5} or None
        candidates: 상위 top_n 후보 리스트 (UI에 표시용)
    """
    if catalog_df is None:
        catalog_df = get_catalog()
    if catalog_df is None or len(catalog_df) == 0:
        return None, []

    text = user_text.lower()

    # 텍스트에서 동의어 사전 키워드 탐색
    hits: List[Tuple[str, List[str]]] = []  # (keyword, synonyms)
    for kw, syns in SYNONYMS.items():
        if kw.replace(" ", "").lower() in text.replace(" ", ""):
            hits.append((kw, syns + [kw]))

    # 사전에 없는 단어도 2글자 이상 한글 명사 단위로 시도
    nouns = re.findall(r"[가-힣]{2,}", user_text)
    for n in nouns:
        if n in ["기준", "환산", "투자", "설비", "시점", "현재", "기간", "금액", "현재가"]:
            continue
        if not any(n == kw for kw, _ in hits):
            hits.append((n, [n]))

    if not hits:
        return None, []

    # 각 후보 행에 대해 점수 계산
    best_global_rows = []
    for kw, syns in hits:
        scores = catalog_df.apply(lambda r: _score_candidate(r, kw, syns), axis=1)
        scored = catalog_df.assign(_score=scores)
        scored = scored[scored["_score"] >= min_score].sort_values("_score", ascending=False)
        for _, row in scored.head(top_n).iterrows():
            best_global_rows.append({
                "code": str(row.get("ITEM_CODE", "")),
                "name": str(row.get("ITEM_NAME", "")),
                "level": row.get("ITEM_LEVEL"),
                "score": float(row["_score"]),
                "matched_keyword": kw,
            })

    if not best_global_rows:
        return None, []

    # 중복 제거 + 점수순 정렬
    seen = set()
    unique = []
    for r in sorted(best_global_rows, key=lambda x: -x["score"]):
        if r["code"] not in seen:
            seen.add(r["code"])
            unique.append(r)

    best = unique[0] if unique else None
    return best, unique[:top_n]
