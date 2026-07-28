"""
건설공사비지수 공종 카탈로그 자동 로더
- KOSIS 통계표(DT_39701_A003)의 실제 공종 분류를 런타임에 받아 캐싱
- ECOS 카탈로그(ecos_catalog.py)와 동일한 철학: 코드 하드코딩 없이 자동 발견
- Streamlit @st.cache_data로 1시간 유효
"""
from __future__ import annotations
import os
from typing import Optional

import pandas as pd

try:
    import streamlit as st
    HAS_ST = True
except ImportError:
    HAS_ST = False


def _load_raw(api_key: Optional[str] = None) -> pd.DataFrame:
    """KOSIS에서 공종 분류 목록을 받아옴. 실패 시 빈 DataFrame."""
    from utils.kosis_client import KOSISClient
    try:
        client = KOSISClient(api_key=api_key)
        cat = client.discover_categories()
        return cat if cat is not None else pd.DataFrame()
    except Exception as e:
        print(f"[construction_catalog] 로드 실패: {e}")
        return pd.DataFrame()


_PROCESS_CACHE: dict = {}
_PROCESS_CACHE_TTL = 3600  # 초


def _process_cached(api_key: str) -> pd.DataFrame:
    """
    Streamlit 없는 환경(FastAPI 등 장기 실행 서버)용 TTL 캐시.
    없으면 매 요청마다 KOSIS 전체 분류를 다시 받게 되어 트래픽 한도(에러 31)에 걸린다.
    """
    import time

    hit = _PROCESS_CACHE.get(api_key)
    if hit is not None:
        ts, df = hit
        if time.monotonic() - ts < _PROCESS_CACHE_TTL:
            return df

    df = _load_raw(api_key)
    # 빈 결과는 캐시하지 않는다 (일시적 오류를 1시간 고정시키지 않기 위해)
    if df is not None and len(df) > 0:
        _PROCESS_CACHE[api_key] = (time.monotonic(), df)
    return df


if HAS_ST:
    @st.cache_data(ttl=3600, show_spinner=False)
    def get_construction_catalog(api_key: Optional[str] = None) -> pd.DataFrame:
        """공종 카탈로그 (캐시됨). 컬럼: C1, C1_NM, ITM_ID, ITM_NM"""
        return _load_raw(api_key)
else:
    def get_construction_catalog(api_key: Optional[str] = None) -> pd.DataFrame:
        """공종 카탈로그 (프로세스 TTL 캐시)"""
        return _process_cached(api_key or os.getenv("KOSIS_API_KEY", ""))


def catalog_to_options(catalog: pd.DataFrame) -> list:
    """선택용 옵션 리스트 [{code, name}] 생성 (공종 분류 기준, 중복 제거)"""
    if catalog is None or len(catalog) == 0:
        return []
    if "C1" not in catalog.columns:
        return []
    seen = catalog[["C1", "C1_NM"]].drop_duplicates()
    return [
        {"code": str(r["C1"]), "name": str(r.get("C1_NM", r["C1"]))}
        for _, r in seen.iterrows()
    ]
