"""
PDF / Excel 보고서 생성 유틸
- 환산 결과를 전문적인 PDF 리포트로
- 다품목 비교 데이터를 Excel로
"""
from __future__ import annotations
import io
from datetime import datetime
from typing import Optional

import pandas as pd


# ─────────────────────────────────────────────
# Excel
# ─────────────────────────────────────────────
def to_excel_bytes(sheets: dict) -> bytes:
    """
    sheets = {"시트명": DataFrame, ...}
    반환: xlsx 바이너리
    """
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        wb = writer.book
        header_fmt = wb.add_format({
            "bold": True, "bg_color": "#005EB8", "font_color": "white",
            "border": 1, "align": "center", "valign": "vcenter",
        })
        num_fmt = wb.add_format({"num_format": "#,##0.00"})

        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
            ws = writer.sheets[sheet_name[:31]]
            for col_idx, col in enumerate(df.columns):
                ws.write(0, col_idx, col, header_fmt)
                max_len = max(df[col].astype(str).map(len).max() if len(df) else 0, len(str(col))) + 2
                ws.set_column(col_idx, col_idx, min(max_len, 30))
            ws.freeze_panes(1, 0)

    buf.seek(0)
    return buf.read()


# ─────────────────────────────────────────────
# PDF (reportlab)
# ─────────────────────────────────────────────
def generate_pdf_report(
    title: str,
    summary: dict,
    body_text: str = "",
    table_df: Optional[pd.DataFrame] = None,
) -> bytes:
    """
    환산 결과 PDF 리포트 생성

    summary: {"원금": "800억", "환산금액": "983억", ...}
    body_text: 자유 텍스트 (Markdown 아님, 일반 텍스트)
    table_df: 첨부 표
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os as _os

    # 한글 폰트 등록 (시스템 폰트 탐색, 없으면 Helvetica 사용)
    font_name = "Helvetica"
    for candidate in [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "C:/Windows/Fonts/malgun.ttf",
    ]:
        if _os.path.exists(candidate):
            try:
                pdfmetrics.registerFont(TTFont("KorFont", candidate))
                font_name = "KorFont"
                break
            except Exception:
                pass

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        leftMargin=2 * cm, rightMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title", parent=styles["Heading1"], fontName=font_name,
        fontSize=20, textColor=colors.HexColor("#005EB8"),
        spaceAfter=8, alignment=0,
    )
    subtitle_style = ParagraphStyle(
        "Sub", parent=styles["Normal"], fontName=font_name,
        fontSize=10, textColor=colors.HexColor("#64748B"), spaceAfter=20,
    )
    h2_style = ParagraphStyle(
        "H2", parent=styles["Heading2"], fontName=font_name,
        fontSize=14, textColor=colors.HexColor("#003D7A"),
        spaceBefore=14, spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"], fontName=font_name,
        fontSize=10, leading=15, textColor=colors.HexColor("#334155"),
        spaceAfter=8,
    )

    story = []
    story.append(Paragraph(title, title_style))
    story.append(Paragraph(
        f"POSCO 투자엔지니어링실 · 생성 일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        subtitle_style,
    ))

    # 요약 테이블
    if summary:
        story.append(Paragraph("📊 핵심 지표", h2_style))
        tbl_data = [["항목", "값"]]
        for k, v in summary.items():
            tbl_data.append([str(k), str(v)])
        tbl = Table(tbl_data, colWidths=[6 * cm, 10 * cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#005EB8")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.HexColor("#F8FAFC"), colors.white]),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("ALIGN", (0, 1), (0, -1), "LEFT"),
            ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ]))
        story.append(tbl)

    # 본문
    if body_text:
        story.append(Paragraph("📝 분석 내용", h2_style))
        for line in body_text.split("\n"):
            line = line.strip()
            if line:
                # Markdown 굵은 기호 정리
                line = line.replace("**", "").replace("###", "").replace("##", "").replace("#", "")
                story.append(Paragraph(line, body_style))

    # 데이터 표
    if table_df is not None and len(table_df) > 0:
        story.append(PageBreak())
        story.append(Paragraph("📋 상세 데이터", h2_style))
        data = [list(table_df.columns)] + table_df.astype(str).values.tolist()
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#005EB8")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.HexColor("#F8FAFC"), colors.white]),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(t)

    story.append(Spacer(1, 20))
    footer = ParagraphStyle(
        "Footer", parent=body_style, fontSize=8,
        textColor=colors.HexColor("#94A3B8"), alignment=1,
    )
    story.append(Paragraph(
        "한국은행 ECOS API 기반 · POSCO 투자엔지니어링실 교육용 데모",
        footer,
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()
