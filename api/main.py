"""
POSCO 투자비 물가보정 API

기존 utils/ 로직을 그대로 감싼 REST 레이어. Streamlit UI와 동일한 계산 경로를 쓰므로
두 곳의 숫자가 갈라지지 않는다.

핵심 설계
  - 승인 게이트를 서버에서 강제한다 (POST /batch/adjust → 409).
    Streamlit에서는 게이트가 UI에 있었지만 웹 API는 프론트를 우회할 수 있다.
    미확인 저신뢰 매칭으로 금액을 만들어내는 경로를 서버가 막아야 한다.
  - LIVE 전용 (원칙 2). 키 없으면 503으로 명확히 실패한다.
  - 품목·공종 코드 하드코딩 없음 (원칙 1). 카탈로그를 런타임에 조회한다.
  - 모든 환산 응답에 면책 문구를 실어 보낸다 (원칙 6).

실행:
    uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pandas as pd
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from api import schemas as S
from api.deps import get_ecos_client, get_kosis_client, upstream_error
from utils.batch_adjust import (
    MAX_ROWS, approval_blockers, guess_columns, read_table, run_batch,
    suggest_matches, summarize,
)
from utils.construction_catalog import catalog_to_options, get_construction_catalog
from utils.ecos_catalog import get_catalog
from utils.forecast import MAX_HORIZON, forecast_index
from utils.forecast_eval import backtest as bt_backtest

KST = timezone(timedelta(hours=9))

app = FastAPI(
    title="POSCO 투자비 물가보정 API",
    description=(
        "한국은행 ECOS 생산자물가지수(설비비)와 한국건설기술연구원 건설공사비지수(공사비)를 "
        "실시간 조회해 과거 투자비를 현재가치로 환산합니다. 내부 검토용입니다."
    ),
    version="1.0.0",
)

# 프론트엔드가 다른 오리진에서 뜨므로 CORS가 필요하다.
# 와일드카드를 기본값으로 두지 않는다 — 사내 도구이므로 명시적으로 허용한다.
_origins = [
    o.strip() for o in os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# 공통 헬퍼
# ─────────────────────────────────────────────
def _series_to_points(df: pd.DataFrame) -> list[S.SeriesPoint]:
    d = df.dropna(subset=["DATA_VALUE"]).sort_values("TIME")
    return [
        S.SeriesPoint(period=str(r.TIME), value=float(r.DATA_VALUE))
        for r in d.itertuples()
    ]


def _default_target() -> str:
    """
    목표시점 기본값 (원칙 7).
    건설공사비지수는 발표가 1~2개월 지연되므로 현재월을 기본값으로 두면
    사용자가 매번 '데이터 없음'을 만난다. 약 2개월 전을 기본으로 한다.
    """
    return (datetime.now(KST) - timedelta(days=62)).strftime("%Y%m")


def _adjust(client, code: str, req: S.AdjustRequest, label: str) -> S.AdjustResponse:
    lo, hi = sorted([req.base, req.target])
    try:
        df = client.get_ppi(code, lo, hi)
    except Exception as e:
        raise upstream_error(e, f"{label} {code} 조회 실패") from e

    s = df.copy()
    s["TIME"] = s["TIME"].astype(str)

    def pick(period: str):
        hit = s.loc[s["TIME"] == period, "DATA_VALUE"]
        return float(hit.iloc[0]) if len(hit) else None

    base_idx, target_idx = pick(req.base), pick(req.target)

    missing = []
    if base_idx is None:
        missing.append(f"기준시점 {req.base}")
    if target_idx is None:
        missing.append(f"목표시점 {req.target}")
    if missing:
        raise HTTPException(
            status_code=404,
            detail=(
                f"{', '.join(missing)}의 지수가 없습니다. "
                f"미발표 시점일 수 있습니다 (권장 목표시점: {_default_target()})."
            ),
        )
    if base_idx == 0:
        raise HTTPException(status_code=422, detail="기준시점 지수가 0이어서 보정할 수 없습니다.")

    factor = target_idx / base_idx
    adjusted = req.amount * factor
    name = None
    if "ITEM_NAME1" in df.columns and len(df):
        name = str(df["ITEM_NAME1"].iloc[0])

    return S.AdjustResponse(
        code=code, name=name, amount=req.amount,
        base=req.base, target=req.target,
        base_index=round(base_idx, 4), target_index=round(target_idx, 4),
        factor=round(factor, 6), adjusted=round(adjusted, 2),
        delta=round(adjusted - req.amount, 2),
        delta_pct=round((factor - 1) * 100, 4),
    )


def _forecast(client, code: str, horizon: int, label: str) -> S.ForecastResponse:
    try:
        hist = client.get_ppi(code, "201501", datetime.now(KST).strftime("%Y%m"))
    except Exception as e:
        raise upstream_error(e, f"{label} {code} 조회 실패") from e

    if len(hist) < 6:
        raise HTTPException(
            status_code=422,
            detail=f"예측에 필요한 과거 데이터가 부족합니다 (확보 {len(hist)}개월, 최소 6개월).",
        )

    res = forecast_index(hist, horizon=horizon)
    fc, lo, up = res["forecast"], res["lower"], res["upper"]

    return S.ForecastResponse(
        code=code,
        method=res["method"],
        horizon=len(fc),
        history=[
            S.SeriesPoint(period=idx.strftime("%Y%m"), value=round(float(v), 4))
            for idx, v in res["history"].items()
        ],
        forecast=[
            S.ForecastPoint(
                period=idx.strftime("%Y%m"),
                value=round(float(fc.loc[idx]), 4),
                lower=round(float(lo.loc[idx]), 4),
                upper=round(float(up.loc[idx]), 4),
            )
            for idx in fc.index
        ],
        warning=res["warning"],
    )


# ─────────────────────────────────────────────
# 메타
# ─────────────────────────────────────────────
@app.get("/health", tags=["메타"])
def health():
    """키 설정 여부만 노출한다. 키 값 자체는 절대 응답에 담지 않는다."""
    return {
        "status": "ok",
        "ecos_key_configured": bool(os.getenv("ECOS_API_KEY")),
        "kosis_key_configured": bool(os.getenv("KOSIS_API_KEY")),
        "server_time_kst": datetime.now(KST).isoformat(timespec="seconds"),
    }


@app.get("/meta", tags=["메타"])
def meta():
    """프론트엔드가 기본값·제약을 하드코딩하지 않도록 서버가 알려준다."""
    return {
        "formula": "환산액 = 원금 × (목표시점 지수 ÷ 기준시점 지수)",
        "disclaimer": S.DISCLAIMER,
        "default_target_period": _default_target(),
        "default_target_note": (
            "건설공사비지수는 발표가 1~2개월 지연되므로 목표시점 기본값을 약 2개월 전으로 둡니다."
        ),
        "max_batch_rows": MAX_ROWS,
        "max_forecast_horizon": MAX_HORIZON,
        "confidence_levels": ["높음", "중간", "낮음", "실패"],
        "auto_approved_levels": ["높음"],
        "sources": {
            "equipment": "한국은행 ECOS 생산자물가지수 404Y014 (2020=100)",
            "construction": "한국건설기술연구원 건설공사비지수 KOSIS DT_39701_A003 (2020=100)",
        },
    }


# ─────────────────────────────────────────────
# 카탈로그
# ─────────────────────────────────────────────
@app.get("/catalog/equipment", response_model=S.CatalogResponse, tags=["카탈로그"])
def catalog_equipment(
    q: str | None = Query(None, description="품목명 부분 검색"),
    client=Depends(get_ecos_client),
):
    """ECOS 품목 카탈로그. 코드를 하드코딩하지 않고 런타임에 조회한다 (원칙 1)."""
    cat = get_catalog(api_key=client.api_key)
    if cat is None or len(cat) == 0:
        raise HTTPException(status_code=502, detail="ECOS 품목 카탈로그를 불러오지 못했습니다.")

    if q:
        mask = cat["ITEM_NAME"].astype(str).str.contains(q, case=False, na=False)
        cat = cat[mask]

    items = [
        S.CatalogItem(
            code=str(r.ITEM_CODE), name=str(r.ITEM_NAME),
            level=int(r.ITEM_LEVEL) if str(getattr(r, "ITEM_LEVEL", "")).isdigit() else None,
        )
        for r in cat.itertuples()
    ]
    return S.CatalogResponse(source="404Y014", count=len(items), items=items)


@app.get("/catalog/construction", response_model=S.CatalogResponse, tags=["카탈로그"])
def catalog_construction(client=Depends(get_kosis_client)):
    """KOSIS 건설공사비지수 공종 분류. itmId=ALL·objL1=ALL로 실제 분류를 발견한다."""
    cat = get_construction_catalog(api_key=client.api_key)
    if cat is None or len(cat) == 0:
        raise HTTPException(status_code=502, detail="KOSIS 공종 카탈로그를 불러오지 못했습니다.")

    opts = catalog_to_options(cat)
    items = [S.CatalogItem(code=str(o["code"]), name=str(o["name"])) for o in opts]
    return S.CatalogResponse(source="DT_39701_A003", count=len(items), items=items)


# ─────────────────────────────────────────────
# 시계열
# ─────────────────────────────────────────────
@app.get("/series/equipment/{code}", response_model=S.SeriesResponse, tags=["시계열"])
def series_equipment(
    code: str,
    start: str = Query("201501", pattern=S.PERIOD_PATTERN),
    end: str | None = Query(None, pattern=S.PERIOD_PATTERN),
    client=Depends(get_ecos_client),
):
    end = end or datetime.now(KST).strftime("%Y%m")
    try:
        df = client.get_ppi(code, start, end)
    except Exception as e:
        raise upstream_error(e, f"ECOS {code} 조회 실패") from e
    name = str(df["ITEM_NAME1"].iloc[0]) if "ITEM_NAME1" in df.columns and len(df) else None
    return S.SeriesResponse(code=code, name=name, start=start, end=end,
                            points=_series_to_points(df))


@app.get("/series/construction/{code}", response_model=S.SeriesResponse, tags=["시계열"])
def series_construction(
    code: str,
    start: str = Query("201501", pattern=S.PERIOD_PATTERN),
    end: str | None = Query(None, pattern=S.PERIOD_PATTERN),
    client=Depends(get_kosis_client),
):
    end = end or _default_target()
    try:
        df = client.get_ppi(code, start, end)
    except Exception as e:
        raise upstream_error(e, f"KOSIS {code} 조회 실패") from e
    return S.SeriesResponse(code=code, start=start, end=end, points=_series_to_points(df))


# ─────────────────────────────────────────────
# 단일 환산
# ─────────────────────────────────────────────
@app.post("/adjust/equipment", response_model=S.AdjustResponse, tags=["환산"])
def adjust_equipment(req: S.AdjustRequest, client=Depends(get_ecos_client)):
    """설비 투자비 환산 (ECOS 생산자물가지수)"""
    return _adjust(client, req.code, req, "ECOS")


@app.post("/adjust/construction", response_model=S.AdjustResponse, tags=["환산"])
def adjust_construction(req: S.AdjustRequest, client=Depends(get_kosis_client)):
    """공사비 환산 (건설공사비지수)"""
    return _adjust(client, req.code, req, "KOSIS")


# ─────────────────────────────────────────────
# 엑셀 일괄 보정
# ─────────────────────────────────────────────
@app.post("/batch/parse", response_model=S.ParsedTable, tags=["일괄 보정"])
async def batch_parse(
    file: UploadFile = File(..., description="견적 엑셀 (xlsx/xls/csv)"),
    preview: int = Query(20, ge=1, le=200, description="반환할 미리보기 행 수"),
):
    """
    업로드된 견적서를 읽어 컬럼 목록과 추정 결과를 반환한다.
    컬럼 추정은 '기본 선택값' 제안이며, 사용자가 바꿀 수 있어야 한다.
    """
    import io as _io

    raw = await file.read()
    try:
        df = read_table(_io.BytesIO(raw), file.filename or "")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"파일을 읽을 수 없습니다: {e}") from e

    if df is None or len(df) == 0:
        raise HTTPException(status_code=422, detail="빈 파일입니다.")

    item_col, amount_col = guess_columns(df)
    head = df.head(preview).where(pd.notna(df.head(preview)), None)
    return S.ParsedTable(
        columns=[str(c) for c in df.columns],
        guessed_item_column=str(item_col) if item_col is not None else None,
        guessed_amount_column=str(amount_col) if amount_col is not None else None,
        row_count=int(len(df)),
        rows=head.to_dict(orient="records"),
    )


@app.post("/batch/suggest", response_model=S.SuggestResponse, tags=["일괄 보정"])
def batch_suggest(req: S.SuggestRequest, client=Depends(get_ecos_client)):
    """
    품목명 → ECOS 품목 자동 제안 + 신뢰도·판단근거.

    '판단근거'를 함께 돌려주는 이유: 등급만 주면 검토자가 그대로 믿는다.
    근거를 읽고 스스로 판단할 수 있어야 조용히 틀린 금액을 막을 수 있다.
    """
    if len(req.items) > MAX_ROWS:
        raise HTTPException(
            status_code=422,
            detail=f"행 수 {len(req.items)}건이 상한 {MAX_ROWS}건을 초과합니다. 나눠서 요청하세요.",
        )

    cat = get_catalog(api_key=client.api_key)
    if cat is None or len(cat) == 0:
        raise HTTPException(status_code=502, detail="ECOS 품목 카탈로그를 불러오지 못했습니다.")

    df = pd.DataFrame([{"품목명": it.name, "금액": it.amount} for it in req.items])
    rev = suggest_matches(df, "품목명", "금액", cat, top_n=req.top_n)

    # 요청이 준 실제 엑셀 행번호로 덮어쓴다 (suggest_matches는 0-base+2로 채움)
    rev["행"] = [it.row for it in req.items]

    out = [
        S.Suggestion(
            row=int(r["행"]),
            name=str(r["견적품목명"]),
            amount=None if pd.isna(r["금액"]) else float(r["금액"]),
            code=str(r["제안코드"]),
            ecos_name=str(r["제안품목"]),
            confidence=str(r["신뢰도"]),
            reason=str(r["판단근거"]),
            amount_error=str(r["금액오류"] or ""),
            candidates=[
                S.Candidate(
                    code=str(c.get("code", "")), name=str(c.get("name", "")),
                    score=float(c.get("score", 0)),
                    matched_keyword=c.get("matched_keyword"),
                )
                for c in (r["후보"] or [])
            ],
        )
        for _, r in rev.iterrows()
    ]

    counts = rev["신뢰도"].value_counts()
    return S.SuggestResponse(
        count=len(out),
        high=int(counts.get("높음", 0)),
        medium=int(counts.get("중간", 0)),
        low=int(counts.get("낮음", 0)),
        failed=int(counts.get("실패", 0)),
        suggestions=out,
    )


@app.post(
    "/batch/adjust",
    response_model=S.BatchAdjustResponse,
    responses={409: {"model": S.BlockedResponse}},
    tags=["일괄 보정"],
)
def batch_adjust(req: S.BatchAdjustRequest, client=Depends(get_ecos_client)):
    """
    승인된 매칭표를 일괄 환산한다.

    ★ 승인 게이트를 서버에서 강제한다. 프론트엔드를 우회해 미확인 저신뢰 매칭을
      보내면 409로 거부한다 — 틀린 매칭이 조용히 금액을 만들어 품의서에 들어가는
      경로를 서버가 막아야 한다.
    """
    if not req.rows:
        raise HTTPException(status_code=422, detail="보정할 행이 없습니다.")

    rev = pd.DataFrame([
        {
            "행": r.row,
            "견적품목명": r.name,
            "금액": r.amount,
            "제안코드": (r.code or "").strip(),
            "제안품목": "",
            "신뢰도": r.confidence,
            "확인": bool(r.confirmed),
        }
        for r in req.rows
    ])

    blockers = approval_blockers(rev)
    if blockers:
        raise HTTPException(
            status_code=409,
            detail={
                "detail": "승인되지 않은 항목이 있어 일괄 보정을 실행할 수 없습니다.",
                "blockers": blockers,
            },
        )

    try:
        res = run_batch(rev, client, req.base, req.target)
    except Exception as e:
        raise upstream_error(e, "일괄 보정 실패") from e

    sm = summarize(res)

    def _f(v):
        return None if v is None or pd.isna(v) else float(v)

    rows = [
        S.BatchResultRow(
            row=None if pd.isna(r["행"]) else int(r["행"]),
            name=str(r["견적품목명"]),
            ecos_name=str(r["ECOS품목"]),
            code=str(r["품목코드"]),
            confidence=str(r["신뢰도"]),
            confirmed=bool(r["확인"]),
            amount=_f(r["원금"]),
            base_index=_f(r["기준지수"]),
            target_index=_f(r["목표지수"]),
            factor=_f(r["보정계수"]),
            adjusted=_f(r["환산액"]),
            delta=_f(r["증감액"]),
            delta_pct=_f(r["증감률(%)"]),
            error=str(r["오류"] or ""),
        )
        for _, r in res.iterrows()
    ]

    warning = None
    if sm["실패"]:
        warning = (
            f"{sm['실패']}건은 환산하지 못해 합계에서 제외했습니다. "
            "따라서 합계가 견적 전체 금액과 다릅니다. 각 행의 error를 확인하세요."
        )

    return S.BatchAdjustResponse(
        base=req.base, target=req.target,
        summary=S.BatchSummary(
            count=sm["건수"], succeeded=sm["성공"], failed=sm["실패"],
            principal_total=sm["원금합계"], adjusted_total=sm["환산합계"],
            delta=sm["증감액"], delta_pct=sm["증감률(%)"],
            low_confidence_count=sm["저신뢰건수"],
        ),
        rows=rows,
        warning=warning,
    )


# ─────────────────────────────────────────────
# 예측
# ─────────────────────────────────────────────
@app.get("/forecast/equipment/{code}", response_model=S.ForecastResponse, tags=["예측"])
def forecast_equipment(
    code: str,
    horizon: int = Query(12, ge=1, le=MAX_HORIZON),
    client=Depends(get_ecos_client),
):
    """
    설비 PPI 예측. 점 추정이 아니라 95% 신뢰구간 밴드로 돌려주고,
    사용 방법론과 경고를 함께 실어 보낸다 (원칙 5). 'AI 예측'이 아니다.
    """
    return _forecast(client, code, horizon, "ECOS")


@app.get("/forecast/construction/{code}", response_model=S.ForecastResponse, tags=["예측"])
def forecast_construction(
    code: str,
    horizon: int = Query(12, ge=1, le=MAX_HORIZON),
    client=Depends(get_kosis_client),
):
    """건설공사비지수 예측"""
    return _forecast(client, code, horizon, "KOSIS")


def _backtest(client, code: str, horizon: int, folds: int, label: str) -> dict:
    try:
        hist = client.get_ppi(code, "200501", datetime.now(KST).strftime("%Y%m"))
    except Exception as e:
        raise upstream_error(e, f"{label} {code} 조회 실패") from e

    res = bt_backtest(hist, horizon=horizon, folds=folds)
    if not res["ok"]:
        raise HTTPException(status_code=422, detail=res["reason"])

    res["code"] = code
    res["disclaimer"] = S.DISCLAIMER
    res["caveat"] = (
        "백테스트가 좋아도 미래를 보장하지 않습니다. 과거에 없던 충격"
        "(원자재 급등·정책 변화)은 어떤 방법도 예측하지 못합니다."
    )
    return res


@app.get("/forecast/backtest/equipment/{code}", tags=["예측"])
def backtest_equipment(
    code: str,
    horizon: int = Query(12, ge=1, le=MAX_HORIZON),
    folds: int = Query(6, ge=2, le=12),
    client=Depends(get_ecos_client),
):
    """
    예측 검증 (walk-forward 백테스트).

    naive(마지막 값 유지)를 기준으로 각 방법을 비교한다. naive를 이기지 못하면
    그 품목에서는 예측이 값을 더하지 못한다는 뜻이고, best가 "naive"로 돌아온다.
    프론트엔드는 best와 best_reason을 그대로 보여줘야 한다 — 검증 결과를 숨기고
    예측값만 보여주면 사용자는 근거 없이 신뢰하게 된다.
    """
    return _backtest(client, code, horizon, folds, "ECOS")


@app.get("/forecast/backtest/construction/{code}", tags=["예측"])
def backtest_construction(
    code: str,
    horizon: int = Query(12, ge=1, le=MAX_HORIZON),
    folds: int = Query(6, ge=2, le=12),
    client=Depends(get_kosis_client),
):
    """건설공사비지수 예측 검증"""
    return _backtest(client, code, horizon, folds, "KOSIS")
