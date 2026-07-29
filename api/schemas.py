"""API 요청·응답 스키마.

프론트엔드(Next.js 등)와의 계약이다. 여기 정의된 필드명이 곧 API 표면이므로
필드를 바꾸면 프론트가 깨진다 — 추가는 자유롭게, 삭제·개명은 신중히.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

PERIOD_PATTERN = r"^\d{6}$"

# 원칙 6 — 모든 환산 응답에 면책 문구를 함께 실어 보낸다.
# 프론트가 표시를 잊더라도 응답 본문에는 남아 있어야 한다.
DISCLAIMER = (
    "본 결과는 내부 투자비 추정·검토용이며, 「국가계약법」상 계약금액조정(물가변동) "
    "산식과 다르므로 공식 계약 근거로 사용할 수 없습니다."
)


def _check_period(v: str) -> str:
    if not v or len(v) != 6 or not v.isdigit():
        raise ValueError("시점은 YYYYMM 6자리 숫자여야 합니다 (예: 201901)")
    month = int(v[4:])
    if not 1 <= month <= 12:
        raise ValueError(f"월이 올바르지 않습니다: {v[4:]}")
    return v


# ─────────────────────────────────────────────
# 카탈로그
# ─────────────────────────────────────────────
class CatalogItem(BaseModel):
    code: str
    name: str
    level: Optional[int] = None


class CatalogResponse(BaseModel):
    source: str = Field(description="ECOS 통계표 코드 또는 KOSIS 통계표 ID")
    count: int
    items: List[CatalogItem]


# ─────────────────────────────────────────────
# 시계열
# ─────────────────────────────────────────────
class SeriesPoint(BaseModel):
    period: str
    value: float


class SeriesResponse(BaseModel):
    code: str
    name: Optional[str] = None
    start: str
    end: str
    points: List[SeriesPoint]


# ─────────────────────────────────────────────
# 단일 환산
# ─────────────────────────────────────────────
class AdjustRequest(BaseModel):
    code: str = Field(description="ECOS 품목코드 또는 KOSIS 공종코드")
    amount: float = Field(gt=0, description="원금 (원 단위)")
    base: str = Field(description="기준시점 YYYYMM")
    target: str = Field(description="목표시점 YYYYMM")

    @field_validator("base", "target")
    @classmethod
    def _v(cls, v: str) -> str:
        return _check_period(v)


class AdjustResponse(BaseModel):
    code: str
    name: Optional[str] = None
    amount: float
    base: str
    target: str
    base_index: float
    target_index: float
    factor: float
    adjusted: float
    delta: float
    delta_pct: float
    formula: str = "환산액 = 원금 × (목표시점 지수 ÷ 기준시점 지수)"
    disclaimer: str = DISCLAIMER


# ─────────────────────────────────────────────
# 엑셀 일괄 보정
# ─────────────────────────────────────────────
class ParsedTable(BaseModel):
    columns: List[str]
    guessed_item_column: Optional[str]
    guessed_amount_column: Optional[str]
    row_count: int
    rows: List[dict] = Field(description="원본 행 (미리보기·컬럼 선택용)")


class SuggestItem(BaseModel):
    row: int = Field(description="엑셀 행 번호 (헤더 1행 기준)")
    name: str
    amount: Optional[float] = None


class SuggestRequest(BaseModel):
    items: List[SuggestItem]
    top_n: int = Field(default=5, ge=1, le=20)


class Candidate(BaseModel):
    code: str
    name: str
    score: float
    matched_keyword: Optional[str] = None


class Suggestion(BaseModel):
    row: int
    name: str
    amount: Optional[float]
    code: str
    ecos_name: str
    confidence: str = Field(description="높음 / 중간 / 낮음 / 실패")
    reason: str = Field(description="신뢰도 판단 근거 — 검토자가 스스로 판단할 수 있도록")
    amount_error: str = ""
    candidates: List[Candidate] = []


class SuggestResponse(BaseModel):
    count: int
    high: int
    medium: int
    low: int
    failed: int
    suggestions: List[Suggestion]
    notice: str = (
        "자동 매칭은 제안이며 확정이 아닙니다. 신뢰도가 '높음'이 아닌 항목은 "
        "검토 후 confirmed=true로 표시해야 일괄 보정이 실행됩니다."
    )


class BatchRow(BaseModel):
    row: int
    name: str = ""
    code: str = ""
    amount: Optional[float] = None
    confidence: str = "실패"
    confirmed: bool = False


class BatchAdjustRequest(BaseModel):
    base: str
    target: str
    rows: List[BatchRow]

    @field_validator("base", "target")
    @classmethod
    def _v(cls, v: str) -> str:
        return _check_period(v)


class BatchResultRow(BaseModel):
    row: Optional[int] = None
    name: str = ""
    ecos_name: str = ""
    code: str = ""
    confidence: str = ""
    confirmed: bool = False
    amount: Optional[float] = None
    base_index: Optional[float] = None
    target_index: Optional[float] = None
    factor: Optional[float] = None
    adjusted: Optional[float] = None
    delta: Optional[float] = None
    delta_pct: Optional[float] = None
    error: str = ""


class BatchSummary(BaseModel):
    count: int
    succeeded: int
    failed: int
    principal_total: float
    adjusted_total: float
    delta: float
    delta_pct: Optional[float] = None
    low_confidence_count: int


class BatchAdjustResponse(BaseModel):
    base: str
    target: str
    summary: BatchSummary
    rows: List[BatchResultRow]
    formula: str = "환산액 = 원금 × (목표시점 지수 ÷ 기준시점 지수)"
    disclaimer: str = DISCLAIMER
    warning: Optional[str] = None


class BlockedResponse(BaseModel):
    """승인 게이트 위반 — HTTP 409"""
    detail: str = "승인되지 않은 항목이 있어 일괄 보정을 실행할 수 없습니다."
    blockers: List[str]


# ─────────────────────────────────────────────
# 예측
# ─────────────────────────────────────────────
class ForecastPoint(BaseModel):
    period: str
    value: float
    lower: float
    upper: float


class ForecastResponse(BaseModel):
    code: str
    method: str = Field(description="사용된 방법론 — 예측값 해석에 필요하므로 반드시 표시")
    horizon: int
    history: List[SeriesPoint]
    forecast: List[ForecastPoint]
    confidence_level: float = 0.95
    warning: str
    disclaimer: str = DISCLAIMER
