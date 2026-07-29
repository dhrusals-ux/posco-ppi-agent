"""
관심 품목 키워드가 실제 ECOS 품목에 매칭되는지 검증한다.

data/steel_plant_items.py의 keywords는 '기대'일 뿐이고, 실제로 무엇에 매칭되는지는
카탈로그를 받아봐야 안다. 틀린 매칭은 에러 없이 조용히 엉뚱한 품목의 지수를
리포트에 실어 보내므로, 눈으로 확인할 수 있어야 한다.

사용
    $env:ECOS_API_KEY="키"; python -m scripts.verify_items
    python -m scripts.verify_items --csv result.csv     # 결과를 CSV로 저장

출력
    [OK]     label -> 실제 ECOS 품목명 (코드)   매칭된 키워드
    [약함]   1순위 키워드가 아닌 뒤쪽 폴백으로 잡힌 경우 — 확인 권장
    [실패]   아무 키워드도 매칭되지 않음 + 카탈로그에서 찾은 유사 후보 제시
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from data.steel_plant_items import STEEL_PLANT_ITEMS  # noqa: E402
from utils.ecos_catalog import get_catalog  # noqa: E402
from utils.monitor import resolve_item  # noqa: E402


def _norm(s) -> str:
    return re.sub(r"\s+", "", str(s)).lower()


def suggest(catalog: pd.DataFrame, label: str, keywords: list, limit: int = 5) -> list:
    """
    매칭 실패 시 카탈로그에서 유사 후보를 찾는다.
    키워드를 2글자 단위로 잘라 부분일치를 시도한다 — '절연선및케이블'이 실패하면
    '절연', '케이블' 같은 조각으로라도 실제 품목명을 찾아 보여준다.
    """
    names = catalog["ITEM_NAME"].astype(str)
    norm = names.map(_norm)

    frags = set()
    for kw in list(keywords) + [label]:
        k = _norm(kw)
        for size in (4, 3, 2):
            for i in range(0, max(1, len(k) - size + 1)):
                frag = k[i:i + size]
                if len(frag) >= 2:
                    frags.add(frag)

    hits: dict[str, str] = {}
    for frag in sorted(frags, key=len, reverse=True):
        mask = norm.str.contains(re.escape(frag), na=False)
        for _, row in catalog[mask].head(3).iterrows():
            code = str(row["ITEM_CODE"])
            if code not in hits:
                hits[code] = str(row["ITEM_NAME"])
        if len(hits) >= limit:
            break
    return [f"{n} ({c})" for c, n in list(hits.items())[:limit]]


def main() -> int:
    p = argparse.ArgumentParser(description="관심 품목 키워드 → 실제 ECOS 품목 매칭 검증")
    p.add_argument("--csv", default="", help="결과를 CSV로 저장할 경로")
    args = p.parse_args()

    if not os.getenv("ECOS_API_KEY"):
        print("[오류] ECOS_API_KEY가 설정되지 않았습니다.", file=sys.stderr)
        print("       $env:ECOS_API_KEY=\"키\" 를 먼저 실행하세요.", file=sys.stderr)
        return 2

    catalog = get_catalog(api_key=os.getenv("ECOS_API_KEY"))
    if catalog is None or len(catalog) == 0:
        print("[오류] ECOS 카탈로그를 불러오지 못했습니다. 키·네트워크를 확인하세요.",
              file=sys.stderr)
        return 2

    print(f"ECOS 카탈로그 {len(catalog):,}개 품목 로드 완료\n")

    rows = []
    n_ok = n_weak = n_fail = 0

    for proc, items in STEEL_PLANT_ITEMS.items():
        print(f"{'─' * 74}\n[{proc}]")
        for it in items:
            label = it["label"]
            kws = it.get("keywords", [])
            res = resolve_item(catalog, kws)

            if not res:
                n_fail += 1
                cands = suggest(catalog, label, kws)
                print(f"  실패   {label:22} 키워드={kws}")
                if cands:
                    print(f"         후보: {', '.join(cands)}")
                rows.append({"공정": proc, "label": label, "상태": "실패",
                             "키워드": " / ".join(kws), "매칭키워드": "",
                             "ECOS품목명": "", "코드": "", "후보": " | ".join(cands)})
                continue

            matched = res.get("matched", "")
            # 1순위 키워드로 잡혔는지 — 뒤쪽 폴백이면 확인이 필요하다
            is_primary = bool(kws) and _norm(matched) == _norm(kws[0])
            exact_name = _norm(res["name"]) == _norm(matched)

            if is_primary or exact_name:
                n_ok += 1
                status, tag = "OK", "OK    "
            else:
                n_weak += 1
                status, tag = "약함", "약함  "

            print(f"  {tag} {label:22} -> {res['name']} ({res['code']})"
                  f"   [키워드: {matched}]")
            rows.append({"공정": proc, "label": label, "상태": status,
                         "키워드": " / ".join(kws), "매칭키워드": matched,
                         "ECOS품목명": res["name"], "코드": res["code"], "후보": ""})

    total = n_ok + n_weak + n_fail
    print(f"\n{'═' * 74}")
    print(f"전체 {total}건 — OK {n_ok} · 약함 {n_weak} · 실패 {n_fail}")

    # 서로 다른 label이 같은 코드로 매칭되면, 리포트에 같은 지수가 여러 줄로 나온다
    df = pd.DataFrame(rows)
    matched_df = df[df["코드"] != ""]
    dup = matched_df.groupby("코드")["label"].nunique()
    dup_codes = dup[dup > 1]
    if len(dup_codes):
        print(f"\n※ 서로 다른 품목이 같은 ECOS 코드로 매칭됐습니다 ({len(dup_codes)}건).")
        print("   리포트에 동일한 지수가 여러 줄로 나오니 키워드를 구분해 주세요.")
        for code in dup_codes.index:
            labels = matched_df[matched_df["코드"] == code]["label"].unique()
            name = matched_df[matched_df["코드"] == code]["ECOS품목명"].iloc[0]
            print(f"   {code} ({name}): {', '.join(labels)}")

    if n_weak:
        print(f"\n※ '약함' {n_weak}건은 1순위 키워드가 아닌 폴백으로 매칭됐습니다.")
        print("   엉뚱한 품목이 잡혔을 수 있으니 ECOS품목명을 확인하세요.")
    if n_fail:
        print(f"\n※ '실패' {n_fail}건은 리포트·모니터링에서 빠집니다.")
        print("   위 '후보'를 참고해 data/steel_plant_items.py의 keywords를 고치세요.")

    if args.csv:
        pathlib.Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(args.csv, index=False, encoding="utf-8-sig")
        print(f"\n결과 저장: {args.csv}")

    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
