"""
ECOS 품목 카탈로그를 그대로 출력한다 — 실제 품목명·코드를 눈으로 확인하는 용도.

왜 필요한가
  data/steel_plant_items.py의 keywords는 '이런 이름일 것이다'는 추정이다.
  추정으로 채우면 조용히 엉뚱한 품목이 잡힌다. 실제 카탈로그를 보고 골라야 한다.

사용
    $env:ECOS_API_KEY="키"

    # 설비 투자비 보정에 쓰이는 계열만 (기계·전기·금속·비금속 등)
    python -m scripts.dump_catalog --preset equipment

    # 이름으로 검색
    python -m scripts.dump_catalog --grep 변압
    python -m scripts.dump_catalog --grep "일반목적|특수목적|금속가공"

    # 계층 구조로 (상위 분류 → 세부 품목)
    python -m scripts.dump_catalog --preset equipment --tree

    # 전체를 엑셀로 (1,577개)
    python -m scripts.dump_catalog --csv catalog.csv
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from utils.ecos_catalog import get_catalog  # noqa: E402

# 설비 투자비 보정에서 실제로 쓰이는 계열.
# 코드가 아니라 '이름에 들어갈 단어'라서 통계표 개편에도 잘 견딘다.
PRESETS = {
    "equipment": [
        # 기계
        "기계", "장비", "펌프", "압축기", "기관", "터빈", "원동기", "보일러",
        "크레인", "컨베이어", "운반", "하역", "승강", "권양",
        "공조", "냉동", "환기", "베어링", "기어", "동력전달", "밸브", "유압",
        "로봇", "건설", "광산", "굴삭", "로및노", "산업용로",
        # 전기
        "변압기", "전동기", "발전기", "배전", "제어", "개폐", "배선",
        "케이블", "전선", "절연", "축전지", "조명", "전기장비",
        # 계측
        "계측", "계량", "측정", "분석",
        # 금속·구조
        "금속", "철강", "형강", "강판", "후판", "철근", "선재", "강관",
        "구조물", "탱크", "저장용기", "주물", "단조", "도금",
        # 비금속·화학·에너지
        "시멘트", "콘크리트", "레미콘", "골재", "내화", "벽돌", "유리",
        "화학", "도료", "가스", "코크스", "전력", "수도",
        # 상위 지수
        "총지수", "공산품",
    ],
    "machinery": [
        "일반목적용기계", "특수목적용기계", "금속가공기계", "기계및장비",
        "펌프", "압축기", "내연기관", "터빈", "운반하역", "공기조화",
        "베어링", "동력전달", "밸브",
    ],
    "electrical": [
        "전기장비", "변압기", "전동기", "발전기", "배전", "제어기기",
        "절연선", "케이블", "축전지", "조명",
    ],
}


def main() -> int:
    p = argparse.ArgumentParser(description="ECOS 품목 카탈로그 조회")
    p.add_argument("--preset", choices=sorted(PRESETS), help="미리 정의된 계열 필터")
    p.add_argument("--grep", default="", help="품목명 정규식 검색 (예: '변압|전동기')")
    p.add_argument("--level", type=int, default=0, help="이 레벨 이하만 (0=전체)")
    p.add_argument("--tree", action="store_true", help="ITEM_LEVEL 들여쓰기로 계층 표시")
    p.add_argument("--csv", default="", help="결과를 CSV로 저장")
    p.add_argument("--limit", type=int, default=0, help="출력 개수 제한 (0=전체)")
    args = p.parse_args()

    if not os.getenv("ECOS_API_KEY"):
        print("[오류] ECOS_API_KEY가 설정되지 않았습니다.", file=sys.stderr)
        print('       $env:ECOS_API_KEY="키" 를 먼저 실행하세요.', file=sys.stderr)
        return 2

    cat = get_catalog(api_key=os.getenv("ECOS_API_KEY"))
    if cat is None or len(cat) == 0:
        print("[오류] 카탈로그를 불러오지 못했습니다. 키·네트워크를 확인하세요.", file=sys.stderr)
        return 2

    total = len(cat)
    names = cat["ITEM_NAME"].astype(str)

    if args.preset:
        kws = PRESETS[args.preset]
        mask = names.apply(lambda n: any(k in n.replace(" ", "") for k in kws))
        cat = cat[mask]
        print(f"카탈로그 {total:,}개 중 preset '{args.preset}' 필터 → {len(cat):,}개\n")
    elif args.grep:
        try:
            mask = names.str.contains(args.grep, case=False, na=False, regex=True)
        except re.error as e:
            print(f"[오류] 정규식이 잘못됐습니다: {e}", file=sys.stderr)
            return 2
        cat = cat[mask]
        print(f"카탈로그 {total:,}개 중 '{args.grep}' 검색 → {len(cat):,}개\n")
    else:
        print(f"카탈로그 전체 {total:,}개\n")

    if args.level and "ITEM_LEVEL" in cat.columns:
        lv = pd.to_numeric(cat["ITEM_LEVEL"], errors="coerce")
        cat = cat[lv <= args.level]
        print(f"레벨 {args.level} 이하 → {len(cat):,}개\n")

    if len(cat) == 0:
        print("조건에 맞는 품목이 없습니다.")
        return 0

    show = cat.head(args.limit) if args.limit else cat
    print(f"{'코드':<12} {'Lv':<3} 품목명")
    print("─" * 72)
    for r in show.itertuples():
        lv_raw = str(getattr(r, "ITEM_LEVEL", "") or "")
        lv = int(lv_raw) if lv_raw.isdigit() else 0
        indent = "  " * max(0, lv - 1) if args.tree else ""
        print(f"{str(r.ITEM_CODE):<12} {lv:<3} {indent}{r.ITEM_NAME}")

    if args.limit and len(cat) > args.limit:
        print(f"\n... {len(cat) - args.limit:,}개 더 있음 (--limit 0 으로 전체 출력)")

    if args.csv:
        pathlib.Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
        keep = [c for c in ["ITEM_CODE", "ITEM_NAME", "ITEM_LEVEL", "P_ITEM_CODE",
                            "WGT", "UNIT_NAME", "START_TIME", "END_TIME"]
                if c in cat.columns]
        cat[keep].to_csv(args.csv, index=False, encoding="utf-8-sig")
        print(f"\n저장: {args.csv} ({len(cat):,}행)")
        print("엑셀로 열어 실제 품목명을 확인하고, 원하는 품목을 알려주세요.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
