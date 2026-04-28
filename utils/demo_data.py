"""
데모 데이터 생성기
- ECOS API 키 없이도 Streamlit 앱을 시연할 수 있도록
  실제 PPI 추이를 모방한 가상 시계열을 생성합니다.
- 품목별로 고유한 변동 패턴(트렌드 + 계절성 + 변동성)을 부여해
  실제 데이터처럼 보이게 만듭니다.
"""
import numpy as np
import pandas as pd
from datetime import datetime


# 품목별 특성 (연간 상승률, 변동성, 계절성 강도)
# 철강/원자재는 상승폭과 변동성이 크고, 계측기기는 안정적
ITEM_PROFILES = {
    # 철강/토건 - 고변동
    "4101": {"annual_growth": 0.055, "volatility": 0.035, "seasonal": 0.015},  # 철강1차
    "4102": {"annual_growth": 0.050, "volatility": 0.032, "seasonal": 0.012},  # 구조용강재
    "4103": {"annual_growth": 0.042, "volatility": 0.020, "seasonal": 0.018},  # 시멘트
    "4104": {"annual_growth": 0.038, "volatility": 0.018, "seasonal": 0.010},  # 내화재
    # 기계 - 중변동
    "4111": {"annual_growth": 0.028, "volatility": 0.015, "seasonal": 0.008},  # 원동기/펌프
    "4112": {"annual_growth": 0.032, "volatility": 0.018, "seasonal": 0.010},  # 운반하역
    "4113": {"annual_growth": 0.030, "volatility": 0.016, "seasonal": 0.012},  # 냉동공조
    "4121": {"annual_growth": 0.035, "volatility": 0.020, "seasonal": 0.008},  # 금속가공기계
    "4122": {"annual_growth": 0.025, "volatility": 0.014, "seasonal": 0.006},  # 산업용로봇
    "4123": {"annual_growth": 0.033, "volatility": 0.019, "seasonal": 0.010},  # 광업/건설기계
    # 전기 - 중저변동
    "4131": {"annual_growth": 0.029, "volatility": 0.015, "seasonal": 0.007},  # 변압기
    "4132": {"annual_growth": 0.026, "volatility": 0.013, "seasonal": 0.006},  # 전동기
    "4133": {"annual_growth": 0.027, "volatility": 0.014, "seasonal": 0.007},  # 배전반
    "4134": {"annual_growth": 0.040, "volatility": 0.025, "seasonal": 0.010},  # 전선/케이블 (구리 민감)
    "4135": {"annual_growth": 0.020, "volatility": 0.010, "seasonal": 0.005},  # 산업용 조명
    # 계측 - 저변동
    "4141": {"annual_growth": 0.018, "volatility": 0.010, "seasonal": 0.004},  # 산업용 계측기
    "4142": {"annual_growth": 0.020, "volatility": 0.011, "seasonal": 0.005},  # 분석기기
    "4143": {"annual_growth": 0.022, "volatility": 0.012, "seasonal": 0.005},  # PLC/DCS
    # 종합지수
    "*AA": {"annual_growth": 0.028, "volatility": 0.012, "seasonal": 0.008},  # 총지수
    "2":   {"annual_growth": 0.030, "volatility": 0.015, "seasonal": 0.009},  # 공산품
    "41":  {"annual_growth": 0.048, "volatility": 0.028, "seasonal": 0.014},  # 1차금속 종합
    "42":  {"annual_growth": 0.030, "volatility": 0.016, "seasonal": 0.008},  # 기계 종합
    "43":  {"annual_growth": 0.030, "volatility": 0.017, "seasonal": 0.008},  # 전기 종합
}

# 기본 프로파일 (매칭 안 될 때)
DEFAULT_PROFILE = {"annual_growth": 0.028, "volatility": 0.015, "seasonal": 0.008}


def _period_to_month_index(period: str, base_month: pd.Timestamp) -> int:
    """YYYYMM을 base_month 기준 월 인덱스로 변환"""
    dt = pd.to_datetime(period, format="%Y%m")
    return (dt.year - base_month.year) * 12 + (dt.month - base_month.month)


def generate_ppi_series(
    item_code: str,
    start: str,
    end: str,
    base_index_2020: float = 100.0,
) -> pd.DataFrame:
    """
    품목별 가상 PPI 시계열 생성

    - 2020년 1월을 100으로 설정(ECOS 관례와 동일)
    - 연간 상승 트렌드 + 계절성 + 랜덤 변동 + COVID/원자재 쇼크 반영
    """
    profile = ITEM_PROFILES.get(item_code, DEFAULT_PROFILE)

    # 재현성 있는 난수 (품목별 고정 seed)
    seed = sum(ord(c) for c in item_code) % 10000
    rng = np.random.default_rng(seed)

    # 날짜 범위 생성 (월 단위)
    start_dt = pd.to_datetime(start, format="%Y%m")
    end_dt = pd.to_datetime(end, format="%Y%m")
    dates = pd.date_range(start=start_dt, end=end_dt, freq="MS")

    if len(dates) == 0:
        raise ValueError(f"유효한 기간이 아닙니다: {start} ~ {end}")

    # 2020년 1월을 기준점으로
    base_2020 = pd.Timestamp("2020-01-01")
    months_from_base = np.array([
        (d.year - base_2020.year) * 12 + (d.month - base_2020.month)
        for d in dates
    ])

    # 1. 기본 트렌드 (연간 상승률을 월 복리로 변환)
    monthly_growth = (1 + profile["annual_growth"]) ** (1 / 12) - 1
    trend = base_index_2020 * (1 + monthly_growth) ** months_from_base

    # 2. 계절성 (sin 패턴)
    seasonal = 1 + profile["seasonal"] * np.sin(2 * np.pi * np.array([d.month for d in dates]) / 12)

    # 3. 랜덤 변동 (누적 평활화)
    noise = rng.normal(0, profile["volatility"], len(dates))
    noise_smooth = pd.Series(noise).rolling(window=3, min_periods=1).mean().values
    random_factor = 1 + noise_smooth

    # 4. 실제 이벤트 반영: 2020 COVID 하락 → 2021~2022 원자재 급등
    event_factor = np.ones(len(dates))
    for i, d in enumerate(dates):
        y, m = d.year, d.month
        if y == 2020 and m >= 3 and m <= 8:
            event_factor[i] *= 0.97  # COVID 하락
        elif (y == 2021) or (y == 2022 and m <= 6):
            event_factor[i] *= 1.0 + 0.015 * profile["volatility"] * 10  # 원자재 급등
        elif y == 2022 and m >= 7:
            event_factor[i] *= 1.02  # 고점
        elif y == 2023:
            event_factor[i] *= 0.99  # 조정

    values = trend * seasonal * random_factor * event_factor

    # DataFrame 구성 (ECOS 응답 형식과 호환)
    df = pd.DataFrame({
        "TIME": [d.strftime("%Y%m") for d in dates],
        "ITEM_NAME1": [f"[DEMO] {item_code}"] * len(dates),
        "DATA_VALUE": np.round(values, 2),
    })
    return df


def generate_ppi_at(item_code: str, period: str) -> float:
    """특정 시점 단일 값"""
    df = generate_ppi_series(item_code, period, period)
    return float(df["DATA_VALUE"].iloc[0])


class DemoECOSClient:
    """ECOSClient와 동일한 인터페이스의 데모 클라이언트"""

    def __init__(self, *args, **kwargs):
        pass

    def get_ppi(self, item_code, start, end, cycle="M"):
        return generate_ppi_series(item_code, start, end)

    def get_ppi_at(self, item_code, period, cycle="M"):
        return generate_ppi_at(item_code, period)

    def get_multi_items(self, item_codes, start, end, cycle="M"):
        frames = []
        for code in item_codes:
            df = self.get_ppi(code, start, end)
            df["ITEM_CODE"] = code
            frames.append(df)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
