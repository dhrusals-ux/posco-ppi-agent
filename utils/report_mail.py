"""
월간 물가 동향 메일 리포트 (UI 비의존)

설계 판단
  - 기준 시점을 '현재월'로 가정하지 않고 실제 데이터에서 찾아낸다.
    ECOS 생산자물가지수는 익월 중하순에 발표되고 건설공사비지수는 1~2개월
    지연되므로, 현재월을 기준으로 잡으면 매달 빈 리포트를 보내게 된다.
  - 발표가 갱신되지 않았으면 발송하지 않는다(should_send=False).
    같은 내용을 두 번 보내면 수신자가 리포트를 신뢰하지 않게 된다.
  - 매칭 실패 품목 수를 리포트에 명시한다. 조용히 빠뜨리면 '관심 품목 24개'라고
    적힌 리포트에 실제로는 18개만 담기는 일이 생긴다.
  - 메일 HTML은 인라인 스타일만 쓴다. 대부분의 메일 클라이언트가 <style>을 제거한다.

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

DISCLAIMER = (
    "본 리포트는 내부 투자비 추정·검토용이며, 「국가계약법」상 계약금액조정(물가변동) "
    "산식과 다르므로 공식 계약 근거로 사용할 수 없습니다."
)


# ─────────────────────────────────────────────
# 리포트 데이터 구성
# ─────────────────────────────────────────────
def _fmt_pct(v: Optional[float]) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{v:+.2f}%"


def _fmt_idx(v: Optional[float]) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{v:,.2f}"


def _fmt_period(p: Optional[str]) -> str:
    if not p or len(str(p)) < 6:
        return "—"
    p = str(p)
    return f"{p[:4]}년 {int(p[4:6])}월"


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

    last_sent_period : 지난번에 보낸 기준 시점(YYYYMM). 같으면 should_send=False.

    Returns dict {
      as_of, rows, notable, unresolved, generated_at, should_send, skip_reason
    }
    """
    end = datetime.now(KST).strftime("%Y%m")
    start_dt = datetime.now(KST) - timedelta(days=31 * months)
    start = start_dt.strftime("%Y%m")

    mon = build_monitor(client, items, catalog, start, end)
    rows = mon.get("rows", [])
    unresolved = mon.get("unresolved", [])

    # 기준 시점은 실제 데이터에서 찾는다 (발표 지연 때문에 현재월로 가정할 수 없다)
    periods = [str(r.get("period")) for r in rows if r.get("period")]
    as_of = max(periods) if periods else None

    notable = sorted(
        [r for r in rows if r.get("mom") is not None and abs(r["mom"]) >= threshold],
        key=lambda r: -abs(r["mom"]),
    )

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
        "notable": notable,
        "unresolved": unresolved,
        "requested_count": len(items),
        "generated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "should_send": should_send,
        "skip_reason": skip_reason,
    }


def subject_line(report: Dict) -> str:
    return f"[투자비 물가동향] {_fmt_period(report.get('as_of'))} 기준 설비 품목 지수"


# ─────────────────────────────────────────────
# 렌더링
# ─────────────────────────────────────────────
_C_TEXT = "#222222"
_C_MUTED = "#848484"
_C_BLUE = "#005C9C"
_C_NAVY = "#022846"
_C_BORDER = "#E5E5E5"
_C_UP = "#B42318"     # 상승 = 적색 (비용 증가)
_C_DOWN = "#1B7F4B"   # 하락 = 녹색


def _color(v: Optional[float]) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return _C_MUTED
    if v > 0:
        return _C_UP
    if v < 0:
        return _C_DOWN
    return _C_MUTED


def render_html(report: Dict) -> str:
    """메일 본문 HTML. 인라인 스타일만 사용한다 (메일 클라이언트가 <style>을 제거함)."""
    as_of = _fmt_period(report.get("as_of"))
    rows = report.get("rows", [])
    notable = report.get("notable", [])
    unresolved = report.get("unresolved", [])

    def td(content, align="left", color=_C_TEXT, weight="400", size="13px"):
        return (
            f'<td style="padding:7px 10px;border-bottom:1px solid {_C_BORDER};'
            f'text-align:{align};color:{color};font-weight:{weight};font-size:{size};'
            f'font-variant-numeric:tabular-nums;">{content}</td>'
        )

    def th(content, align="left"):
        return (
            f'<th style="padding:7px 10px;background:#F4F4F4;border-bottom:1px solid #DDDDDD;'
            f'text-align:{align};color:#555555;font-weight:500;font-size:12px;">{content}</th>'
        )

    # 주목할 변동
    notable_html = ""
    if notable:
        lis = "".join(
            f'<li style="margin:4px 0;font-size:13px;color:{_C_TEXT};">'
            f'{r.get("label","")} '
            f'<span style="color:{_color(r.get("mom"))};font-weight:500;">'
            f'{_fmt_pct(r.get("mom"))}</span>'
            f'<span style="color:{_C_MUTED};"> (전년동월비 {_fmt_pct(r.get("yoy"))})</span>'
            f"</li>"
            for r in notable[:8]
        )
        notable_html = (
            f'<div style="margin:0 0 22px;padding:14px 16px;background:#FAFAFA;'
            f'border-left:3px solid {_C_BLUE};">'
            f'<div style="font-size:13px;font-weight:500;color:{_C_NAVY};margin-bottom:8px;">'
            f"전월비 {NOTABLE_MOM_THRESHOLD:.1f}% 이상 변동한 품목</div>"
            f'<ul style="margin:0;padding-left:18px;">{lis}</ul></div>'
        )
    else:
        notable_html = (
            f'<p style="font-size:13px;color:{_C_MUTED};margin:0 0 22px;">'
            f"전월비 {NOTABLE_MOM_THRESHOLD:.1f}% 이상 변동한 품목이 없습니다.</p>"
        )

    body_rows = "".join(
        "<tr>"
        + td(r.get("label", ""))
        + td(r.get("ecos_name", ""), color=_C_MUTED, size="12px")
        + td(_fmt_idx(r.get("latest")), align="right")
        + td(_fmt_pct(r.get("mom")), align="right", color=_color(r.get("mom")), weight="500")
        + td(_fmt_pct(r.get("yoy")), align="right", color=_color(r.get("yoy")), weight="500")
        + "</tr>"
        for r in rows
    )

    # 데이터 품질 고지 — 빠진 품목을 조용히 넘기지 않는다
    quality_html = ""
    if unresolved:
        names = ", ".join(str(u) for u in unresolved[:10])
        more = f" 외 {len(unresolved) - 10}건" if len(unresolved) > 10 else ""
        quality_html = (
            f'<p style="font-size:12px;color:{_C_UP};margin:14px 0 0;">'
            f"※ 관심 품목 {report.get('requested_count', 0)}개 중 "
            f"{len(unresolved)}개는 ECOS 품목 매칭에 실패해 이 리포트에서 빠졌습니다: "
            f"{names}{more}</p>"
        )

    return (
        f'<div style="font-family:\'Malgun Gothic\',\'Apple SD Gothic Neo\',sans-serif;'
        f'max-width:720px;margin:0 auto;padding:0 0 24px;color:{_C_TEXT};">'
        f'<div style="border-top:3px solid {_C_BLUE};border-bottom:1px solid {_C_BORDER};'
        f'padding:18px 0 16px;margin-bottom:22px;">'
        f'<div style="font-size:19px;font-weight:700;color:{_C_NAVY};">'
        f"투자비 물가동향 월간 리포트</div>"
        f'<div style="font-size:13px;color:#555555;margin-top:6px;">'
        f"{as_of} 기준 · 한국은행 ECOS 생산자물가지수(2020=100)</div></div>"
        f"{notable_html}"
        f'<div style="font-size:14px;font-weight:700;color:{_C_NAVY};margin:0 0 10px;">'
        f"관심 품목 현황 ({len(rows)}개)</div>"
        f'<table style="width:100%;border-collapse:collapse;">'
        f"<thead><tr>{th('품목')}{th('ECOS 품목명')}{th('지수', 'right')}"
        f"{th('전월비', 'right')}{th('전년동월비', 'right')}</tr></thead>"
        f"<tbody>{body_rows}</tbody></table>"
        f"{quality_html}"
        f'<p style="font-size:11px;color:{_C_MUTED};margin:24px 0 0;padding-top:14px;'
        f'border-top:1px solid {_C_BORDER};line-height:1.7;">'
        f"생성 시각 {report.get('generated_at', '')} · POSCO 투자엔지니어링실<br>"
        f'<span style="color:{_C_UP};">{DISCLAIMER}</span></p>'
        f"</div>"
    )


def render_text(report: Dict) -> str:
    """HTML을 못 읽는 클라이언트용 대체 본문"""
    lines = [
        "투자비 물가동향 월간 리포트",
        f"{_fmt_period(report.get('as_of'))} 기준 · 한국은행 ECOS 생산자물가지수(2020=100)",
        "",
    ]
    notable = report.get("notable", [])
    if notable:
        lines.append(f"[전월비 {NOTABLE_MOM_THRESHOLD:.1f}% 이상 변동]")
        for r in notable[:8]:
            lines.append(
                f"  - {r.get('label','')}: 전월비 {_fmt_pct(r.get('mom'))}, "
                f"전년동월비 {_fmt_pct(r.get('yoy'))}"
            )
    else:
        lines.append(f"[전월비 {NOTABLE_MOM_THRESHOLD:.1f}% 이상 변동한 품목 없음]")
    lines.append("")

    rows = report.get("rows", [])
    lines.append(f"[관심 품목 현황 {len(rows)}개]")
    lines.append(f"  {'품목':22} {'지수':>10} {'전월비':>9} {'전년동월비':>10}")
    for r in rows:
        lines.append(
            f"  {str(r.get('label',''))[:20]:22} {_fmt_idx(r.get('latest')):>10} "
            f"{_fmt_pct(r.get('mom')):>9} {_fmt_pct(r.get('yoy')):>10}"
        )

    unresolved = report.get("unresolved", [])
    if unresolved:
        lines += [
            "",
            f"※ 관심 품목 {report.get('requested_count', 0)}개 중 {len(unresolved)}개는 "
            f"ECOS 품목 매칭에 실패해 빠졌습니다: {', '.join(str(u) for u in unresolved[:10])}",
        ]

    lines += ["", f"생성 시각 {report.get('generated_at','')} · POSCO 투자엔지니어링실", DISCLAIMER]
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
    """
    SMTP로 발송한다. 설정이 빠져 있으면 조용히 넘기지 않고 예외를 던진다.
    """
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
