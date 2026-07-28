"""
물가지수 예측 모듈 (과거 추세 기반)
- Holt-Winters 지수평활(추세+계절성)로 향후 N개월 예측
- 데이터가 짧거나 모델 적합 실패 시 → 선형 추세 외삽으로 자동 폴백
- 신뢰구간(밴드)을 함께 반환하여 불확실성을 시각적으로 강제

⚠️ 예측값은 '과거 추세의 연장'일 뿐, 실제 물가는 외부 충격(원자재 급등 등)으로
   크게 달라질 수 있습니다. 출력 시 반드시 경고를 함께 표기하세요.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

MAX_HORIZON = 12  # 예측 상한 (개월) — 보수적 제한


def _to_monthly_series(df: pd.DataFrame) -> pd.Series:
    """df[TIME(YYYYMM), DATA_VALUE] → 월별 Series(index=datetime)"""
    s = df.copy()
    s["TIME_DT"] = pd.to_datetime(s["TIME"].astype(str), format="%Y%m")
    s = s.sort_values("TIME_DT").set_index("TIME_DT")["DATA_VALUE"].astype(float)
    s = s.asfreq("MS")  # 월초 빈도 (결측은 보간)
    s = s.interpolate(method="linear").ffill().bfill()
    return s


def forecast_index(
    df: pd.DataFrame,
    horizon: int = 12,
    seasonal: bool = True,
) -> dict:
    """
    Parameters
    ----------
    df : DataFrame[TIME, DATA_VALUE]  (과거 실측 시계열)
    horizon : 예측 개월 수 (1~12로 강제 제한)
    seasonal : 계절성 반영 여부

    Returns
    -------
    dict {
      "method": 사용된 방법 설명(str),
      "history": Series(과거),
      "forecast": Series(예측 평균),
      "lower": Series(하한), "upper": Series(상한),
      "warning": 경고 문구(str),
    }
    """
    horizon = max(1, min(int(horizon), MAX_HORIZON))
    hist = _to_monthly_series(df)
    n = len(hist)

    future_idx = pd.date_range(
        hist.index[-1] + pd.offsets.MonthBegin(1), periods=horizon, freq="MS"
    )

    method = ""
    fc = lower = upper = None

    # 1순위: Holt-Winters (데이터 24개월 이상일 때만 계절성 시도)
    use_seasonal = seasonal and n >= 24
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        model = ExponentialSmoothing(
            hist,
            trend="add",
            seasonal="add" if use_seasonal else None,
            seasonal_periods=12 if use_seasonal else None,
            initialization_method="estimated",
        ).fit()
        fc = model.forecast(horizon)

        # 신뢰구간: 잔차 표준편차 기반 ±1.96σ, 기간에 따라 점진 확대
        resid = hist - model.fittedvalues
        sigma = float(np.nanstd(resid))
        widen = np.sqrt(np.arange(1, horizon + 1))  # 미래로 갈수록 넓게
        margin = 1.96 * sigma * widen
        lower = fc - margin
        upper = fc + margin
        method = (
            f"Holt-Winters 지수평활 (추세{'+계절성' if use_seasonal else ''}, "
            f"과거 {n}개월 학습)"
        )
    except Exception as e:
        fc = None
        print(f"[forecast] Holt-Winters 실패 → 선형 추세 폴백: {e}")

    # 폴백: 선형 추세 외삽
    if fc is None:
        x = np.arange(n)
        y = hist.values
        # 최근 추세를 더 반영하기 위해 가중(최근 36개월 우선)
        w = np.ones(n)
        if n > 36:
            w[-36:] = 2.0
        coef = np.polyfit(x, y, 1, w=w)
        future_x = np.arange(n, n + horizon)
        fc_vals = np.polyval(coef, future_x)
        fc = pd.Series(fc_vals, index=future_idx)

        resid = y - np.polyval(coef, x)
        sigma = float(np.nanstd(resid))
        widen = np.sqrt(np.arange(1, horizon + 1))
        margin = 1.96 * sigma * widen
        lower = fc - margin
        upper = fc + margin
        method = f"선형 추세 외삽 (과거 {n}개월, 계절성 미반영)"

    fc.index = future_idx
    lower.index = future_idx
    upper.index = future_idx

    warning = (
        "예측값은 과거 추세의 연장이며, 원자재 급등·정책 변화 등 외부 충격은 "
        "반영하지 못합니다. 투자 의사결정 시 참고 지표로만 활용하고 확정값으로 "
        "사용하지 마십시오."
    )

    return {
        "method": method,
        "history": hist,
        "forecast": fc,
        "lower": lower,
        "upper": upper,
        "warning": warning,
    }
