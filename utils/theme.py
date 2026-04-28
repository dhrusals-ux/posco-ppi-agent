"""
UI 테마 & 공통 CSS — POSCO 브랜드 컬러 기반
사용법:
    from utils.theme import inject_theme, POSCO_COLORS, plotly_template
    inject_theme()
"""
import streamlit as st
import plotly.graph_objects as go
import plotly.io as pio


# ─────────────────────────────────────────────
# 포스코 브랜드 컬러 팔레트
# ─────────────────────────────────────────────
POSCO_COLORS = {
    "primary": "#005EB8",       # 포스코 블루
    "primary_dark": "#003D7A",
    "primary_light": "#4A90D9",
    "accent": "#F29F05",        # 포스코 골드
    "accent_light": "#FFC857",
    "success": "#22C55E",
    "warning": "#F97316",
    "danger": "#EF4444",
    "neutral_50": "#F8FAFC",
    "neutral_100": "#F1F5F9",
    "neutral_200": "#E2E8F0",
    "neutral_500": "#64748B",
    "neutral_700": "#334155",
    "neutral_900": "#0F172A",
    "gradient_main": "linear-gradient(135deg, #005EB8 0%, #003D7A 100%)",
    "gradient_gold": "linear-gradient(135deg, #F29F05 0%, #D97706 100%)",
}

# 차트 시리즈 컬러 (다품목 비교용)
SERIES_COLORS = [
    "#005EB8", "#F29F05", "#22C55E", "#8B5CF6",
    "#EC4899", "#14B8A6", "#F43F5E", "#6366F1",
    "#EA580C", "#84CC16",
]


# ─────────────────────────────────────────────
# Plotly 공통 템플릿
# ─────────────────────────────────────────────
def plotly_template():
    """포스코 브랜드 Plotly 템플릿"""
    return dict(
        layout=go.Layout(
            font=dict(family="'Pretendard', 'Noto Sans KR', sans-serif", size=13, color="#334155"),
            title=dict(font=dict(size=18, color="#0F172A", family="'Pretendard', sans-serif")),
            plot_bgcolor="#FFFFFF",
            paper_bgcolor="#FFFFFF",
            colorway=SERIES_COLORS,
            xaxis=dict(
                gridcolor="#F1F5F9",
                linecolor="#E2E8F0",
                tickfont=dict(size=11, color="#64748B"),
                zerolinecolor="#E2E8F0",
            ),
            yaxis=dict(
                gridcolor="#F1F5F9",
                linecolor="#E2E8F0",
                tickfont=dict(size=11, color="#64748B"),
                zerolinecolor="#E2E8F0",
            ),
            legend=dict(
                bgcolor="rgba(255,255,255,0.9)",
                bordercolor="#E2E8F0",
                borderwidth=1,
                font=dict(size=11),
            ),
            hoverlabel=dict(
                bgcolor="#0F172A",
                font=dict(color="white", family="'Pretendard', sans-serif"),
            ),
            margin=dict(l=40, r=20, t=60, b=40),
        )
    )


pio.templates["posco"] = go.layout.Template(plotly_template())


# ─────────────────────────────────────────────
# Streamlit CSS 주입
# ─────────────────────────────────────────────
def inject_theme():
    """앱 전반에 포스코 브랜드 CSS 주입"""
    st.markdown(
        """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css" rel="stylesheet">

    <style>
    /* 전체 폰트 */
    html, body, [class*="css"], .stApp, .stMarkdown, .stText {
        font-family: 'Pretendard', 'Noto Sans KR', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    /* 헤더 그라디언트 */
    .posco-hero {
        background: linear-gradient(135deg, #005EB8 0%, #003D7A 100%);
        color: white;
        padding: 28px 32px;
        border-radius: 16px;
        margin-bottom: 20px;
        box-shadow: 0 10px 30px rgba(0, 94, 184, 0.2);
    }
    .posco-hero h1 {
        color: white !important;
        font-size: 28px !important;
        margin: 0 !important;
        font-weight: 700;
    }
    .posco-hero p {
        color: rgba(255,255,255,0.85) !important;
        margin: 8px 0 0 0 !important;
        font-size: 14px;
    }

    /* KPI 카드 */
    .kpi-card {
        background: white;
        border-radius: 14px;
        padding: 18px 20px;
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.06);
        border: 1px solid #E2E8F0;
        transition: all 0.25s ease;
        height: 100%;
    }
    .kpi-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 8px 24px rgba(0, 94, 184, 0.12);
        border-color: #005EB8;
    }
    .kpi-label {
        font-size: 12px;
        color: #64748B;
        font-weight: 500;
        letter-spacing: 0.3px;
        text-transform: uppercase;
        margin-bottom: 6px;
    }
    .kpi-value {
        font-size: 26px;
        font-weight: 700;
        color: #0F172A;
        line-height: 1.1;
    }
    .kpi-delta {
        font-size: 13px;
        font-weight: 600;
        margin-top: 4px;
    }
    .kpi-delta.up { color: #EF4444; }
    .kpi-delta.down { color: #22C55E; }
    .kpi-delta.neutral { color: #64748B; }
    .kpi-icon {
        font-size: 20px;
        float: right;
        opacity: 0.8;
    }

    /* 하이라이트 카드 (환산 결과 등) */
    .highlight-card {
        background: linear-gradient(135deg, #005EB8 0%, #003D7A 100%);
        color: white;
        border-radius: 16px;
        padding: 24px 28px;
        box-shadow: 0 10px 30px rgba(0, 94, 184, 0.25);
    }
    .highlight-card .kpi-label { color: rgba(255,255,255,0.8); }
    .highlight-card .kpi-value { color: white; font-size: 32px; }
    .highlight-card .kpi-delta { color: #FFC857; }

    /* 탭 스타일 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        border-bottom: 2px solid #F1F5F9;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 18px;
        font-weight: 600;
        color: #64748B;
        border-radius: 8px 8px 0 0;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        color: #005EB8 !important;
        background: #F0F7FF !important;
        border-bottom: 3px solid #005EB8 !important;
    }

    /* Primary 버튼 */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #005EB8 0%, #003D7A 100%);
        border: none;
        font-weight: 600;
        padding: 10px 24px;
        border-radius: 10px;
        box-shadow: 0 4px 12px rgba(0, 94, 184, 0.3);
        transition: all 0.2s;
    }
    .stButton > button[kind="primary"]:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 16px rgba(0, 94, 184, 0.4);
    }

    /* 정보 박스 */
    .stAlert {
        border-radius: 12px;
        border-left-width: 4px;
    }

    /* Divider 컬러 */
    hr { border-color: #E2E8F0 !important; }

    /* 사이드바 */
    [data-testid="stSidebar"] {
        background: #F8FAFC;
    }
    [data-testid="stSidebar"] .stMarkdown h3 {
        color: #005EB8;
        font-size: 15px;
        margin-top: 12px;
    }

    /* 메트릭 기본을 업그레이드 */
    [data-testid="stMetric"] {
        background: white;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 14px 18px;
        box-shadow: 0 2px 6px rgba(15, 23, 42, 0.04);
    }
    [data-testid="stMetricLabel"] {
        color: #64748B;
        font-weight: 500;
    }
    [data-testid="stMetricValue"] {
        color: #0F172A;
        font-weight: 700;
    }

    /* 섹션 타이틀 */
    .section-title {
        font-size: 18px;
        font-weight: 700;
        color: #0F172A;
        margin: 24px 0 12px 0;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .section-title::before {
        content: '';
        width: 4px;
        height: 20px;
        background: linear-gradient(135deg, #005EB8 0%, #F29F05 100%);
        border-radius: 2px;
    }

    /* Pulse (라이브 표시) */
    .pulse-dot {
        width: 8px;
        height: 8px;
        background: #22C55E;
        border-radius: 50%;
        display: inline-block;
        margin-right: 6px;
        animation: pulse 2s infinite;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(34,197,94,0.6); }
        50% { opacity: 0.7; box-shadow: 0 0 0 8px rgba(34,197,94,0); }
    }
    </style>
    """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────
# 헬퍼: KPI 카드 HTML 렌더러
# ─────────────────────────────────────────────
def kpi_card(label, value, delta=None, delta_type="neutral", icon="", highlight=False):
    """
    HTML 기반 KPI 카드 생성

    delta_type: 'up'(빨강↑) / 'down'(초록↓) / 'neutral'
    """
    klass = "highlight-card" if highlight else "kpi-card"
    delta_html = ""
    if delta:
        arrow = "▲" if delta_type == "up" else ("▼" if delta_type == "down" else "—")
        delta_html = f'<div class="kpi-delta {delta_type}">{arrow} {delta}</div>'
    icon_html = f'<span class="kpi-icon">{icon}</span>' if icon else ""
    return f"""
    <div class="{klass}">
        {icon_html}
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        {delta_html}
    </div>
    """


def hero_header(title, subtitle):
    """상단 그라디언트 헤더"""
    return f"""
    <div class="posco-hero">
        <h1>{title}</h1>
        <p>{subtitle}</p>
    </div>
    """


def section_title(text):
    """섹션 구분 타이틀"""
    return f'<div class="section-title">{text}</div>'


def live_badge(text="LIVE"):
    """실시간 표시 뱃지"""
    return f'<span class="pulse-dot"></span><span style="color:#22C55E;font-weight:600;font-size:12px;">{text}</span>'
