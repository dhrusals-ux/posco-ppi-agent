"""
한국은행 ECOS Open API 클라이언트
생산자물가지수(PPI) 데이터 조회 모듈
"""
import os
import requests
import pandas as pd
from typing import Optional, List


class ECOSClient:
    """한국은행 ECOS API 클라이언트"""

    BASE_URL = "https://ecos.bok.or.kr/api"
    PPI_STAT_CODE = "404Y014"  # 생산자물가지수 (품목별, 2020=100)

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ECOS_API_KEY")
        if not self.api_key:
            raise ValueError(
                "ECOS_API_KEY가 설정되지 않았습니다. "
                "사이드바에서 인증키를 입력하거나 .env 파일을 확인하세요."
            )

    def get_ppi(
        self,
        item_code: str,
        start: str,
        end: str,
        cycle: str = "M",
    ) -> pd.DataFrame:
        """
        PPI 시계열 조회

        Parameters
        ----------
        item_code : str
            ECOS 품목 코드 (예: '4101'=철강1차제품)
        start : str
            시작 시점 ('YYYYMM' 또는 'YYYY')
        end : str
            종료 시점
        cycle : str
            'M'(월), 'Q'(분기), 'A'(연)
        """
        url = (
            f"{self.BASE_URL}/StatisticSearch/{self.api_key}/json/kr/1/1000/"
            f"{self.PPI_STAT_CODE}/{cycle}/{start}/{end}/{item_code}"
        )
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()

        if "RESULT" in data:
            raise RuntimeError(f"ECOS API 오류: {data['RESULT']}")

        rows = data.get("StatisticSearch", {}).get("row", [])
        if not rows:
            raise ValueError(
                f"품목코드 '{item_code}' 데이터가 없습니다.\n"
                f"→ ECOS 사이트에서 정확한 코드를 확인하세요."
            )

        df = pd.DataFrame(rows)
        df["DATA_VALUE"] = pd.to_numeric(df["DATA_VALUE"], errors="coerce")
        df = df.dropna(subset=["DATA_VALUE"]).reset_index(drop=True)
        return df[["TIME", "ITEM_NAME1", "DATA_VALUE"]]

    def get_ppi_at(self, item_code: str, period: str, cycle: str = "M") -> float:
        """특정 시점의 PPI 단일 값"""
        df = self.get_ppi(item_code, period, period, cycle)
        return float(df["DATA_VALUE"].iloc[0])

    def get_multi_items(
        self,
        item_codes: List[str],
        start: str,
        end: str,
        cycle: str = "M",
    ) -> pd.DataFrame:
        """여러 품목을 한 번에 조회"""
        all_data = []
        for code in item_codes:
            try:
                df = self.get_ppi(code, start, end, cycle)
                df["ITEM_CODE"] = code
                all_data.append(df)
            except Exception as e:
                print(f"⚠️ {code} 조회 실패: {e}")
        if not all_data:
            return pd.DataFrame()
        return pd.concat(all_data, ignore_index=True)
