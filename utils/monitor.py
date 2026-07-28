"""
철강 플랜트 품목 물가 모니터링 로직
- 품목명 키워드 → ECOS 실제 ITEM_CODE 자동 해석 (하드코딩 없음)
- 월별 시계열 조회 + 최신지수/전월비/전년동월비 계산
"""
from __future__ import annotations
import re
from typing import Optional, List, Dict

import pandas as pd


def _norm(s: str) -> str:
    """공백 제거 + 소문자화 (카탈로그 ITEM_NAME_NORM과 동일 규칙)"""
    return re.sub(r"\s+", "", str(s)).lower()


def resolve_item(catalog: pd.DataFrame, keywords: List[str]) -> Optional[Dict]:
    """
    키워드 목록으로 ECOS 카탈로그에서 품목을 찾는다.
    우선순위: 키워드 순서 → 완전일치 → 이름이 짧은 것(상위·대표 품목일 가능성)

    Returns {code, name, matched} or None
    """
    if catalog is None or len(catalog) == 0:
        return None
    if "ITEM_NAME" not in catalog.columns:
        return None

    name_col = "ITEM_NAME_NORM" if "ITEM_NAME_NORM" in catalog.columns else None
    names_norm = (
        catalog[name_col]
        if name_col
        else catalog["ITEM_NAME"].astype(str).map(_norm)
    )

    for kw in keywords:
        k = _norm(kw)
        if not k:
            continue

        # 1) 완전일치 우선
        exact = catalog[names_norm == k]
        if len(exact) > 0:
            row = exact.iloc[0]
            return {
                "code": str(row["ITEM_CODE"]),
                "name": str(row["ITEM_NAME"]),
                "matched": kw,
            }

        # 2) 부분일치 → 이름 짧은 순 (대표 품목 우선)
        part = catalog[names_norm.str.contains(re.escape(k), na=False)]
        if len(part) > 0:
            part = part.assign(_len=part["ITEM_NAME"].astype(str).str.len())
            row = part.sort_values("_len").iloc[0]
            return {
                "code": str(row["ITEM_CODE"]),
                "name": str(row["ITEM_NAME"]),
                "matched": kw,
            }

    return None


def compute_metrics(df: pd.DataFrame) -> Dict:
    """
    시계열에서 최신지수·전월비·전년동월비 계산
    df: DataFrame[TIME(YYYYMM), DATA_VALUE]
    """
    if df is None or len(df) == 0:
        return {"latest": None, "period": None, "mom": None, "yoy": None}

    d = df.dropna(subset=["DATA_VALUE"]).sort_values("TIME").reset_index(drop=True)
    if len(d) == 0:
        return {"latest": None, "period": None, "mom": None, "yoy": None}

    latest = float(d["DATA_VALUE"].iloc[-1])
    period = str(d["TIME"].iloc[-1])

    mom = None
    if len(d) >= 2:
        prev = float(d["DATA_VALUE"].iloc[-2])
        if prev:
            mom = (latest / prev - 1) * 100

    yoy = None
    # 12개월 전 같은 달 찾기
    try:
        y, m = int(period[:4]), int(period[4:6])
        target = f"{y-1}{m:02d}"
        row = d[d["TIME"].astype(str) == target]
        if len(row) > 0:
            base = float(row["DATA_VALUE"].iloc[0])
            if base:
                yoy = (latest / base - 1) * 100
    except Exception:
        pass

    return {"latest": latest, "period": period, "mom": mom, "yoy": yoy}


def build_monitor(
    client,
    items: List[Dict],
    catalog: pd.DataFrame,
    start: str,
    end: str,
) -> Dict:
    """
    품목 목록을 모니터링용 데이터로 변환

    items : [{label, keywords, note}, ...]
    Returns {
      "rows": [{label, note, code, ecos_name, latest, period, mom, yoy}],
      "series": {code: DataFrame},
      "unresolved": [label, ...],
    }
    """
    rows, series, unresolved = [], {}, []

    for it in items:
        resolved = resolve_item(catalog, it.get("keywords", []))
        if not resolved:
            unresolved.append(it.get("label", "?"))
            continue

        code = resolved["code"]
        try:
            df = client.get_ppi(code, start, end)
        except Exception as e:
            print(f"[monitor] {it.get('label')} ({code}) 조회 실패: {e}")
            unresolved.append(f"{it.get('label')} (조회실패)")
            continue

        met = compute_metrics(df)
        series[code] = df
        rows.append({
            "label": it.get("label", ""),
            "note": it.get("note", ""),
            "code": code,
            "ecos_name": resolved["name"],
            **met,
        })

    return {"rows": rows, "series": series, "unresolved": unresolved}
