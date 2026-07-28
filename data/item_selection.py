"""
관심 품목 '공정별' 선택 저장 (ECOS 카탈로그에서 직접 고른 실제 품목)

왜 이게 필요한가
  steel_plant_items.py의 keywords는 '이런 이름일 것이다'는 추정이고, 추정이 틀리면
  에러 없이 엉뚱한 품목의 지수가 리포트에 실린다. 카탈로그에서 직접 골라 **실제
  ITEM_CODE**를 저장하면 매칭 단계가 사라져 그 위험이 없어진다.

저장 형식 (data/selected_items.json)
  {
    "version": 1,
    "updated_at": "2026-07-29 10:00",
    "processes": {
      "제선": [{"code": "...", "name": "...", "note": "고로 내장재"}, ...],
      "제강": [...]
    }
  }

⚠️ Streamlit Cloud는 파일 시스템이 휘발성이다. 앱에서 '저장'을 눌러도 서버에
   영구 보관되지 않고, GitHub Actions(월간 메일)는 아예 다른 프로세스다.
   따라서 흐름은 이렇게 된다:
     1) 앱에서 공정별로 고른다        → 그 세션에서 바로 모니터링에 쓰임
     2) JSON을 내려받아 레포에 커밋   → 앱·월간 메일이 모두 이 파일을 읽음
   커밋된 파일이 없으면 steel_plant_items.py의 기본 목록으로 폴백한다.
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

KST = timezone(timedelta(hours=9))

SCHEMA_VERSION = 1

# 레포 루트 기준 경로
_ROOT = pathlib.Path(__file__).resolve().parent.parent
SELECTION_PATH = _ROOT / "data" / "selected_items.json"

# 기본 공정 구분 — 사용자가 앱에서 직접 추가할 수도 있다
DEFAULT_PROCESSES = [
    "제선",
    "제강",
    "열연",
    "냉연·도금",
    "발전·유틸리티",
    "인프라·토건",
    "상위 지수",
]

# ─────────────────────────────────────────────
# 플랜트 설비 카테고리 (ECOS 품목명에 들어갈 단어 기준)
# 코드가 아니라 '이름 조각'으로 거르므로 통계표 개편에 깨지지 않는다 (원칙 1).
# 앱의 품목 선택 필터와 scripts/dump_catalog.py가 이 하나를 공유한다.
# ─────────────────────────────────────────────
PLANT_CATEGORIES: Dict[str, List[str]] = {
    "기계·장비": [
        "기계", "장비", "펌프", "압축기", "송풍", "기관", "터빈", "원동기",
        "보일러", "크레인", "컨베이어", "운반", "하역", "승강", "권양",
        "공조", "공기조화", "냉동", "환기", "베어링", "기어", "동력전달",
        "밸브", "유압", "공압", "로봇", "건설", "광산", "굴삭",
        "산업용로", "로및노", "열교환",
    ],
    "전기·전력설비": [
        "전기장비", "변압기", "전동기", "발전기", "배전", "개폐", "배선",
        "제어기기", "케이블", "전선", "절연", "축전지", "전지", "조명", "램프",
        "전력변환", "인버터",
    ],
    "계측·제어": [
        "계측", "계량", "측정", "분석", "제어", "자동", "센서", "정밀기기",
    ],
    "금속·구조재": [
        "철강", "형강", "강판", "후판", "철근", "선재", "강관", "강선",
        "금속", "구조물", "탱크", "저장용기", "주물", "단조", "도금",
        "알루미늄", "구리", "아연", "니켈", "합금철", "스테인리스",
    ],
    "내화·건자재": [
        "내화", "벽돌", "시멘트", "콘크리트", "레미콘", "골재", "자갈", "모래",
        "유리", "타일", "단열", "석고", "비금속광물",
    ],
    "화학·약품": [
        "화학", "도료", "페인트", "산", "알칼리", "가스", "윤활",
        "수지", "용제", "촉매",
    ],
    "에너지·유틸리티": [
        "전력", "도시가스", "수도", "코크스", "유연탄", "석탄", "석유",
        "경유", "중유", "증기", "열",
    ],
    "상위 지수": [
        "총지수", "공산품", "제1차금속", "1차금속", "금속가공제품",
        "기계및장비", "전기장비", "비금속광물제품", "화학제품",
    ],
}


def category_keywords(names: Optional[List[str]] = None) -> List[str]:
    """선택된 카테고리들의 키워드를 합친다. names가 없으면 전체."""
    if not names:
        names = list(PLANT_CATEGORIES)
    out: List[str] = []
    for n in names:
        out.extend(PLANT_CATEGORIES.get(n, []))
    return out


def filter_catalog(catalog, categories: Optional[List[str]] = None, query: str = ""):
    """
    카탈로그를 플랜트 카테고리·검색어로 거른다.
    catalog: ECOS 카탈로그 DataFrame (ITEM_CODE, ITEM_NAME, ...)
    """
    if catalog is None or len(catalog) == 0 or "ITEM_NAME" not in catalog.columns:
        return catalog

    df = catalog
    if categories:
        kws = category_keywords(categories)
        if kws:
            names = df["ITEM_NAME"].astype(str).str.replace(r"\s+", "", regex=True)
            mask = names.apply(lambda n: any(k in n for k in kws))
            df = df[mask]

    q = (query or "").strip()
    if q:
        df = df[df["ITEM_NAME"].astype(str).str.contains(q, case=False, na=False)]

    return df.reset_index(drop=True)


# ─────────────────────────────────────────────
# 저장 · 로드
# ─────────────────────────────────────────────
def empty_selection() -> Dict:
    return {
        "version": SCHEMA_VERSION,
        "updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "processes": {},
    }


def normalize(sel: Optional[Dict]) -> Dict:
    """
    형식을 보정한다. 손으로 편집한 JSON이나 옛 버전이 들어와도 깨지지 않게 한다.
    코드가 없는 항목은 버린다 — 코드가 없으면 조회할 수 없고, 조용히 빠지면
    '선택했는데 리포트에 없다'는 상황이 된다.
    """
    if not isinstance(sel, dict):
        return empty_selection()

    procs_in = sel.get("processes")
    if not isinstance(procs_in, dict):
        procs_in = {}

    procs: Dict[str, List[Dict]] = {}
    for proc, items in procs_in.items():
        if not isinstance(items, list):
            continue
        seen, clean = set(), []
        for it in items:
            if not isinstance(it, dict):
                continue
            code = str(it.get("code") or "").strip()
            if not code or code in seen:
                continue
            seen.add(code)
            clean.append({
                "code": code,
                "name": str(it.get("name") or "").strip(),
                "note": str(it.get("note") or "").strip(),
            })
        if clean:
            procs[str(proc)] = clean

    return {
        "version": SCHEMA_VERSION,
        "updated_at": str(sel.get("updated_at") or datetime.now(KST).strftime("%Y-%m-%d %H:%M")),
        "processes": procs,
    }


def load_selection(path: Optional[pathlib.Path] = None) -> Optional[Dict]:
    """
    저장된 선택을 읽는다. 파일이 없으면 None (기본 목록으로 폴백해야 함).
    깨진 파일이면 조용히 무시하지 않고 예외를 올린다 — 선택이 사라진 채로
    기본 목록이 쓰이면 사용자는 자기 설정이 반영됐다고 착각한다.
    """
    p = pathlib.Path(path) if path else SELECTION_PATH
    if not p.exists():
        return None
    raw = json.loads(p.read_text(encoding="utf-8"))
    return normalize(raw)


def dumps_selection(sel: Dict) -> str:
    """다운로드·커밋용 JSON 문자열"""
    s = normalize(sel)
    s["updated_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    return json.dumps(s, ensure_ascii=False, indent=2) + "\n"


def save_selection(sel: Dict, path: Optional[pathlib.Path] = None) -> pathlib.Path:
    """로컬 파일로 저장 (Streamlit Cloud에서는 휘발성이므로 다운로드를 권장)"""
    p = pathlib.Path(path) if path else SELECTION_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dumps_selection(sel), encoding="utf-8")
    return p


# ─────────────────────────────────────────────
# 변환 · 요약
# ─────────────────────────────────────────────
def selection_to_items(sel: Optional[Dict]) -> List[Dict]:
    """
    build_monitor / build_report가 받는 형태로 변환한다.
    code가 들어 있으므로 monitor는 키워드 매칭을 건너뛴다.
    """
    s = normalize(sel)
    out: List[Dict] = []
    for proc, items in s["processes"].items():
        for it in items:
            out.append({
                "label": it["name"] or it["code"],
                "ecos_name": it["name"],
                "code": it["code"],
                "note": it.get("note", ""),
                "process": proc,
                "keywords": [],          # 코드가 있으므로 사용되지 않음
            })
    return out


def counts(sel: Optional[Dict]) -> Dict[str, int]:
    s = normalize(sel)
    return {p: len(items) for p, items in s["processes"].items()}


def total_count(sel: Optional[Dict]) -> int:
    return sum(counts(sel).values())


def codes_of(sel: Optional[Dict], process: str) -> List[str]:
    s = normalize(sel)
    return [it["code"] for it in s["processes"].get(process, [])]


def set_process(sel: Dict, process: str, items: List[Dict]) -> Dict:
    """
    특정 공정의 선택을 통째로 교체한다. 다른 공정은 건드리지 않는다.
    items가 비면 그 공정을 제거한다.
    """
    s = normalize(sel)
    clean = []
    seen = set()
    for it in items:
        code = str(it.get("code") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        clean.append({
            "code": code,
            "name": str(it.get("name") or "").strip(),
            "note": str(it.get("note") or "").strip(),
        })
    if clean:
        s["processes"][process] = clean
    else:
        s["processes"].pop(process, None)
    s["updated_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    return s


def from_default_items(catalog, default_items: List[Dict]) -> Dict:
    """
    steel_plant_items.py의 기본 목록을 카탈로그에 매칭해 선택 형식으로 바꾼다.
    '기본 목록 불러오기' 버튼용 — 처음부터 1,577개를 훑지 않고 시작할 수 있다.
    매칭 실패한 항목은 넣지 않는다 (코드가 없으면 조회 불가).
    """
    from utils.monitor import resolve_item

    sel = empty_selection()
    for it in default_items:
        proc = it.get("process", "기타")
        res = resolve_item(catalog, it.get("keywords", []))
        if not res:
            continue
        sel["processes"].setdefault(proc, []).append({
            "code": res["code"],
            "name": res["name"],
            "note": it.get("note", ""),
        })
    return normalize(sel)
