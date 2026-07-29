"""
월간 물가 동향 메일 리포트 (UI 비의존)

읽는 순서를 설계했다. 매달 50개 품목 표를 처음부터 읽는 사람은 없다.
  1) 요약 스트립  — 이번 달이 오른 달인지 내린 달인지 한 줄로
  2) 상승/하락 TOP — 실제로 궁금한 두 가지를 나란히
  3) 공정별 상세  — 담당 공정만 보면 되도록 그룹 분리, 전월비 큰 순 정렬
전월비는 막대로 함께 그린다. 숫자를 읽지 않고도 크기가 비교된다.

설계 판단
  - 기준 시점을 '현재월'로 가정하지 않고 실제 데이터에서 찾아낸다.
    ECOS 생산자물가지수는 익월 중하순에 발표되므로 현재월을 기준으로 잡으면
    매달 빈 리포트를 보내게 된다.
  - 발표가 갱신되지 않았으면 발송하지 않는다(should_send=False).
    같은 내용을 두 번 보내면 수신자가 리포트를 신뢰하지 않게 된다.
  - 매칭 실패 품목을 리포트에 명시한다. 조용히 빠뜨리면 '관심 품목 50개'라고
    적힌 리포트에 실제로는 40개만 담기는 일이 생긴다.
  - 상승을 적색, 하락을 녹색으로 쓴다. 주식과 반대인데 의도한 것이다 —
    투자비 관점에서 지수 상승은 비용 증가다.
  - 메일 HTML은 표 기반 레이아웃 + 인라인 스타일만 쓴다.
    Outlook은 flex/grid를 지원하지 않고 대부분의 클라이언트가 <style>을 제거한다.

발송은 이 모듈이 하지 않는다 — scripts/send_monthly_report.py가 명시적으로 호출한다.
"""
from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, formatdate
from typing import Dict, List, Optional

import pandas as pd

from utils.monitor import build_monitor

KST = timezone(timedelta(hours=9))

# 전월비 절대값이 이 값을 넘으면 '주목할 변동'으로 뽑는다
NOTABLE_MOM_THRESHOLD = 1.0

# 상승/하락 TOP에 각각 몇 개까지 보여줄지
TOP_N = 5

DISCLAIMER = (
    "본 리포트는 내부 투자비 추정·검토용이며, 「국가계약법」상 계약금액조정(물가변동) "
    "산식과 다르므로 공식 계약 근거로 사용할 수 없습니다."
)

# ── 색상 (utils/theme.py의 POSCO CI 실측값과 동일) ──
_C_TEXT = "#222222"
_C_MUTED = "#848484"
_C_SUB = "#555555"
_C_BLUE = "#005C9C"
_C_NAVY = "#022846"
_C_BORDER = "#E5E5E5"
_C_BG = "#F4F4F4"
_C_UP = "#B42318"     # 상승 = 적색 (비용 증가)
_C_DOWN = "#1B7F4B"   # 하락 = 녹색


# ─────────────────────────────────────────────
# 서식
# ─────────────────────────────────────────────
def _none(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v))


def _fmt_pct(v: Optional[float]) -> str:
    return "—" if _none(v) else f"{v:+.2f}%"


def _fmt_idx(v: Optional[float]) -> str:
    return "—" if _none(v) else f"{v:,.2f}"


def _fmt_period(p: Optional[str]) -> str:
    if not p or len(str(p)) < 6:
        return "—"
    p = str(p)
    return f"{p[:4]}년 {int(p[4:6])}월"


def _color(v: Optional[float]) -> str:
    if _none(v):
        return _C_MUTED
    if v > 0:
        return _C_UP
    if v < 0:
        return _C_DOWN
    return _C_MUTED


# ─────────────────────────────────────────────
# 리포트 데이터 구성
# ─────────────────────────────────────────────
def build_report(
    client,
    catalog: pd.DataFrame,
    items: List[Dict],
    months: int = 26,
    threshold: float = NOTABLE_MOM_THRESHOLD,
    last_sent_period: Optional[str] = None,
) -> Dict:
    """
    관심 품목의 최신 지수·전월비·전년동월비를 모아 리포트 데이터를 만든다.

    items : [{label, keywords, note, process}, ...] — process는 그룹 표시에 쓴다
    last_sent_period : 지난번에 보낸 기준 시점(YYYYMM). 같으면 should_send=False.
    """
    end = datetime.now(KST).strftime("%Y%m")
    start = (datetime.now(KST) - timedelta(days=31 * months)).strftime("%Y%m")

    mon = build_monitor(client, items, catalog, start, end)
    rows = mon.get("rows", [])
    unresolved = mon.get("unresolved", [])

    # build_monitor는 process를 넘겨주지 않으므로 label로 되짚어 붙인다
    # (monitor.py는 앱과 공용이라 건드리지 않는다)
    proc_of = {it.get("label"): it.get("process", "") for it in items}
    for r in rows:
        r["process"] = proc_of.get(r.get("label"), "")

    # 기준 시점은 실제 데이터에서 찾는다 (발표 지연 때문에 현재월로 가정할 수 없다)
    periods = [str(r.get("period")) for r in rows if r.get("period")]
    as_of = max(periods) if periods else None

    moms = [r["mom"] for r in rows if not _none(r.get("mom"))]
    yoys = [r["yoy"] for r in rows if not _none(r.get("yoy"))]

    summary = {
        "mom_avg": (sum(moms) / len(moms)) if moms else None,
        "yoy_avg": (sum(yoys) / len(yoys)) if yoys else None,
        "up": sum(1 for v in moms if v > 0),
        "down": sum(1 for v in moms if v < 0),
        "flat": sum(1 for v in moms if v == 0),
        "mom_count": len(moms),
    }

    ranked = sorted([r for r in rows if not _none(r.get("mom"))], key=lambda r: -r["mom"])
    top_up = [r for r in ranked if r["mom"] > 0][:TOP_N]
    top_down = [r for r in reversed(ranked) if r["mom"] < 0][:TOP_N]

    notable = sorted(
        [r for r in rows if not _none(r.get("mom")) and abs(r["mom"]) >= threshold],
        key=lambda r: -abs(r["mom"]),
    )

    # 공정별 그룹 — items에 나온 순서를 유지한다 (제선→제강→…)
    order, seen = [], set()
    for it in items:
        p = it.get("process", "")
        if p and p not in seen:
            seen.add(p)
            order.append(p)
    groups = [
        (p, sorted([r for r in rows if r.get("process") == p],
                   key=lambda r: (-(r["mom"]) if not _none(r.get("mom")) else 1e9)))
        for p in order
    ]
    groups = [(p, rs) for p, rs in groups if rs]

    should_send, skip_reason = True, ""
    if not rows:
        should_send = False
        skip_reason = "조회된 품목이 없습니다 (인증키·네트워크 확인 필요)."
    elif as_of is None:
        should_send = False
        skip_reason = "기준 시점을 판별할 수 없습니다."
    elif last_sent_period and str(last_sent_period) >= as_of:
        should_send = False
        skip_reason = (
            f"신규 발표가 없습니다 (최신 {as_of}, 지난 발송 {last_sent_period}). "
            "같은 내용을 중복 발송하지 않습니다."
        )

    return {
        "as_of": as_of,
        "rows": rows,
        "groups": groups,
        "summary": summary,
        "top_up": top_up,
        "top_down": top_down,
        "notable": notable,
        "threshold": threshold,
        "unresolved": unresolved,
        "requested_count": len(items),
        "generated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "should_send": should_send,
        "skip_reason": skip_reason,
    }


def subject_line(report: Dict) -> str:
    s = report.get("summary") or {}
    avg = s.get("mom_avg")
    tail = f" (전월비 평균 {avg:+.2f}%)" if not _none(avg) else ""
    return f"[투자비 물가동향] {_fmt_period(report.get('as_of'))} 기준{tail}"


# ─────────────────────────────────────────────
# HTML 렌더링
# ─────────────────────────────────────────────
def _bar(mom: Optional[float], max_abs: float, width_px: int = 54) -> str:
    """
    전월비 막대. 표 기반 + bgcolor라 Outlook에서도 그려진다.
    숫자를 읽지 않고도 어느 품목이 크게 움직였는지 비교된다.
    """
    if _none(mom) or not max_abs:
        return ""
    w = max(2, int(round(abs(mom) / max_abs * width_px)))
    return (
        f'<table cellpadding="0" cellspacing="0" border="0" '
        f'style="border-collapse:collapse;"><tr>'
        f'<td width="{w}" height="7" bgcolor="{_color(mom)}" '
        f'style="width:{w}px;height:7px;background:{_color(mom)};font-size:0;line-height:0;">'
        f"&nbsp;</td></tr></table>"
    )


def _summary_strip(report: Dict) -> str:
    s = report.get("summary") or {}
    tiles = [
        ("전월비 평균", _fmt_pct(s.get("mom_avg")), _color(s.get("mom_avg"))),
        ("전년동월비 평균", _fmt_pct(s.get("yoy_avg")), _color(s.get("yoy_avg"))),
        ("상승", f"{s.get('up', 0)}개", _C_UP),
        ("하락", f"{s.get('down', 0)}개", _C_DOWN),
    ]
    cells = "".join(
        f'<td width="25%" style="width:25%;padding:11px 12px;border-left:1px solid {_C_BORDER};">'
        f'<div style="font-size:11px;color:{_C_MUTED};margin-bottom:3px;">{label}</div>'
        f'<div style="font-size:18px;font-weight:700;color:{color};'
        f'font-variant-numeric:tabular-nums;">{value}</div></td>'
        for label, value, color in tiles
    )
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="border-collapse:collapse;border:1px solid {_C_BORDER};'
        f'border-left:none;background:#FFFFFF;margin:0 0 20px;">'
        f"<tr>{cells}</tr></table>"
    )


def _top_list(title: str, rows: List[Dict], accent: str) -> str:
    if not rows:
        body = f'<div style="font-size:12px;color:{_C_MUTED};padding:4px 0;">해당 없음</div>'
    else:
        body = "".join(
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="border-collapse:collapse;"><tr>'
            f'<td style="padding:4px 0;font-size:13px;color:{_C_TEXT};">{r.get("label","")}'
            f'<span style="color:{_C_MUTED};font-size:11px;"> · {r.get("process","")}</span></td>'
            f'<td align="right" style="padding:4px 0;font-size:13px;font-weight:700;'
            f'color:{_color(r.get("mom"))};font-variant-numeric:tabular-nums;'
            f'white-space:nowrap;">{_fmt_pct(r.get("mom"))}</td>'
            f"</tr></table>"
            for r in rows
        )
    return (
        f'<td width="50%" valign="top" style="width:50%;padding:0 10px;">'
        f'<div style="font-size:12px;font-weight:700;color:{accent};'
        f'padding-bottom:6px;border-bottom:2px solid {accent};margin-bottom:6px;">{title}</div>'
        f"{body}</td>"
    )


def _detail_table(report: Dict) -> str:
    groups = report.get("groups") or []
    all_moms = [abs(r["mom"]) for r in report.get("rows", []) if not _none(r.get("mom"))]
    max_abs = max(all_moms) if all_moms else 0.0

    def th(t, align="left", width=""):
        w = f'width="{width}" ' if width else ""
        return (
            f'<th {w}align="{align}" style="padding:7px 9px;background:{_C_BG};'
            f"border-top:1px solid #DDDDDD;border-bottom:1px solid #DDDDDD;"
            f'text-align:{align};color:{_C_SUB};font-weight:500;font-size:11px;">{t}</th>'
        )

    out = [
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="border-collapse:collapse;">',
        "<tr>",
        th("품목"), th("ECOS 품목명"), th("지수", "right", "62"),
        th("전월비", "right", "64"), th("", "left", "58"), th("전년동월비", "right", "74"),
        "</tr>",
    ]

    for proc, rows in groups:
        out.append(
            f'<tr><td colspan="6" style="padding:10px 9px 5px;font-size:12px;'
            f'font-weight:700;color:{_C_NAVY};border-bottom:1px solid {_C_BORDER};">'
            f'{proc} <span style="color:{_C_MUTED};font-weight:400;">({len(rows)})</span>'
            f"</td></tr>"
        )
        for r in rows:
            td = (
                f'<td style="padding:6px 9px;border-bottom:1px solid #F0F0F0;'
                f'font-size:12.5px;color:{_C_TEXT};">{r.get("label","")}</td>'
                f'<td style="padding:6px 9px;border-bottom:1px solid #F0F0F0;'
                f'font-size:11px;color:{_C_MUTED};">{r.get("ecos_name","")}</td>'
                f'<td align="right" style="padding:6px 9px;border-bottom:1px solid #F0F0F0;'
                f'font-size:12.5px;color:{_C_TEXT};font-variant-numeric:tabular-nums;'
                f'white-space:nowrap;">{_fmt_idx(r.get("latest"))}</td>'
                f'<td align="right" style="padding:6px 9px;border-bottom:1px solid #F0F0F0;'
                f'font-size:12.5px;font-weight:700;color:{_color(r.get("mom"))};'
                f'font-variant-numeric:tabular-nums;white-space:nowrap;">'
                f'{_fmt_pct(r.get("mom"))}</td>'
                f'<td style="padding:6px 9px;border-bottom:1px solid #F0F0F0;">'
                f'{_bar(r.get("mom"), max_abs)}</td>'
                f'<td align="right" style="padding:6px 9px;border-bottom:1px solid #F0F0F0;'
                f'font-size:12.5px;color:{_color(r.get("yoy"))};'
                f'font-variant-numeric:tabular-nums;white-space:nowrap;">'
                f'{_fmt_pct(r.get("yoy"))}</td>'
            )
            out.append(f"<tr>{td}</tr>")

    out.append("</table>")
    return "".join(out)


def render_html(report: Dict) -> str:
    """메일 본문 HTML. 표 기반 레이아웃 + 인라인 스타일만 사용한다."""
    as_of = _fmt_period(report.get("as_of"))
    rows = report.get("rows", [])
    unresolved = report.get("unresolved", [])
    thr = report.get("threshold", NOTABLE_MOM_THRESHOLD)

    quality = ""
    if unresolved:
        names = ", ".join(str(u) for u in unresolved[:12])
        more = f" 외 {len(unresolved) - 12}건" if len(unresolved) > 12 else ""
        quality = (
            f'<p style="font-size:11.5px;color:{_C_UP};margin:12px 0 0;line-height:1.6;">'
            f"※ 관심 품목 {report.get('requested_count', 0)}개 중 {len(unresolved)}개는 "
            f"ECOS 품목 매칭에 실패해 이 리포트에서 빠졌습니다: {names}{more}</p>"
        )

    return (
        f'<div style="font-family:\'Malgun Gothic\',\'Apple SD Gothic Neo\',sans-serif;'
        f'max-width:760px;margin:0 auto;padding:0 0 24px;color:{_C_TEXT};">'

        # 헤더
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="border-collapse:collapse;border-top:3px solid {_C_BLUE};'
        f'border-bottom:1px solid {_C_BORDER};margin-bottom:18px;"><tr>'
        f'<td style="padding:17px 0 15px;">'
        f'<div style="font-size:19px;font-weight:700;color:{_C_NAVY};">'
        f"투자비 물가동향 월간 리포트</div>"
        f'<div style="font-size:12.5px;color:{_C_SUB};margin-top:5px;">'
        f"<b>{as_of}</b> 기준 · 한국은행 ECOS 생산자물가지수(2020=100) · "
        f"관심 품목 {len(rows)}개</div>"
        f"</td></tr></table>"

        # 요약 스트립
        f"{_summary_strip(report)}"

        # 상승 / 하락 TOP
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="border-collapse:collapse;margin:0 0 22px;"><tr>'
        f'{_top_list(f"상승 상위 {TOP_N}", report.get("top_up", []), _C_UP)}'
        f'{_top_list(f"하락 상위 {TOP_N}", report.get("top_down", []), _C_DOWN)}'
        f"</tr></table>"

        # 공정별 상세
        f'<div style="font-size:13.5px;font-weight:700;color:{_C_NAVY};margin:0 0 8px;">'
        f"공정별 상세 <span style=\"font-size:11px;color:{_C_MUTED};font-weight:400;\">"
        f"· 전월비 큰 순 · 막대는 전월비 크기</span></div>"
        f"{_detail_table(report)}"
        f"{quality}"

        # 푸터
        f'<p style="font-size:11px;color:{_C_MUTED};margin:22px 0 0;padding-top:13px;'
        f'border-top:1px solid {_C_BORDER};line-height:1.7;">'
        f"주목 기준: 전월비 절대값 {thr:.1f}% 이상 · "
        f"전년동월비는 정확히 12개월 전 같은 달 데이터가 있을 때만 표시<br>"
        f"생성 시각 {report.get('generated_at', '')} · POSCO 투자엔지니어링실<br>"
        f'<span style="color:{_C_UP};">{DISCLAIMER}</span></p>'
        f"</div>"
    )


# ─────────────────────────────────────────────
# 텍스트 렌더링 (HTML을 못 읽는 클라이언트용)
# ─────────────────────────────────────────────
def render_text(report: Dict) -> str:
    s = report.get("summary") or {}
    lines = [
        "투자비 물가동향 월간 리포트",
        f"{_fmt_period(report.get('as_of'))} 기준 · 한국은행 ECOS 생산자물가지수(2020=100)",
        "",
        f"[요약] 전월비 평균 {_fmt_pct(s.get('mom_avg'))} · "
        f"전년동월비 평균 {_fmt_pct(s.get('yoy_avg'))} · "
        f"상승 {s.get('up', 0)} / 하락 {s.get('down', 0)} / 보합 {s.get('flat', 0)}",
        "",
    ]

    for title, key in (("상승 상위", "top_up"), ("하락 상위", "top_down")):
        rs = report.get(key, [])
        lines.append(f"[{title} {TOP_N}]")
        if rs:
            for r in rs:
                lines.append(
                    f"  {_fmt_pct(r.get('mom')):>8}  {r.get('label','')} ({r.get('process','')})"
                )
        else:
            lines.append("  해당 없음")
        lines.append("")

    lines.append("[공정별 상세] 전월비 큰 순")
    for proc, rows in report.get("groups", []):
        lines.append(f"\n  ── {proc} ({len(rows)}) ──")
        lines.append(f"  {'품목':20} {'지수':>9} {'전월비':>9} {'전년동월비':>11}")
        for r in rows:
            lines.append(
                f"  {str(r.get('label',''))[:18]:20} {_fmt_idx(r.get('latest')):>9} "
                f"{_fmt_pct(r.get('mom')):>9} {_fmt_pct(r.get('yoy')):>11}"
            )

    unresolved = report.get("unresolved", [])
    if unresolved:
        lines += [
            "",
            f"※ 관심 품목 {report.get('requested_count', 0)}개 중 {len(unresolved)}개는 "
            f"ECOS 품목 매칭에 실패해 빠졌습니다:",
            f"  {', '.join(str(u) for u in unresolved[:12])}",
        ]

    lines += [
        "",
        f"주목 기준: 전월비 절대값 {report.get('threshold', NOTABLE_MOM_THRESHOLD):.1f}% 이상",
        "전년동월비는 정확히 12개월 전 같은 달 데이터가 있을 때만 표시",
        f"생성 시각 {report.get('generated_at','')} · POSCO 투자엔지니어링실",
        DISCLAIMER,
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────
# SMTP 발송
# ─────────────────────────────────────────────
@dataclass
class SmtpConfig:
    host: str = ""
    port: int = 587
    user: str = ""
    password: str = field(default="", repr=False)   # repr에서 제외 — 로그 유출 방지
    sender: str = ""
    sender_name: str = "투자비 물가보정 시스템"
    recipients: List[str] = field(default_factory=list)
    use_starttls: bool = True

    @classmethod
    def from_env(cls) -> "SmtpConfig":
        raw = os.getenv("REPORT_RECIPIENTS", "")
        return cls(
            host=os.getenv("SMTP_HOST", "").strip(),
            port=int(os.getenv("SMTP_PORT", "587")),
            user=os.getenv("SMTP_USER", "").strip(),
            password=os.getenv("SMTP_PASSWORD", ""),
            sender=(os.getenv("SMTP_FROM") or os.getenv("SMTP_USER", "")).strip(),
            sender_name=os.getenv("SMTP_FROM_NAME", "투자비 물가보정 시스템"),
            recipients=[a.strip() for a in raw.split(",") if a.strip()],
            use_starttls=os.getenv("SMTP_STARTTLS", "1") not in ("0", "false", "False"),
        )

    def missing(self) -> List[str]:
        """설정이 빠진 항목. 발송 전에 확인해 명확히 실패시킨다."""
        out = []
        if not self.host:
            out.append("SMTP_HOST")
        if not self.user:
            out.append("SMTP_USER")
        if not self.password:
            out.append("SMTP_PASSWORD")
        if not self.sender:
            out.append("SMTP_FROM (또는 SMTP_USER)")
        if not self.recipients:
            out.append("REPORT_RECIPIENTS")
        return out


def build_message(subject: str, html: str, text: str, cfg: SmtpConfig) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((cfg.sender_name, cfg.sender))
    msg["To"] = ", ".join(cfg.recipients)
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return msg


def send_email(subject: str, html: str, text: str, cfg: SmtpConfig) -> None:
    """SMTP로 발송한다. 설정이 빠져 있으면 조용히 넘기지 않고 예외를 던진다."""
    missing = cfg.missing()
    if missing:
        raise RuntimeError(
            "SMTP 설정이 빠졌습니다: " + ", ".join(missing)
            + " — 환경변수(또는 GitHub Secrets)에 등록하세요."
        )

    msg = build_message(subject, html, text, cfg)
    context = ssl.create_default_context()

    if cfg.port == 465:
        with smtplib.SMTP_SSL(cfg.host, cfg.port, context=context, timeout=30) as s:
            s.login(cfg.user, cfg.password)
            s.send_message(msg)
        return

    with smtplib.SMTP(cfg.host, cfg.port, timeout=30) as s:
        s.ehlo()
        if cfg.use_starttls:
            s.starttls(context=context)
            s.ehlo()
        if cfg.user and cfg.password:
            s.login(cfg.user, cfg.password)
        s.send_message(msg)
