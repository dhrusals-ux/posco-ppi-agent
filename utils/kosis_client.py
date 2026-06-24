"""
KOSIS(국가통계포털) Open API 클라이언트
건설공사비지수(한국건설기술연구원 작성) 데이터 조회 모듈

- 통계표: DT_39701_A003 (건설공사비지수, 2020=100), 기관코드 397
- ECOSClient 와 동일한 인터페이스(get_ppi / get_ppi_at)를 제공하여
  기존 환산 로직(원금 × 목표지수/기준지수)을 그대로 재사용할 수 있게 한다.

⚠️ KOSIS API는 통계표마다 itmId(항목ID)·objL1(분류ID) 체계가 다르다.
   건설공사비지수는 단일 항목(T10: 지수)에 공종 분류(objL1)로 갈래가 나뉜다.
   런타임에 분류 목록을 한 번 받아 캐싱하는 방식을 권장한다.
"""
import os
import requests
import pandas as pd
from typing import Optional, List


class KOSISClient:
    """KOSIS 통계자료 Open API 클라이언트 (건설공사비지수 전용 기본값)"""

    BASE_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
    LIST_URL = "https://kosis.kr/openapi/statisticsData.do"

    # 건설공사비지수 (2020=100)
    ORG_ID = "397"            # 한국건설기술연구원
    TBL_ID = "DT_39701_A003"  # 건설공사비지수(2020년기준)
    ITM_ID = "T10"            # 지수 항목 (통계표에 따라 확인 필요)

    def __init__(self, api_key: Optional[str] = None):
        raw = api_key or os.getenv("KOSIS_API_KEY")
        if not raw:
            raise ValueError(
                "KOSIS_API_KEY가 설정되지 않았습니다. "
                "사이드바에서 인증키를 입력하거나 .env 파일을 확인하세요.\n"
                "→ kosis.kr 회원가입 후 '공유서비스(OpenAPI)'에서 무료 발급"
            )
        # ECOS와 동일하게 따옴표/공백/줄바꿈 방어
        self.api_key = raw.strip().strip('"').strip("'").strip()

    def _raise_with_hint(self, payload):
        """KOSIS 에러 응답에 친절한 한국어 설명을 붙여서 예외 발생"""
        # KOSIS 오류는 보통 {"err":"30","errMsg":"..."} 형태
        if isinstance(payload, dict):
            code = str(payload.get("err", ""))
            msg = payload.get("errMsg", "") or payload.get("message", "")
            hints = {
                "20": "→ 인증키가 유효하지 않습니다. 앞뒤 따옴표·공백을 제거했는지, "
                      "발급 직후라면 활성화까지 대기가 필요한지 확인하세요.",
                "30": "→ 등록되지 않은 서비스이거나 일일 호출 한도를 초과했습니다.",
                "31": "→ 일일 트래픽(호출량) 초과입니다. 내일 다시 시도하세요.",
                "300": "→ 해당 기간/분류에 데이터가 없습니다. 공종 코드(objL1)와 "
                       "기간이 최신 발표월 이내인지 확인하세요.",
            }
            hint = hints.get(code, "")
            raise RuntimeError(f"KOSIS API 오류 [{code}] {msg}\n{hint}")
        raise RuntimeError(f"KOSIS API 알 수 없는 응답: {payload}")

    def get_ppi(
        self,
        item_code: str,
        start: str,
        end: str,
        cycle: str = "M",
    ) -> pd.DataFrame:
        """
        건설공사비지수 시계열 조회 (ECOSClient.get_ppi 와 동일 시그니처)

        Parameters
        ----------
        item_code : str
            공종 분류 코드 (objL1). 예: 건설공사비지수 종합 / 토목 / 건축 등.
            ECOS의 ITEM_CODE 자리에 대응.
        start, end : str
            'YYYYMM' (월 주기 기준)
        cycle : str
            'M'(월), 'Y'(연). KOSIS prdSe 파라미터로 매핑.

        Returns
        -------
        pd.DataFrame  (컬럼: TIME, ITEM_NAME1, DATA_VALUE) — ECOS 응답과 호환
        """
        prd_se = {"M": "M", "Q": "Q", "A": "Y", "Y": "Y"}.get(cycle, "M")

        params = {
            "method": "getList",
            "apiKey": self.api_key,
            "orgId": self.ORG_ID,
            "tblId": self.TBL_ID,
            "itmId": self.ITM_ID,
            "objL1": item_code,
            "format": "json",
            "jsonVD": "Y",
            "prdSe": prd_se,
            "startPrdDe": start,
            "endPrdDe": end,
        }
        r = requests.get(self.BASE_URL, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()

        # 오류는 dict, 정상은 list 로 온다
        if isinstance(data, dict):
            self._raise_with_hint(data)

        if not data:
            raise ValueError(
                f"공종코드 '{item_code}' 데이터가 없습니다.\n"
                f"→ 분류(objL1) 코드와 기간을 확인하세요."
            )

        df = pd.DataFrame(data)
        # KOSIS 표준 필드: PRD_DE(시점), DT(값), C1_NM(분류명), ITM_NM(항목명)
        out = pd.DataFrame({
            "TIME": df.get("PRD_DE", pd.Series(dtype=str)).astype(str),
            "ITEM_NAME1": df.get("C1_NM", df.get("ITM_NM", "건설공사비지수")),
            "DATA_VALUE": pd.to_numeric(df.get("DT"), errors="coerce"),
        })
        out = out.dropna(subset=["DATA_VALUE"]).reset_index(drop=True)
        out = out.sort_values("TIME").reset_index(drop=True)
        return out

    def get_ppi_at(self, item_code: str, period: str, cycle: str = "M") -> float:
        """특정 시점의 지수 단일 값"""
        df = self.get_ppi(item_code, period, period, cycle)
        if len(df) == 0:
            raise ValueError(f"{period} 시점 데이터가 없습니다 (코드 {item_code}).")
        return float(df["DATA_VALUE"].iloc[0])

    def get_multi_items(
        self,
        item_codes: List[str],
        start: str,
        end: str,
        cycle: str = "M",
    ) -> pd.DataFrame:
        """여러 공종을 한 번에 조회"""
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
