"""
KOSIS(국가통계포털) Open API 클라이언트 — 건설공사비지수
- 통계표: DT_39701_A003 (건설공사비지수, 2020=100), 기관코드 397 (한국건설기술연구원)
- ECOSClient 와 동일한 인터페이스(get_ppi / get_ppi_at)를 제공하여
  기존 환산 로직(원금 × 목표지수/기준지수)을 그대로 재사용한다.

★ 설계 원칙: 항목ID(itmId)·공종코드(objL1)를 하드코딩하지 않는다.
  KOSIS는 itmId/objL1 에 "ALL" 을 넣으면 통계표의 모든 항목·분류를 돌려준다.
  → 실제 코드값을 런타임에 응답에서 자동 발견(discover)하므로,
    통계표 개편이나 코드 추정 오류에 영향을 받지 않는다.

응답 표준 필드: PRD_DE(시점), DT(값), C1(분류코드), C1_NM(분류명),
              ITM_ID(항목코드), ITM_NM(항목명), UNIT_NM(단위)
"""
import os
import requests
import pandas as pd
from typing import Optional, List, Dict


class KOSISClient:
    """KOSIS 통계자료 Open API 클라이언트 (건설공사비지수 기본값)"""

    BASE_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"

    ORG_ID = "397"            # 한국건설기술연구원
    TBL_ID = "DT_39701_A003"  # 건설공사비지수(2020년기준)
    DEFAULT_ITM_ID = "16397AAA0"  # 지수 항목 (실측 확인값)

    def __init__(self, api_key: Optional[str] = None,
                 org_id: Optional[str] = None, tbl_id: Optional[str] = None):
        raw = api_key or os.getenv("KOSIS_API_KEY")
        if not raw:
            raise ValueError(
                "KOSIS_API_KEY가 설정되지 않았습니다. "
                "사이드바에서 인증키를 입력하거나 secrets에 등록하세요.\n"
                "→ kosis.kr 회원가입 후 '공유서비스(OpenAPI)'에서 무료 발급"
            )
        self.api_key = raw.strip().strip('"').strip("'").strip()
        self.org_id = org_id or self.ORG_ID
        self.tbl_id = tbl_id or self.TBL_ID

    # ───────────────────────────────────────
    # 내부 공통 호출
    # ───────────────────────────────────────
    def _request(self, params: dict) -> list:
        base = {
            "method": "getList",
            "apiKey": self.api_key,
            "orgId": self.org_id,
            "tblId": self.tbl_id,
            "format": "json",
            "jsonVD": "Y",
        }
        base.update(params)
        r = requests.get(self.BASE_URL, params=base, timeout=20)
        r.raise_for_status()
        data = r.json()

        # 오류는 dict({"err","errMsg"}), 정상은 list
        if isinstance(data, dict):
            code = str(data.get("err", ""))
            msg = data.get("errMsg", "") or data.get("message", "")
            hints = {
                "11": "→ 유효하지 않은 인증키입니다. 키를 확인하거나 "
                      "발급 직후라면 활성화 대기가 필요할 수 있습니다.",
                "20": "→ 인증키가 유효하지 않거나 분류 레벨이 부족합니다. "
                      "키 확인 또는 objL2='ALL' 추가가 필요할 수 있습니다.",
                "30": "→ 등록되지 않은 서비스이거나 호출 한도 초과입니다.",
                "31": "→ 일일 트래픽(호출량) 초과입니다.",
                "300": "→ 해당 기간/분류에 데이터가 없습니다.",
            }
            raise RuntimeError(f"KOSIS API 오류 [{code}] {msg}\n{hints.get(code,'')}")
        return data or []

    # ───────────────────────────────────────
    # 공종(분류) 목록 자동 발견
    # ───────────────────────────────────────
    def discover_categories(self, sample_period: Optional[str] = None) -> pd.DataFrame:
        """
        objL1=ALL, itmId=ALL 로 호출해 통계표의 실제 공종 분류·항목을 추출.
        반환 컬럼: C1(공종코드), C1_NM(공종명), ITM_ID(항목코드), ITM_NM(항목명)
        """
        # 최신 한 달치만 받아 구조 파악 (데이터 양 최소화)
        from datetime import datetime
        end = sample_period or datetime.now().strftime("%Y%m")
        # 최근 6개월 범위로 넉넉히 (발표 지연 대비)
        start = (datetime.now().replace(day=1))
        start = f"{start.year - 1}{start.month:02d}"

        rows = self._request({
            "itmId": "ALL", "objL1": "ALL",
            "prdSe": "M", "startPrdDe": start, "endPrdDe": end,
        })
        if not rows:
            return pd.DataFrame(columns=["C1", "C1_NM", "ITM_ID", "ITM_NM"])

        df = pd.DataFrame(rows)
        cols = [c for c in ["C1", "C1_NM", "ITM_ID", "ITM_NM"] if c in df.columns]
        cat = df[cols].drop_duplicates().reset_index(drop=True)
        return cat

    # ───────────────────────────────────────
    # ECOS 호환 인터페이스
    # ───────────────────────────────────────
    def get_ppi(self, item_code: str, start: str, end: str,
                cycle: str = "M", itm_id: Optional[str] = None) -> pd.DataFrame:
        """
        건설공사비지수 시계열 조회 (ECOSClient.get_ppi 호환)

        item_code : 공종 분류 코드(objL1). 'ALL' 도 가능.
        itm_id    : 항목 코드. 기본은 통계표 실측 항목(16397AAA0).
        반환: DataFrame[TIME, ITEM_NAME1, DATA_VALUE]
        """
        prd_se = {"M": "M", "Q": "Q", "A": "Y", "Y": "Y"}.get(cycle, "M")
        rows = self._request({
            "itmId": itm_id or self.DEFAULT_ITM_ID, "objL1": item_code,
            "prdSe": prd_se, "startPrdDe": start, "endPrdDe": end,
        })
        if not rows:
            raise ValueError(
                f"공종코드 '{item_code}' · 기간 {start}~{end} 데이터가 없습니다.\n"
                f"→ 건설공사비지수는 발표가 1~2개월 지연됩니다. "
                f"목표 시점을 최근 발표월(예: 2~3개월 전)로 조정해 보세요."
            )

        df = pd.DataFrame(rows)
        name_col = "C1_NM" if "C1_NM" in df.columns else ("ITM_NM" if "ITM_NM" in df.columns else None)
        out = pd.DataFrame({
            "TIME": df.get("PRD_DE", pd.Series(dtype=str)).astype(str),
            "ITEM_NAME1": df[name_col] if name_col else "건설공사비지수",
            "DATA_VALUE": pd.to_numeric(df.get("DT"), errors="coerce"),
        })
        out = out.dropna(subset=["DATA_VALUE"]).reset_index(drop=True)
        out = out.sort_values("TIME").reset_index(drop=True)
        return out

    def get_ppi_at(self, item_code: str, period: str,
                   cycle: str = "M", itm_id: Optional[str] = None) -> float:
        df = self.get_ppi(item_code, period, period, cycle, itm_id)
        if len(df) == 0:
            raise ValueError(f"{period} 시점 데이터가 없습니다 (코드 {item_code}).")
        return float(df["DATA_VALUE"].iloc[0])

    def get_multi_items(self, item_codes: List[str], start: str, end: str,
                        cycle: str = "M") -> pd.DataFrame:
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
