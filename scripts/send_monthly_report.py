"""
월간 물가동향 리포트 생성 · 발송 CLI

★ 기본 동작은 미리보기(dry-run)다. 실제 발송은 --send를 명시해야 한다.
  실수로 돌렸을 때 수신자에게 메일이 날아가지 않게 하기 위한 것이다.

사용
    # 미리보기 (메일 발송 안 함, HTML 파일로 저장)
    python -m scripts.send_monthly_report --out preview.html

    # 실제 발송
    python -m scripts.send_monthly_report --send

    # 신규 발표가 없어도 강제 발송 (중복 발송 주의)
    python -m scripts.send_monthly_report --send --force

필요한 환경변수
    ECOS_API_KEY        한국은행 ECOS 인증키
    SMTP_HOST           메일 서버 (사내 릴레이 또는 smtp.gmail.com)
    SMTP_PORT           기본 587 (465면 SSL로 자동 전환)
    SMTP_USER           계정
    SMTP_PASSWORD       비밀번호 / 앱 비밀번호
    SMTP_FROM           보내는 주소 (없으면 SMTP_USER)
    REPORT_RECIPIENTS   받는 주소, 쉼표 구분
    LAST_SENT_PERIOD    (선택) 지난 발송 기준월 YYYYMM — 중복 발송 방지
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys

# 레포 루트를 import 경로에 넣는다 (python scripts/... 로 직접 실행하는 경우 대비)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from data.steel_plant_items import get_all_items_flat  # noqa: E402
from utils.ecos_catalog import get_catalog  # noqa: E402
from utils.ecos_client import ECOSClient  # noqa: E402
from utils.report_mail import (  # noqa: E402
    SmtpConfig, build_report, render_html, render_text, send_email, subject_line,
)


def main() -> int:
    p = argparse.ArgumentParser(description="월간 물가동향 리포트 생성·발송")
    p.add_argument("--send", action="store_true",
                   help="실제로 메일을 발송한다 (기본은 미리보기)")
    p.add_argument("--force", action="store_true",
                   help="신규 발표가 없어도 발송한다 (중복 발송 주의)")
    p.add_argument("--out", default="",
                   help="HTML 미리보기를 저장할 경로")
    p.add_argument("--threshold", type=float, default=1.0,
                   help="'주목할 변동' 전월비 기준 %% (기본 1.0)")
    args = p.parse_args()

    if not os.getenv("ECOS_API_KEY"):
        print("[오류] ECOS_API_KEY가 설정되지 않았습니다.", file=sys.stderr)
        return 2

    try:
        client = ECOSClient()
    except Exception as e:
        print(f"[오류] ECOS 클라이언트 생성 실패: {e}", file=sys.stderr)
        return 2

    catalog = get_catalog(api_key=os.getenv("ECOS_API_KEY"))
    if catalog is None or len(catalog) == 0:
        print("[오류] ECOS 품목 카탈로그를 불러오지 못했습니다.", file=sys.stderr)
        return 2

    # dedup=True: 같은 품목이 여러 공정에 걸려 있어도 한 번만 조회한다.
    # 품목마다 개별 API 호출이 발생하므로 중복을 없애야 호출 수가 줄고
    # 리포트 표에 같은 품목이 두 번 나오지 않는다.
    items = get_all_items_flat(dedup=True)
    print(f"관심 품목 {len(items)}개 조회 중... (품목당 API 1회)")

    report = build_report(
        client, catalog, items,
        threshold=args.threshold,
        last_sent_period=os.getenv("LAST_SENT_PERIOD") or None,
    )

    print(f"기준 시점: {report['as_of']}")
    print(f"조회 성공: {len(report['rows'])}개 / 매칭 실패: {len(report['unresolved'])}개")
    if report["unresolved"]:
        print(f"  실패 품목: {', '.join(str(u) for u in report['unresolved'][:10])}")
    print(f"주목할 변동: {len(report['notable'])}개")

    subject = subject_line(report)
    html = render_html(report)
    text = render_text(report)

    if args.out:
        pathlib.Path(args.out).write_text(html, encoding="utf-8")
        print(f"미리보기 저장: {args.out}")

    if not report["should_send"] and not args.force:
        print(f"\n[발송 보류] {report['skip_reason']}")
        print("강제로 보내려면 --force 를 붙이세요.")
        return 0

    if not args.send:
        print("\n" + "=" * 60)
        print(text)
        print("=" * 60)
        print("\n[미리보기 모드] 메일을 발송하지 않았습니다. 실제 발송은 --send 를 붙이세요.")
        return 0

    cfg = SmtpConfig.from_env()
    missing = cfg.missing()
    if missing:
        print(f"[오류] SMTP 설정이 빠졌습니다: {', '.join(missing)}", file=sys.stderr)
        return 2

    print(f"\n발송 중... 수신자 {len(cfg.recipients)}명")
    try:
        send_email(subject, html, text, cfg)
    except Exception as e:
        print(f"[오류] 발송 실패: {e}", file=sys.stderr)
        return 1

    print(f"발송 완료: {subject}")
    # 다음 실행에서 중복 발송을 막으려면 이 값을 LAST_SENT_PERIOD로 넘겨야 한다
    print(f"LAST_SENT_PERIOD={report['as_of']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
