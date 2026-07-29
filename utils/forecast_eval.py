"""
예측 검증 (walk-forward 백테스트)

왜 필요한가
  utils/forecast.py는 Holt-Winters로 예측하지만, 그게 맞는지 아무도 모른다.
  검증되지 않은 예측을 투자 검토에 쓰는 건 원칙 5(예측은 정직하게)에 어긋난다.

무엇을 확인하는가
  1) naive(마지막 값 그대로)를 이기는가 — 월별 물가지수에서 naive는 강한 상대다.
     못 이기면 그 품목에서는 예측 기능이 값이 없다는 뜻이고, 그 사실을 말해야 한다.
  2) 95% 신뢰구간이 실제로 95%를 담는가(coverage) — 밴드가 좁으면 실제보다
     확신 있어 보인다. forecast.py의 밴드는 잔차 표준편차 × sqrt(h) 휴리스틱이라
     모수 불확실성을 반영하지 않으므로 좁게 나올 수 있다. 숫자로 확인해야 한다.
  3) 예측 기간(h)이 길어질수록 얼마나 나빠지는가 — 1개월 뒤와 12개월 뒤는 다르다.

방법
  rolling origin(전진 검증). 시점을 뒤로 옮기며 학습→예측→실측 비교를 반복한다.
  미래 데이터를 학습에 쓰지 않는다(누수 방지).

주의
  백테스트가 좋아도 미래를 보장하지 않는다. 과거에 없던 충격(원자재 급등,
  정책 변화)은 어떤 방법도 예측하지 못한다.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from utils.forecast import MAX_HORIZON, _to_monthly_series

# 신뢰구간 계수 (95%)
Z95 = 1.96

# 백테스트에 필요한 최소 학습 길이 (개월)
MIN_TRAIN = 36

# naive보다 이 정도는 확실히 나아야 복잡한 방법을 추천한다.
# 근거: fold가 겹치고 표본이 적으면 몇 %의 우위는 우연히 나온다.
# 합성 random walk(=예측 불가 계열) 실험에서 단일 실현·8fold 기준으로
# 선형 추세가 naive를 20%대까지 '이기는' 경우가 관측됐다.
MIN_SKILL_TO_RECOMMEND = 0.25

# 평균만 보면 한 fold에서 크게 이기고 나머지에서 진 방법도 통과한다.
# 그래서 '몇 번 이겼는지'(일관성)도 함께 요구한다. 사실상 부호검정이다.
# 이 두 조건을 함께 걸면 random walk 25개 실현에서 오추천이 크게 줄었다.
MIN_WIN_RATE_TO_RECOMMEND = 0.70

# fold가 이보다 적으면 방법 간 비교를 신뢰할 수 없다고 경고한다
MIN_FOLDS_FOR_CONFIDENCE = 4


# ─────────────────────────────────────────────
# 예측 방법들
#
# 모든 방법이 동일한 밴드 규칙(1스텝 오차 표준편차 × Z × sqrt(h))을 쓴다.
# 방법마다 다른 규칙을 쓰면 coverage 비교가 공정하지 않다.
# ─────────────────────────────────────────────
def _band(point: np.ndarray, sigma: float, horizon: int) -> tuple:
    widen = np.sqrt(np.arange(1, horizon + 1))
    margin = Z95 * float(sigma) * widen
    return point - margin, point + margin


def _sigma_from(errors: np.ndarray) -> float:
    e = np.asarray(errors, dtype=float)
    e = e[~np.isnan(e)]
    if len(e) < 2:
        return 0.0
    return float(np.std(e, ddof=1))


def m_naive(train: pd.Series, horizon: int) -> Dict:
    """마지막 값을 그대로 연장. 가장 단순한 베이스라인이지만 강하다."""
    last = float(train.iloc[-1])
    point = np.full(horizon, last)
    sigma = _sigma_from(np.diff(train.values))          # 1개월 변화의 표준편차
    lo, up = _band(point, sigma, horizon)
    return {"point": point, "lower": lo, "upper": up, "label": "naive (마지막 값 유지)"}


def m_drift(train: pd.Series, horizon: int) -> Dict:
    """마지막 값 + 평균 변화량 × h (random walk with drift)"""
    v = train.values.astype(float)
    last = float(v[-1])
    drift = (v[-1] - v[0]) / max(1, len(v) - 1)
    point = last + drift * np.arange(1, horizon + 1)
    sigma = _sigma_from(np.diff(v) - drift)
    lo, up = _band(point, sigma, horizon)
    return {"point": point, "lower": lo, "upper": up, "label": "drift (평균 변화 연장)"}


def m_seasonal_naive(train: pd.Series, horizon: int) -> Dict:
    """12개월 전 같은 달의 값. 계절성이 강하면 유효하다."""
    v = train.values.astype(float)
    if len(v) < 12:
        return m_naive(train, horizon)
    point = np.array([v[-12 + (i % 12)] for i in range(horizon)], dtype=float)
    sigma = _sigma_from(v[12:] - v[:-12])
    lo, up = _band(point, sigma, horizon)
    return {"point": point, "lower": lo, "upper": up, "label": "seasonal naive (12개월 전)"}


def m_linear(train: pd.Series, horizon: int) -> Dict:
    """선형 추세 외삽 — forecast.py의 폴백과 같은 방식(최근 36개월 가중)"""
    v = train.values.astype(float)
    n = len(v)
    x = np.arange(n)
    w = np.ones(n)
    if n > 36:
        w[-36:] = 2.0
    coef = np.polyfit(x, v, 1, w=w)
    point = np.polyval(coef, np.arange(n, n + horizon))
    sigma = _sigma_from(v - np.polyval(coef, x))
    lo, up = _band(point, sigma, horizon)
    return {"point": point, "lower": lo, "upper": up, "label": "선형 추세"}


def m_holt_winters(train: pd.Series, horizon: int) -> Dict:
    """
    Holt-Winters 지수평활. forecast.py의 1순위 방법.
    statsmodels가 없거나 적합에 실패하면 None을 반환한다 —
    조용히 다른 방법으로 바꿔치기하면 비교가 의미를 잃는다.
    """
    n = len(train)
    use_seasonal = n >= 24
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        model = ExponentialSmoothing(
            train,
            trend="add",
            seasonal="add" if use_seasonal else None,
            seasonal_periods=12 if use_seasonal else None,
            initialization_method="estimated",
        ).fit()
        point = np.asarray(model.forecast(horizon), dtype=float)
        sigma = _sigma_from(np.asarray(train - model.fittedvalues, dtype=float))
        lo, up = _band(point, sigma, horizon)
        suffix = "추세+계절성" if use_seasonal else "추세"
        return {"point": point, "lower": lo, "upper": up,
                "label": f"Holt-Winters ({suffix})"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}", "label": "Holt-Winters"}


METHODS: Dict[str, Callable[[pd.Series, int], Dict]] = {
    "naive": m_naive,
    "drift": m_drift,
    "seasonal_naive": m_seasonal_naive,
    "linear": m_linear,
    "holt_winters": m_holt_winters,
}

# 비교 기준 — 이걸 못 이기면 예측이 값을 더하지 않는다
BASELINE = "naive"


# ─────────────────────────────────────────────
# 백테스트
# ─────────────────────────────────────────────
def backtest(
    df: pd.DataFrame,
    horizon: int = 12,
    folds: int = 6,
    step: Optional[int] = None,
    methods: Optional[List[str]] = None,
    min_train: int = MIN_TRAIN,
) -> Dict:
    """
    rolling origin 전진 검증.

    fold f 에서:
        학습 = series[: n - horizon - f*step]
        실측 = 그 다음 horizon 개월
    학습 구간에 미래 데이터가 절대 들어가지 않는다.

    step 기본값 = horizon (검증 구간이 겹치지 않음).
      겹치게 하면(step=1) fold 수는 늘지만 인접 fold가 검증 구간을 대부분
      공유해 '몇 번 이겼는지'가 독립적인 승수가 아니게 된다. 그러면 우연한
      우위가 일관된 우위처럼 보인다. 합성 random walk 실험에서 step=1은
      오추천을 크게 늘렸다.

    Returns dict {
      "ok": bool, "reason": str,
      "horizon": int, "folds_used": int, "n": int,
      "methods": {name: {label, mae, mape, rmse, coverage, skill, by_h: [...], error}},
      "baseline": "naive",
      "best": name, "best_reason": str,
      "notes": [str, ...],
    }
    """
    horizon = max(1, min(int(horizon), MAX_HORIZON))
    step = int(step) if step else horizon      # 기본: 겹치지 않는 검증
    step = max(1, step)
    names = methods or list(METHODS)
    notes: List[str] = []
    if step < horizon:
        notes.append(
            f"검증 구간이 겹칩니다(step={step} < 예측 {horizon}개월). "
            "fold 수는 늘지만 '몇 번 이겼는지'가 독립적인 승수가 아니므로 "
            "방법 간 우위를 과대평가할 수 있습니다."
        )

    hist = _to_monthly_series(df)
    n = len(hist)

    need = min_train + horizon
    if n < need:
        return {
            "ok": False,
            "reason": (
                f"백테스트에 필요한 데이터가 부족합니다. "
                f"확보 {n}개월, 최소 {need}개월 필요 "
                f"(학습 {min_train} + 예측 {horizon})."
            ),
            "horizon": horizon, "folds_used": 0, "n": n,
            "methods": {}, "baseline": BASELINE, "notes": notes,
        }

    # 가능한 fold 수 계산 — 학습 길이가 min_train 아래로 내려가지 않게
    max_folds = 1 + (n - horizon - min_train) // max(1, step)
    folds_used = max(1, min(int(folds), int(max_folds)))
    if folds_used < folds:
        notes.append(
            f"요청한 {folds}회 중 {folds_used}회만 검증했습니다 "
            f"(데이터 길이 {n}개월 제약)."
        )

    # 방법별 오차 누적
    acc: Dict[str, Dict] = {
        name: {"abs": [], "pct": [], "sq": [], "in_band": [],
               "fold_mape": [],          # fold별 MAPE — 일관성 판정용. 인덱스가 fold와 정렬돼야 한다
               "by_h_abs": [[] for _ in range(horizon)],
               "by_h_pct": [[] for _ in range(horizon)],
               "label": name, "error": ""}
        for name in names
    }

    for f in range(folds_used):
        cut = n - horizon - f * step
        train = hist.iloc[:cut]
        actual = hist.iloc[cut:cut + horizon].values.astype(float)
        if len(actual) < horizon:
            continue

        for name in names:
            fn = METHODS.get(name)
            if fn is None:
                acc[name]["error"] = "알 수 없는 방법"
                acc[name]["fold_mape"].append(np.nan)
                continue
            try:
                res = fn(train, horizon)
            except Exception as e:  # noqa: BLE001
                acc[name]["error"] = f"{type(e).__name__}: {e}"
                acc[name]["fold_mape"].append(np.nan)
                continue
            if res.get("error"):
                acc[name]["error"] = res["error"]
                acc[name]["label"] = res.get("label", name)
                # fold 인덱스 정렬을 유지한다 — 어긋나면 승률 비교가 엉뚱해진다
                acc[name]["fold_mape"].append(np.nan)
                continue

            acc[name]["label"] = res.get("label", name)
            point = np.asarray(res["point"], dtype=float)
            lo = np.asarray(res["lower"], dtype=float)
            up = np.asarray(res["upper"], dtype=float)

            err = point - actual
            with np.errstate(divide="ignore", invalid="ignore"):
                pct = np.abs(err) / np.where(actual == 0, np.nan, np.abs(actual)) * 100

            acc[name]["abs"].extend(np.abs(err).tolist())
            acc[name]["pct"].extend(pct.tolist())
            acc[name]["sq"].extend((err ** 2).tolist())
            acc[name]["in_band"].extend(((actual >= lo) & (actual <= up)).tolist())
            acc[name]["fold_mape"].append(float(np.nanmean(pct)))
            for h in range(horizon):
                acc[name]["by_h_abs"][h].append(float(abs(err[h])))
                acc[name]["by_h_pct"][h].append(float(pct[h]))

    # 집계
    def agg(d: Dict) -> Dict:
        if d["error"] and not d["abs"]:
            return {"label": d["label"], "error": d["error"],
                    "mae": None, "mape": None, "rmse": None,
                    "coverage": None, "by_h": []}
        return {
            "label": d["label"],
            "error": d["error"],
            "mae": float(np.nanmean(d["abs"])) if d["abs"] else None,
            "mape": float(np.nanmean(d["pct"])) if d["pct"] else None,
            "rmse": float(np.sqrt(np.nanmean(d["sq"]))) if d["sq"] else None,
            "coverage": (float(np.mean(d["in_band"])) * 100) if d["in_band"] else None,
            "fold_mape": list(d["fold_mape"]),
            "by_h": [
                {
                    "h": h + 1,
                    "mae": float(np.nanmean(d["by_h_abs"][h])) if d["by_h_abs"][h] else None,
                    "mape": float(np.nanmean(d["by_h_pct"][h])) if d["by_h_pct"][h] else None,
                }
                for h in range(horizon)
            ],
        }

    out = {name: agg(d) for name, d in acc.items()}

    # naive 대비 개선도(skill). 1에 가까울수록 좋고, 0 이하면 naive만 못하다.
    base = out.get(BASELINE, {}).get("mape")
    base_folds = out.get(BASELINE, {}).get("fold_mape") or []
    for name, m in out.items():
        if base and m.get("mape") is not None and base > 0:
            m["skill"] = 1 - (m["mape"] / base)
        else:
            m["skill"] = None

        # 승률 — fold별로 naive를 이긴 비율. 평균이 좋아도 일관성이 없으면 잡음이다.
        mf = m.get("fold_mape") or []
        pairs = [
            (a, b) for a, b in zip(mf, base_folds)
            if a is not None and b is not None
            and not np.isnan(a) and not np.isnan(b)
        ]
        if name == BASELINE or not pairs:
            m["win_rate"] = None
            m["wins"] = None
            m["folds_compared"] = len(pairs)
        else:
            wins = sum(1 for a, b in pairs if a < b)
            m["wins"] = wins
            m["folds_compared"] = len(pairs)
            m["win_rate"] = wins / len(pairs)

    # 추천 — naive를 '확실히' 이겨야 복잡한 방법을 권한다.
    # 근소한 우위는 fold가 겹치고 표본이 적은 탓에 우연히 나올 수 있다.
    usable = {k: v for k, v in out.items() if v.get("mape") is not None}
    best, best_reason = None, ""
    if usable:
        cand = min(usable, key=lambda k: usable[k]["mape"])
        cand_skill = usable[cand].get("skill")

        if cand == BASELINE:
            best, best_reason = BASELINE, (
                "naive(마지막 값 유지)가 가장 정확했습니다. "
                "이 품목은 추세·계절성으로 설명되는 부분이 적어, "
                "예측보다 최신 실측치를 그대로 쓰는 편이 낫습니다."
            )
        elif cand_skill is None or cand_skill < MIN_SKILL_TO_RECOMMEND:
            gap = f"{(cand_skill or 0) * 100:.0f}%"
            best, best_reason = BASELINE, (
                f"{usable[cand]['label']}가 naive보다 {gap} 나았지만, "
                f"추천 기준({MIN_SKILL_TO_RECOMMEND * 100:.0f}%)에 못 미칩니다. "
                f"검증 {folds_used}회 규모에서 이 정도 차이는 우연히 나올 수 있어 "
                "naive를 권합니다."
            )
        elif (usable[cand].get("win_rate") or 0) < MIN_WIN_RATE_TO_RECOMMEND:
            wr = usable[cand].get("win_rate") or 0
            best, best_reason = BASELINE, (
                f"{usable[cand]['label']}의 평균 오차는 naive보다 "
                f"{cand_skill * 100:.0f}% 낮지만, 검증 {usable[cand].get('folds_compared', 0)}회 중 "
                f"{usable[cand].get('wins', 0)}회만 이겼습니다(승률 {wr:.0%}). "
                "특정 구간에서만 잘 맞은 것으로 보여 naive를 권합니다."
            )
        else:
            best = cand
            best_reason = (
                f"naive 대비 오차를 {cand_skill * 100:.0f}% 줄였고, "
                f"검증 {usable[cand].get('folds_compared', 0)}회 중 "
                f"{usable[cand].get('wins', 0)}회 이겼습니다."
            )

    # 검정력 경고 — fold가 적으면 방법 간 순위 자체가 우연일 수 있다
    if folds_used < MIN_FOLDS_FOR_CONFIDENCE:
        notes.append(
            f"검증 횟수가 {folds_used}회뿐입니다. 방법 간 순위가 우연히 뒤바뀔 수 있으니 "
            "'어느 방법이 더 낫다'는 결론으로 쓰지 마세요. 과거 데이터가 더 쌓이면 다시 확인하세요."
        )

    # coverage 경고 — 밴드가 좁으면 실제보다 확신 있어 보인다
    for name, m in out.items():
        cov = m.get("coverage")
        if cov is not None and cov < 80:
            notes.append(
                f"{m['label']}: 95% 밴드가 실제값을 {cov:.0f}%만 담았습니다. "
                "구간이 좁아 실제보다 확신 있어 보일 수 있습니다."
            )
    if any(m.get("error") for m in out.values()):
        for name, m in out.items():
            if m.get("error"):
                notes.append(f"{m['label']} 실행 실패: {m['error']}")

    return {
        "ok": True,
        "reason": "",
        "horizon": horizon,
        "folds_used": folds_used,
        "n": n,
        "methods": out,
        "baseline": BASELINE,
        "best": best,
        "best_reason": best_reason,
        "notes": notes,
    }


def to_frame(result: Dict) -> pd.DataFrame:
    """백테스트 결과를 표로. 화면·엑셀 출력용."""
    if not result.get("ok"):
        return pd.DataFrame()
    rows = []
    for name, m in result["methods"].items():
        rows.append({
            "방법": m["label"],
            "MAPE(%)": round(m["mape"], 3) if m["mape"] is not None else None,
            "MAE": round(m["mae"], 3) if m["mae"] is not None else None,
            "RMSE": round(m["rmse"], 3) if m["rmse"] is not None else None,
            "95%밴드 적중률(%)": round(m["coverage"], 1) if m["coverage"] is not None else None,
            "naive 대비 개선(%)": round(m["skill"] * 100, 1) if m.get("skill") is not None else None,
            "naive 상대 승률": (
                f"{m['wins']}/{m['folds_compared']}" if m.get("win_rate") is not None else "—"
            ),
            "비고": m.get("error", ""),
        })
    df = pd.DataFrame(rows)
    if "MAPE(%)" in df.columns:
        df = df.sort_values("MAPE(%)", na_position="last").reset_index(drop=True)
    return df


def horizon_frame(result: Dict, method: Optional[str] = None) -> pd.DataFrame:
    """예측 기간(h)별 오차 — 몇 개월 뒤까지 쓸 만한지 판단용"""
    if not result.get("ok"):
        return pd.DataFrame()
    name = method or result.get("best")
    m = result["methods"].get(name)
    if not m or not m.get("by_h"):
        return pd.DataFrame()
    return pd.DataFrame([
        {"예측 개월": r["h"],
         "MAPE(%)": round(r["mape"], 3) if r["mape"] is not None else None,
         "MAE": round(r["mae"], 3) if r["mae"] is not None else None}
        for r in m["by_h"]
    ])
