"""
UI 테마 & 공통 CSS — POSCO CI 기반 (사내 정식 시스템 톤)

팔레트·서체는 posco.co.kr에서 실제 사용 중인 값을 측정해 맞췄다.
추측한 브랜드 컬러를 쓰면 '포스코처럼 만든 것'이 되고 실제 CI와 어긋난다.

  블루      #005C9C   (사이트 본문 링크·강조에 실제 사용)
  딥네이비  #022846 / #1C3C52
  스틸그레이 #6F899A
  본문      #222222   (사이트에서 압도적으로 많이 쓰이는 텍스트 색)
  서체      Metropolis → Noto Sans KR → Apple SD Gothic Neo → Malgun Gothic

설계 방침 (기존 테마에서 의도적으로 걷어낸 것):
  - 그라디언트 전면 제거. 포스코 사이트는 평면이다.
    파랑↔골드 그라디언트는 CI에 없는 조합이었다.
  - 골드(#F29F05) 강조 제거. 실제 사이트 주요 색상에 등장하지 않는다.
  - 큰 라운딩(16px)·큰 그림자·hover 부양 효과 제거 → 소비자 대시보드 문법이다.
  - 숫자에 tabular-nums 적용. 금액 도구에서 자리 안 맞는 건 실제 결함이다.
  - 맥박 애니메이션 제거. 검토 도구에서 시선을 빼앗는다.

사용법:
    from utils.theme import inject_theme, POSCO_COLORS, plotly_template
    inject_theme()
"""
import streamlit as st
import plotly.graph_objects as go
import plotly.io as pio


# ─────────────────────────────────────────────
# 팔레트 (posco.co.kr 실측)
# ─────────────────────────────────────────────
POSCO_COLORS = {
    "primary": "#005C9C",        # 포스코 블루 (실측)
    "primary_dark": "#022846",   # 딥 네이비
    "primary_mid": "#1C3C52",
    "primary_light": "#E8F1F8",  # 블루 최연 틴트 (선택 상태 배경)
    "steel": "#6F899A",          # 스틸 블루그레이
    "steel_light": "#98ACB8",

    # 상태색 — 코퍼레이트 팔레트에 맞게 채도를 낮춰 사용
    "success": "#1B7F4B",
    "warning": "#B26A00",
    "danger": "#B42318",

    # 중립
    "neutral_50": "#FAFAFA",
    "neutral_100": "#F4F4F4",    # 실측 배경 그레이
    "neutral_200": "#E5E5E5",
    "neutral_300": "#DDDDDD",
    "neutral_500": "#848484",    # 실측 보조 텍스트
    "neutral_700": "#555555",
    "neutral_900": "#222222",    # 실측 본문

    # 하위 호환 (기존 코드가 참조할 수 있음)
    "accent": "#005C9C",
    "accent_light": "#6F899A",
    "gradient_main": "#022846",
    "gradient_gold": "#005C9C",
}

# 차트 시리즈 — 블루·네이비·스틸 계열을 축으로, 구분용 색을 최소한만 섞는다
SERIES_COLORS = [
    "#005C9C", "#022846", "#6F899A", "#1B7F4B",
    "#B26A00", "#5B4C8C", "#8C5B5B", "#3E7C8C",
    "#7C8C3E", "#B42318",
]

FONT_STACK = (
    "'Metropolis', 'Noto Sans KR', 'Apple SD Gothic Neo', "
    "'Malgun Gothic', '맑은 고딕', sans-serif"
)


# ─────────────────────────────────────────────
# Plotly 공통 템플릿
# ─────────────────────────────────────────────
def plotly_template():
    """POSCO CI Plotly 템플릿 — 평면, 하이라인 그리드"""
    return dict(
        layout=go.Layout(
            font=dict(family=FONT_STACK, size=12, color=POSCO_COLORS["neutral_900"]),
            title=dict(font=dict(size=15, color=POSCO_COLORS["primary_dark"], family=FONT_STACK)),
            plot_bgcolor="#FFFFFF",
            paper_bgcolor="#FFFFFF",
            colorway=SERIES_COLORS,
            xaxis=dict(
                gridcolor="#F0F0F0",
                linecolor=POSCO_COLORS["neutral_300"],
                tickfont=dict(size=11, color=POSCO_COLORS["neutral_500"]),
                zerolinecolor=POSCO_COLORS["neutral_300"],
            ),
            yaxis=dict(
                gridcolor="#F0F0F0",
                linecolor=POSCO_COLORS["neutral_300"],
                tickfont=dict(size=11, color=POSCO_COLORS["neutral_500"]),
                zerolinecolor=POSCO_COLORS["neutral_300"],
            ),
            legend=dict(
                bgcolor="rgba(255,255,255,0.95)",
                bordercolor=POSCO_COLORS["neutral_300"],
                borderwidth=1,
                font=dict(size=11),
            ),
            hoverlabel=dict(
                bgcolor=POSCO_COLORS["primary_dark"],
                bordercolor=POSCO_COLORS["primary_dark"],
                font=dict(color="white", family=FONT_STACK, size=12),
            ),
            margin=dict(l=48, r=20, t=48, b=40),
        )
    )


pio.templates["posco"] = go.layout.Template(plotly_template())


# ─────────────────────────────────────────────
# Streamlit CSS 주입
# ─────────────────────────────────────────────
def inject_theme():
    """앱 전반에 POSCO CI CSS 주입"""
    st.markdown(
        """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">

    <style>
    /* ── 서체: posco.co.kr과 동일한 스택.
       Metropolis는 사내 라이선스 폰트라 여기서 로드하지 않고,
       설치된 환경에서만 우선 적용되고 없으면 Noto Sans KR로 떨어진다. ── */
    html, body, [class*="css"], .stApp, .stMarkdown, .stText,
    button, input, select, textarea {
        font-family: 'Metropolis', 'Noto Sans KR', 'Apple SD Gothic Neo',
                     'Malgun Gothic', '맑은 고딕', sans-serif !important;
    }
    .stApp { background: #FFFFFF; }

    /* 숫자 자리 정렬 — 금액 비교 시 필수 */
    .kpi-value, .kpi-delta,
    [data-testid="stMetricValue"],
    [data-testid="stMetricDelta"],
    [data-testid="stTable"] td,
    .stDataFrame td, .stDataFrame th,
    div[data-testid="stDataEditor"] td {
        font-variant-numeric: tabular-nums;
        font-feature-settings: 'tnum' 1;
    }

    /* ── 헤더: 평면 화이트 + 네이비 텍스트 + 좌측 블루 룰 ── */
    .posco-hero {
        background: #FFFFFF;
        border-top: 3px solid #005C9C;
        border-bottom: 1px solid #E5E5E5;
        padding: 20px 24px 18px;
        margin-bottom: 20px;
    }
    .posco-hero h1 {
        color: #022846 !important;
        font-size: 22px !important;
        margin: 0 !important;
        font-weight: 700;
        letter-spacing: -0.4px;
    }
    .posco-hero p {
        color: #555555 !important;
        margin: 6px 0 0 0 !important;
        font-size: 13px;
        line-height: 1.6;
    }

    /* ── KPI 카드: 하이라인 테두리, 라운딩 3px, 그림자 없음 ── */
    .kpi-card {
        background: #FFFFFF;
        border: 1px solid #E5E5E5;
        border-radius: 3px;
        padding: 14px 16px;
        height: 100%;
    }
    .kpi-label {
        font-size: 12px;
        color: #848484;
        font-weight: 400;
        margin-bottom: 6px;
        letter-spacing: 0;
    }
    .kpi-value {
        font-size: 21px;
        font-weight: 700;
        color: #222222;
        line-height: 1.2;
        letter-spacing: -0.3px;
    }
    .kpi-unit { font-size: 13px; font-weight: 400; color: #848484; margin-left: 2px; }
    .kpi-sub  { font-size: 11px; color: #848484; margin-top: 4px; }
    .kpi-delta { font-size: 12px; font-weight: 500; margin-top: 5px; }
    .kpi-delta.up      { color: #B42318; }
    .kpi-delta.down    { color: #1B7F4B; }
    .kpi-delta.neutral { color: #848484; }

    /* 강조 카드: 네이비 솔리드 (그라디언트 없음) */
    .highlight-card {
        background: #022846;
        border: 1px solid #022846;
        border-radius: 3px;
        padding: 14px 16px;
        height: 100%;
    }
    .highlight-card .kpi-label { color: rgba(255,255,255,0.72); }
    .highlight-card .kpi-value { color: #FFFFFF; }
    .highlight-card .kpi-unit  { color: rgba(255,255,255,0.72); }
    .highlight-card .kpi-sub   { color: rgba(255,255,255,0.62); }
    .highlight-card .kpi-delta { color: #FFFFFF; }

    /* ── 탭: 밑줄형 ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
        border-bottom: 1px solid #E5E5E5;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 9px 14px;
        font-size: 13px;
        font-weight: 500;
        color: #555555;
        border-radius: 0;
    }
    .stTabs [data-baseweb="tab"]:hover { color: #005C9C; background: #FAFAFA; }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        color: #005C9C !important;
        background: transparent !important;
        border-bottom: 2px solid #005C9C !important;
        font-weight: 700;
    }
    .stTabs [data-baseweb="tab-highlight"] { display: none; }

    /* ── 버튼: 솔리드 네이비/블루, 각지게 ── */
    .stButton > button[kind="primary"] {
        background: #005C9C;
        border: 1px solid #005C9C;
        color: #FFFFFF;
        font-weight: 500;
        font-size: 13px;
        padding: 8px 20px;
        border-radius: 3px;
        box-shadow: none;
    }
    .stButton > button[kind="primary"]:hover:enabled {
        background: #022846;
        border-color: #022846;
    }
    .stButton > button[kind="primary"]:disabled {
        background: #F4F4F4; border-color: #E5E5E5; color: #B0B0B0;
    }
    .stButton > button[kind="secondary"],
    .stDownloadButton > button {
        background: #FFFFFF;
        border: 1px solid #DDDDDD;
        color: #222222;
        font-weight: 500;
        font-size: 13px;
        border-radius: 3px;
        box-shadow: none;
    }
    .stButton > button[kind="secondary"]:hover,
    .stDownloadButton > button:hover {
        border-color: #005C9C; color: #005C9C; background: #FFFFFF;
    }

    /* ── 알림 박스: 좌측 컬러 룰, 각지게 ── */
    .stAlert {
        border-radius: 0;
        border-left-width: 3px;
        font-size: 13px;
    }

    hr { border-color: #E5E5E5 !important; margin: 18px 0 !important; }

    /* ── 사이드바 ── */
    [data-testid="stSidebar"] {
        background: #FAFAFA;
        border-right: 1px solid #E5E5E5;
    }
    [data-testid="stSidebar"] .stMarkdown h3 {
        color: #022846;
        font-size: 13px;
        font-weight: 700;
        letter-spacing: 0.2px;
        margin-top: 14px;
        padding-bottom: 6px;
        border-bottom: 1px solid #E5E5E5;
    }

    /* ── 기본 metric 위젯 ── */
    [data-testid="stMetric"] {
        background: #FFFFFF;
        border: 1px solid #E5E5E5;
        border-radius: 3px;
        padding: 12px 16px;
        box-shadow: none;
    }
    [data-testid="stMetricLabel"] { color: #848484; font-weight: 400; font-size: 12px; }
    [data-testid="stMetricValue"] { color: #222222; font-weight: 700; }

    /* ── 섹션 타이틀: 블루 세로 룰 (그라디언트 없음) ── */
    .section-title {
        font-size: 15px;
        font-weight: 700;
        color: #022846;
        margin: 22px 0 10px 0;
        display: flex;
        align-items: center;
        gap: 8px;
        letter-spacing: -0.2px;
    }
    .section-title::before {
        content: '';
        width: 3px;
        height: 15px;
        background: #005C9C;
        flex: none;
    }

    /* ── 표: 헤더는 연회색, 격자 최소화 ── */
    .stDataFrame thead th,
    div[data-testid="stDataEditor"] thead th {
        background: #F4F4F4 !important;
        color: #555555 !important;
        font-weight: 500 !important;
        font-size: 12px !important;
        border-bottom: 1px solid #DDDDDD !important;
    }
    .stDataFrame, div[data-testid="stDataEditor"] { font-size: 12.5px; }

    /* ── 상태 뱃지 (신뢰도 등) ── */
    .badge {
        display: inline-block;
        font-size: 11px;
        font-weight: 500;
        padding: 2px 8px;
        border-radius: 2px;
        border: 1px solid transparent;
    }
    .badge.ok   { background:#E6F2EA; color:#1B7F4B; border-color:#BFDFCB; }
    .badge.mid  { background:#FBF1E0; color:#B26A00; border-color:#EBD7B0; }
    .badge.low  { background:#FBE9E7; color:#B42318; border-color:#EFC5C0; }
    .badge.none { background:#F4F4F4; color:#848484; border-color:#DDDDDD; }

    /* 연결 상태 표시 — 애니메이션 없이 정적 점 */
    .status-dot {
        width: 6px; height: 6px; border-radius: 50%;
        display: inline-block; margin-right: 6px; vertical-align: 1px;
    }
    .status-dot.on  { background: #1B7F4B; }
    .status-dot.off { background: #848484; }
    </style>
    """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────
def kpi_card(label, value, delta=None, delta_type="neutral", icon="", highlight=False,
             unit=None, sub=None):
    """
    KPI 카드 HTML.

    delta_type : 'up'(상승=적색) / 'down'(하락=녹색) / 'neutral'
    unit       : 값 뒤에 작게 붙는 단위 ('억원' 등)
    sub        : 값 아래 보조 설명 (원 단위 전체 금액 병기 등)
    icon       : 하위 호환용. 장식용 이모지를 걷어내는 방침이라 렌더링하지 않는다.
    """
    klass = "highlight-card" if highlight else "kpi-card"
    unit_html = f'<span class="kpi-unit">{unit}</span>' if unit else ""

    parts = [
        f'<div class="{klass}">',
        f'<div class="kpi-label">{label}</div>',
        f'<div class="kpi-value">{value}{unit_html}</div>',
    ]
    if sub:
        parts.append(f'<div class="kpi-sub">{sub}</div>')
    if delta:
        arrow = "▲" if delta_type == "up" else ("▼" if delta_type == "down" else "—")
        parts.append(f'<div class="kpi-delta {delta_type}">{arrow} {delta}</div>')
    parts.append("</div>")

    # ★ 반드시 한 줄로 이어붙인다.
    # 들여쓴 여러 줄로 만들면, 값이 없는 자리(sub/delta)가 빈 줄로 남아
    # Markdown이 HTML 블록을 그 지점에서 끊는다. 뒤따르는 들여쓴 줄은
    # 코드 블록으로 처리되어 '<div class="kpi-delta...'가 화면에 그대로 찍힌다.
    return "".join(parts)


def hero_header(title, subtitle):
    """상단 헤더 — 평면 화이트 + 상단 블루 룰"""
    return (
        f'<div class="posco-hero">'
        f"<h1>{title}</h1>"
        f"<p>{subtitle}</p>"
        f"</div>"
    )


def section_title(text):
    """섹션 구분 타이틀"""
    return f'<div class="section-title">{text}</div>'


def badge(text, level="none"):
    """상태 뱃지. level: ok / mid / low / none"""
    return f'<span class="badge {level}">{text}</span>'


def live_badge(text="실시간 연동"):
    """데이터 연동 상태 표시 (정적 — 애니메이션 없음)"""
    return (
        f'<span class="status-dot on"></span>'
        f'<span style="color:#1B7F4B;font-weight:500;font-size:12px;">{text}</span>'
    )
