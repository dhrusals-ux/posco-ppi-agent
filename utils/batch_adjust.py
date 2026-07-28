"""
엑셀 견적서 일괄 물가보정 로직 (UI 비의존)

설계 의도 — 완전 자동화를 의도적으로 막는다:
  실제 견적 품목명("냉각수 순환펌프 1식", "BFP 3대", "P-101 급수펌프")은 구체적이라
  ECOS 품목 자동매칭이 틀릴 수 있다. 틀린 매칭은 예외를 내지 않고 '조용히 틀린 금액'을
  만들어 투자 품의서에 들어갈 위험이 있다. 그래서 이 모듈은
    - 매칭마다 신뢰도(높음/중간/낮음/실패)와 그 판단 근거를 함께 반환하고
    - 사람이 코드를 갈아끼울 수 있도록 후보 목록을 노출하며
    - 확인되지 않은 저신뢰 행이 남아 있으면 실행을 막는 게이트를 제공한다.
  즉 '자동 제안 + 사람 확인 후 승인' 흐름이 전제다.

환산 공식: 환산액 = 원금 × (목표시점 지수 ÷ 기준시점 지수)

Streamlit을 import하지 않으므로 단독 테스트가 가능하다.
"""
from __future__ import annotations

import io
import re
from typing import Dict, List, Optional, Tuple

import pandas as pd

from utils.ecos_catalog import auto_match_code
from utils.monitor import resolve_item

# ─────────────────────────────────────────────
# 신뢰도 등급
# ─────────────────────────────────────────────
CONF_HIGH = "높음"
CONF_MEDIUM = "중간"
CONF_LOW = "낮음"
CONF_NONE = "실패"

# 원칙 4: matplotlib / background_gradient 금지 → 색상은 이모지로 표현
CONF_ICON = {
    CONF_HIGH: "🟢 높음",
    CONF_MEDIUM: "🟠 중간",
    CONF_LOW: "🔴 낮음",
    CONF_NONE: "⚪ 실패",
}

# 사람 확인 없이 통과시켜도 되는 등급 (그 외는 확인 필수)
AUTO_OK_LEVELS = {CONF_HIGH}

# 행 수 상한 — 품목별 개별 API 호출이 발생하므로 보수적으로 제한
MAX_ROWS = 300

# 공사 성격 키워드.
# 이런 행은 설비 PPI(ECOS)가 아니라 건설공사비지수(KOSIS)를 써야 할 가능성이 높다.
# 예: "펌프실 건축공사"는 '펌프'가 들어 있어 설비 품목으로 강하게 매칭되지만
# 실제로는 공사비 항목이다 — 지수 자체가 틀리는 범주 오류라 반드시 사람이 봐야 한다.
CONSTRUCTION_HINTS = [
    "공사", "건축", "토목", "시공", "철거", "포장", "조경",
    "가설", "부대공", "설치비", "배관공", "도장공", "기초공",
]

# 품목명 컬럼 후보 (견적서에서 흔히 쓰는 헤더)
ITEM_COL_HINTS = ["품목", "품명", "자산", "설비", "공사명", "내역", "항목", "규격", "명칭", "item", "name"]
# 금액 컬럼 후보
AMOUNT_COL_HINTS = ["금액", "투자비", "공사비", "가격", "단가", "원가", "합계", "amount", "cost", "price"]


def _norm(s) -> str:
    """공백 제거 + 소문자화 (카탈로그 ITEM_NAME_NORM과 동일 규칙)"""
    return re.sub(r"\s+", "", str(s)).lower()


# ─────────────────────────────────────────────
# 1) 파일 읽기 · 컬럼 추정
# ─────────────────────────────────────────────
def read_table(file_obj, filename: str = "") -> pd.DataFrame:
    """업로드된 xlsx/xls/csv를 DataFrame으로 읽는다."""
    name = (filename or getattr(file_obj, "name", "") or "").lower()
    if name.endswith(".csv"):
        raw = file_obj.read() if hasattr(file_obj, "read") else file_obj
        if isinstance(raw, bytes):
            for enc in ("utf-8-sig", "cp949", "utf-8"):
                try:
                    return pd.read_csv(io.BytesIO(raw), encoding=enc)
                except UnicodeDecodeError:
                    continue
            raise ValueError("CSV 인코딩을 판별할 수 없습니다 (utf-8/cp949 시도 실패).")
        return pd.read_csv(raw)
    return pd.read_excel(file_obj)


def guess_columns(df: pd.DataFrame) -> Tuple[Optional[str], Optional[str]]:
    """
    품목명 컬럼 · 금액 컬럼을 추정한다. 확정이 아니라 '기본 선택값' 제안용이며
    UI에서 사람이 바꿀 수 있어야 한다.
    """
    item_col = amount_col = None

    for col in df.columns:
        c = _norm(col)
        if item_col is None and any(h in c for h in (_norm(x) for x in ITEM_COL_HINTS)):
            item_col = col
        if amount_col is None and any(h in c for h in (_norm(x) for x in AMOUNT_COL_HINTS)):
            amount_col = col

    # 금액 컬럼을 못 찾았으면 '숫자 비율이 가장 높은 컬럼'으로 대체 추정
    if amount_col is None:
        best_ratio, best_col = 0.0, None
        for col in df.columns:
            if col == item_col:
                continue
            parsed = df[col].map(parse_amount)
            ratio = float(parsed.notna().mean()) if len(parsed) else 0.0
            if ratio > best_ratio:
                best_ratio, best_col = ratio, col
        if best_ratio >= 0.6:
            amount_col = best_col

    # 품목명 컬럼을 못 찾았으면 '문자 비율이 가장 높은 컬럼'
    if item_col is None:
        best_ratio, best_col = 0.0, None
        for col in df.columns:
            if col == amount_col:
                continue
            ratio = float(df[col].map(lambda v: isinstance(v, str) and len(v.strip()) > 1).mean()) if len(df) else 0.0
            if ratio > best_ratio:
                best_ratio, best_col = ratio, col
        item_col = best_col

    return item_col, amount_col


def parse_amount(v) -> Optional[float]:
    """
    금액 문자열을 숫자로 변환. '1,234,567' · '₩1,200' · '3 500원' 등을 처리한다.
    '800억'처럼 단위가 붙은 값은 해석을 추측하지 않고 None을 반환한다
    (억/만원 오해석은 100배 오차를 조용히 만들기 때문).
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return None if pd.isna(f) else f

    s = str(v).strip()
    if not s:
        return None
    # 단위 표기가 섞인 값은 거부 (사람이 숫자로 정리해야 함)
    if re.search(r"[억만천]", s):
        return None
    s = re.sub(r"[₩,\s원]", "", s)
    if not re.fullmatch(r"-?\d+(\.\d+)?", s):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ─────────────────────────────────────────────
# 2) 매칭 + 신뢰도 산정
# ─────────────────────────────────────────────
def classify_confidence(
    query: str,
    best: Optional[Dict],
    candidates: List[Dict],
) -> Tuple[str, str]:
    """
    매칭 결과의 신뢰도와 '판단 근거'를 함께 반환한다.
    근거를 노출하는 이유: 검토자가 등급을 그냥 믿는 대신 스스로 판단할 수 있어야 한다.

    Returns (level, reason)
    """
    if not best:
        return CONF_NONE, "매칭 후보 없음 — 품목을 직접 지정해야 합니다"

    # 공사 성격 항목은 점수가 아무리 높아도 '낮음'으로 내린다.
    # 설비 PPI로 환산하면 지수를 잘못 고른 것이므로 사람이 반드시 판단해야 한다.
    hit = next((h for h in CONSTRUCTION_HINTS if h in str(query)), None)
    if hit:
        return CONF_LOW, (
            f"'{hit}' 포함 — 공사비 항목일 수 있습니다. 설비 PPI가 아니라 "
            "'공사비 물가보정' 탭(건설공사비지수)이 맞는지 확인하세요"
        )

    score = float(best.get("score", 0) or 0)
    second = float(candidates[1]["score"]) if len(candidates) > 1 else 0.0
    margin = score - second

    qn, bn = _norm(query), _norm(best.get("name", ""))

    if bn and bn == qn:
        return CONF_HIGH, "품목명 완전일치"

    # 후보 1·2위가 사실상 동점이면 자동 선택은 동전던지기 → 등급을 내린다
    if len(candidates) > 1 and margin < 2.0:
        return CONF_LOW, f"1·2위 점수차 {margin:.1f}점 — 후보 간 구분 불가"

    if bn and bn in qn:
        return CONF_HIGH, f"ECOS 품목명('{best.get('name')}')이 견적 품목명에 포함"

    if score >= 25.0:
        return CONF_HIGH, f"강한 일치 (점수 {score:.0f}, 2위와 {margin:.0f}점 차)"

    if score >= 13.0:
        return CONF_MEDIUM, f"부분 일치 (키워드 '{best.get('matched_keyword','')}', 점수 {score:.0f})"

    return CONF_LOW, f"약한 일치 (점수 {score:.0f}) — 확인 필요"


def suggest_matches(
    df: pd.DataFrame,
    item_col: str,
    amount_col: Optional[str],
    catalog: pd.DataFrame,
    top_n: int = 5,
) -> pd.DataFrame:
    """
    각 행의 품목명 → ECOS 품목 자동 제안 + 신뢰도 부여.
    같은 품목명이 반복되면 매칭을 재사용해 계산을 줄인다.

    Returns DataFrame[
      행, 견적품목명, 금액, 제안코드, 제안품목, 신뢰도, 판단근거, 후보, 금액오류
    ]
    """
    if catalog is None or len(catalog) == 0:
        raise ValueError("ECOS 카탈로그가 비어 있습니다. 인증키와 네트워크를 확인하세요.")

    cache: Dict[str, Tuple[Optional[Dict], List[Dict]]] = {}
    out = []

    for idx, row in df.iterrows():
        raw_name = row.get(item_col, "")
        name = "" if pd.isna(raw_name) else str(raw_name).strip()

        amount = parse_amount(row.get(amount_col)) if amount_col else None
        amount_err = ""
        if amount_col and amount is None:
            amount_err = f"금액 해석 실패: '{row.get(amount_col)}'"

        if not name:
            out.append({
                "행": int(idx) + 2,  # 엑셀 행번호 (헤더 1행 가정)
                "견적품목명": "",
                "금액": amount,
                "제안코드": "",
                "제안품목": "",
                "신뢰도": CONF_NONE,
                "판단근거": "품목명이 비어 있음",
                "후보": [],
                "금액오류": amount_err,
            })
            continue

        if name in cache:
            best, cands = cache[name]
        else:
            best, cands = auto_match_code(name, catalog_df=catalog, top_n=top_n)
            # auto_match_code가 실패하면 단순 부분일치(monitor.resolve_item)로 한 번 더 시도
            if not best:
                fallback = resolve_item(catalog, [name])
                if fallback:
                    best = {
                        "code": fallback["code"],
                        "name": fallback["name"],
                        "score": 6.0,          # 약한 일치로 취급
                        "matched_keyword": fallback.get("matched", name),
                    }
                    cands = [best]
            cache[name] = (best, cands)

        level, reason = classify_confidence(name, best, cands)

        out.append({
            "행": int(idx) + 2,
            "견적품목명": name,
            "금액": amount,
            "제안코드": (best or {}).get("code", ""),
            "제안품목": (best or {}).get("name", ""),
            "신뢰도": level,
            "판단근거": reason,
            "후보": cands or [],
            "금액오류": amount_err,
        })

    return pd.DataFrame(out)


# ─────────────────────────────────────────────
# 3) 승인 게이트
# ─────────────────────────────────────────────
def approval_blockers(review_df: pd.DataFrame) -> List[str]:
    """
    보정 실행을 막아야 하는 사유 목록. 빈 리스트면 실행 가능.
    '확인' 열(bool)이 있으면 사람이 확인한 행은 통과시킨다.
    """
    problems: List[str] = []
    if review_df is None or len(review_df) == 0:
        return ["보정할 행이 없습니다."]

    confirmed = (
        review_df["확인"].fillna(False).astype(bool)
        if "확인" in review_df.columns
        else pd.Series([False] * len(review_df), index=review_df.index)
    )

    no_code = review_df["제안코드"].astype(str).str.strip() == ""
    if no_code.any():
        rows = ", ".join(str(r) for r in review_df.loc[no_code, "행"].head(10))
        problems.append(f"품목코드가 비어 있는 행 {int(no_code.sum())}건 (행 {rows}) — 품목을 지정하세요.")

    risky = ~review_df["신뢰도"].isin(AUTO_OK_LEVELS) & ~confirmed & ~no_code
    if risky.any():
        rows = ", ".join(str(r) for r in review_df.loc[risky, "행"].head(10))
        problems.append(
            f"신뢰도 '중간·낮음·실패'인데 확인되지 않은 행 {int(risky.sum())}건 (행 {rows}) — "
            "매칭을 검토한 뒤 '확인'에 체크하세요."
        )

    bad_amount = review_df["금액"].isna()
    if bad_amount.any():
        rows = ", ".join(str(r) for r in review_df.loc[bad_amount, "행"].head(10))
        problems.append(
            f"금액을 숫자로 읽을 수 없는 행 {int(bad_amount.sum())}건 (행 {rows}) — "
            "'800억' 같은 단위 표기는 숫자로 정리해야 합니다."
        )

    if len(review_df) > MAX_ROWS:
        problems.append(f"행 수 {len(review_df)}건이 상한 {MAX_ROWS}건을 초과합니다. 나눠서 처리하세요.")

    return problems


# ─────────────────────────────────────────────
# 4) 지수 조회 (품목코드 단위 캐시)
# ─────────────────────────────────────────────
def fetch_index_pair(
    client,
    code: str,
    base: str,
    target: str,
    cache: Optional[Dict] = None,
) -> Tuple[Optional[float], Optional[float], str]:
    """
    한 품목코드의 기준·목표 시점 지수를 조회한다.
    구간을 한 번에 받아 두 값을 뽑으므로 코드당 API 호출은 1회.
    동일 코드가 반복되면 cache에서 재사용한다.

    Returns (base_index, target_index, error)
    """
    if cache is None:
        cache = {}
    key = (str(code), str(base), str(target))
    if key in cache:
        return cache[key]

    lo, hi = sorted([str(base), str(target)])
    try:
        df = client.get_ppi(str(code), lo, hi)
    except Exception as e:  # noqa: BLE001 — API 오류를 행 단위로 표면화
        res = (None, None, f"조회 실패: {e}")
        cache[key] = res
        return res

    s = df.copy()
    s["TIME"] = s["TIME"].astype(str)

    def pick(period: str) -> Optional[float]:
        hit = s.loc[s["TIME"] == str(period), "DATA_VALUE"]
        return float(hit.iloc[0]) if len(hit) else None

    b, t = pick(base), pick(target)

    err = ""
    if b is None and t is None:
        err = f"기준({base})·목표({target}) 지수 모두 없음"
    elif b is None:
        err = f"기준시점 {base} 지수 없음"
    elif t is None:
        err = f"목표시점 {target} 지수 없음 — 아직 미발표일 수 있습니다"

    res = (b, t, err)
    cache[key] = res
    return res


# ─────────────────────────────────────────────
# 5) 일괄 보정 실행
# ─────────────────────────────────────────────
def run_batch(
    review_df: pd.DataFrame,
    client,
    base: str,
    target: str,
    progress_cb=None,
) -> pd.DataFrame:
    """
    승인된 매칭표를 받아 전체 행을 보정한다.

    progress_cb(done, total, label) — 진행률 콜백 (선택)

    Returns DataFrame[
      행, 견적품목명, ECOS품목, 품목코드, 신뢰도, 확인,
      원금, 기준지수, 목표지수, 보정계수, 환산액, 증감액, 증감률(%), 오류
    ]
    """
    cache: Dict = {}
    rows: List[Dict] = []

    # 같은 코드끼리 모아 호출 순서를 정하면 캐시 적중이 빨라진다
    order = review_df.sort_values("제안코드", kind="stable").index
    total = len(order)

    for n, idx in enumerate(order, start=1):
        r = review_df.loc[idx]
        code = str(r.get("제안코드", "") or "").strip()
        principal = r.get("금액")
        label = str(r.get("견적품목명", ""))

        if progress_cb:
            progress_cb(n, total, label)

        base_idx = target_idx = factor = adjusted = None
        err = ""

        if not code:
            err = "품목코드 없음"
        elif principal is None or pd.isna(principal):
            err = "금액 없음"
        else:
            base_idx, target_idx, err = fetch_index_pair(client, code, base, target, cache)
            if not err and base_idx and target_idx:
                if base_idx == 0:
                    err = "기준지수가 0 — 보정 불가"
                else:
                    factor = target_idx / base_idx
                    adjusted = float(principal) * factor

        rows.append({
            "행": r.get("행"),
            "견적품목명": label,
            "ECOS품목": r.get("제안품목", ""),
            "품목코드": code,
            "신뢰도": r.get("신뢰도", ""),
            "확인": bool(r.get("확인", False)) if "확인" in review_df.columns else False,
            "원금": principal,
            "기준지수": base_idx,
            "목표지수": target_idx,
            "보정계수": round(factor, 6) if factor else None,
            "환산액": round(adjusted, 2) if adjusted is not None else None,
            "증감액": round(adjusted - float(principal), 2) if adjusted is not None else None,
            "증감률(%)": round((factor - 1) * 100, 2) if factor else None,
            "오류": err,
        })

    out = pd.DataFrame(rows)
    # 원래 엑셀 행 순서로 복원
    if "행" in out.columns:
        out = out.sort_values("행", kind="stable").reset_index(drop=True)
    return out


def summarize(result_df: pd.DataFrame) -> Dict:
    """일괄 보정 결과 요약. 실패 행은 합계에서 제외하고 별도로 센다."""
    if result_df is None or len(result_df) == 0:
        return {"건수": 0, "성공": 0, "실패": 0, "원금합계": 0.0, "환산합계": 0.0,
                "증감액": 0.0, "증감률(%)": None, "저신뢰건수": 0}

    ok = result_df[result_df["환산액"].notna()]
    principal = float(ok["원금"].sum()) if len(ok) else 0.0
    adjusted = float(ok["환산액"].sum()) if len(ok) else 0.0

    return {
        "건수": int(len(result_df)),
        "성공": int(len(ok)),
        "실패": int(len(result_df) - len(ok)),
        "원금합계": principal,
        "환산합계": adjusted,
        "증감액": adjusted - principal,
        "증감률(%)": round((adjusted / principal - 1) * 100, 2) if principal else None,
        "저신뢰건수": int((~result_df["신뢰도"].isin(AUTO_OK_LEVELS)).sum()),
    }
