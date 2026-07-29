"""클라이언트 생성 · 키 검증 · 오류 변환.

원칙 2 — LIVE 전용. 키가 없으면 명확히 실패한다.
"데모로 조용히 폴백"은 틀린 숫자를 진짜처럼 보이게 하므로 절대 되살리지 않는다.
"""
from __future__ import annotations

import os

from fastapi import HTTPException

from utils.ecos_client import ECOSClient
from utils.kosis_client import KOSISClient


def _clean(v: str | None) -> str:
    """복붙 시 따라오는 따옴표·공백 제거 (ECOS INFO-100의 최다 원인)"""
    return (v or "").strip().strip('"').strip("'").strip()


def get_ecos_client() -> ECOSClient:
    key = _clean(os.getenv("ECOS_API_KEY"))
    if not key:
        raise HTTPException(
            status_code=503,
            detail=(
                "ECOS_API_KEY가 설정되지 않았습니다. 서버 환경변수에 등록하세요. "
                "무료 발급: https://ecos.bok.or.kr/api/"
            ),
        )
    return ECOSClient(api_key=key)


def get_kosis_client() -> KOSISClient:
    key = _clean(os.getenv("KOSIS_API_KEY"))
    if not key:
        raise HTTPException(
            status_code=503,
            detail=(
                "KOSIS_API_KEY가 설정되지 않았습니다. 서버 환경변수에 등록하세요. "
                "무료 발급: https://kosis.kr 공유서비스(OpenAPI)"
            ),
        )
    return KOSISClient(api_key=key)


def upstream_error(exc: Exception, context: str = "") -> HTTPException:
    """
    ECOS/KOSIS 오류를 HTTP 상태로 변환한다.
    클라이언트 모듈이 이미 한국어 힌트를 붙여주므로 메시지를 그대로 전달한다.
    """
    msg = str(exc)
    prefix = f"{context}: " if context else ""

    # 인증 실패 — 서버 설정 문제이므로 502가 아니라 503으로 구분
    if "INFO-100" in msg or "무효" in msg or "인증" in msg:
        return HTTPException(status_code=503, detail=f"{prefix}{msg}")

    # 호출 한도 초과 — 재시도 가능함을 알린다
    if "INFO-300" in msg or "한도" in msg or "트래픽" in msg:
        return HTTPException(status_code=429, detail=f"{prefix}{msg}")

    # 데이터 없음 — 요청한 코드/기간이 잘못된 경우
    if "INFO-200" in msg or "데이터가 없" in msg or "데이터없음" in msg:
        return HTTPException(status_code=404, detail=f"{prefix}{msg}")

    return HTTPException(status_code=502, detail=f"{prefix}{msg}")
