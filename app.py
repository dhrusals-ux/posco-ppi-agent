"""
🏭 POSCO 투자비 물가보정 AI Agent v8
ECOS API + AI Agent + 시나리오 분석 + 포트폴리오 환산 + 고급 시각화
"""
import os
import io
from datetime import datetime

import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

from agents.ppi_agent import run_ppi_agent
from utils.ecos_client import ECOSClient
from utils.demo_data import DemoECOSClient
from utils.ecos_catalog import get_catalog
from data.ppi_categories import CATEGORY_FILTERS, filter_catalog_by_category
from utils.theme import (
    inject_theme, kpi_card, hero_header, section_title, live_badge,
    POSCO_COLORS, SERIES_COLORS, plotly_template,
)
from utils.exporters import to_excel_bytes, generate_pdf_report


# ═══════════════════════════════════════════
# 페이지 설정
# ═══════════════════════════════════════════
st.set_page_config(
    page_title="POSCO 투자비 물가보정 AI Agent",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_theme()

# Plotly 기본 템플릿
import plotly.io as pio
pio.templates.default = "posco"


def get_client():
    """현재 모드에 따른 ECOS 클라이언트"""
    if st.session_state.get("use_demo", True):
        return DemoECOSClient()
    return ECOSClient()


# ═══════════════════════════════════════════
# URL 쿼리 파라미터 → session_state 동기화
# ═══════════════════════════════════════════
qp = st.query_params
if "loaded_qp" not in st.session_state:
    st.session_state["loaded_qp"] = True
    if "code" in qp:
        st.session_state["qp_code"] = qp["code"]
    if "from" in qp:
        st.session_state["qp_from"] = qp["from"]
    if "to" in qp:
        st.session_state["qp_to"] = qp["to"]


# ═══════════════════════════════════════════
# 사이드바
# ═══════════════════════════════════════════
with st.sidebar:
    st.markdown("### ⚙️ 실행 모드")
    use_demo = st.radio(
        "모드 선택",
        ["📦 DEMO 모드 (API 키 불필요)", "🏦 LIVE 모드 (실제 ECOS)"],
        index=0,
    ).startswith("📦")
    st.session_state["use_demo"] = use_demo

    st.divider()

    if use_demo:
        st.success("✅ DEMO 모드 — 가상 PPI 데이터로 동작")
        llm_provider = "none"
    else:
        st.markdown("### 🔑 API 키")
        try:
            default_ecos = st.secrets["ECOS_API_KEY"]
        except Exception:
            default_ecos = os.getenv("ECOS_API_KEY", "")

        ecos_key = st.text_input(
            "ECOS API Key", type="password", value=default_ecos,
            help="앞뒤 따옴표·공백은 자동 제거",
        )
        if ecos_key:
            cleaned = ecos_key.strip().strip('"').strip("'").strip()
            os.environ["ECOS_API_KEY"] = cleaned
            if cleaned != ecos_key:
                st.warning(f"⚠️ 따옴표/공백 정리: {len(ecos_key)}→{len(cleaned)}자")

        st.markdown("##### 🧠 LLM")
        llm_choice = st.radio(
            "자연어 파싱 LLM",
            ["🆓 Gemini (추천)", "💰 OpenAI", "📐 규칙 기반"],
            label_visibility="collapsed",
        )
        if llm_choice.startswith("🆓"):
            try:
                default_gem = st.secrets["GEMINI_API_KEY"]
            except Exception:
                default_gem = os.getenv("GEMINI_API_KEY", "")
            gk = st.text_input("Gemini Key", type="password", value=default_gem)
            if gk:
                os.environ["GEMINI_API_KEY"] = gk.strip().strip('"').strip("'")
            llm_provider = "gemini"
        elif llm_choice.startswith("💰"):
            try:
                default_oai = st.secrets["OPENAI_API_KEY"]
            except Exception:
                default_oai = os.getenv("OPENAI_API_KEY", "")
            ok = st.text_input("OpenAI Key", type="password", value=default_oai)
            if ok:
                os.environ["OPENAI_API_KEY"] = ok.strip().strip('"').strip("'")
            llm_provider = "openai"
        else:
            llm_provider = "none"

        st.divider()
        st.markdown("### 🗂️ 카탈로그")
        if os.getenv("ECOS_API_KEY"):
            try:
                catalog = get_catalog(api_key=os.getenv("ECOS_API_KEY"))
                if catalog is not None and len(catalog) > 0:
                    st.success(f"✅ ECOS 품목 **{len(catalog):,}개** 로드")
                    if st.button("🔄 카탈로그 새로고침", use_container_width=True):
                        st.cache_data.clear()
                        st.rerun()
                else:
                    st.warning("카탈로그 비어있음")
            except Exception as e:
                st.error(f"로드 실패: {e}")

    st.divider()
    st.markdown("### 📖 소개")
    st.caption(
        "**POSCO 투자엔지니어링실 교육용 데모**\n\n"
        "한국은행 ECOS API를 활용해 과거 투자비를 "
        "현재 시점 PPI로 자동 환산하는 AI Agent입니다."
    )
    st.markdown(live_badge("ECOS LIVE" if not use_demo else "DEMO"), unsafe_allow_html=True)


# ═══════════════════════════════════════════
# 상단 Hero 헤더 + 실시간 PPI KPI
# ═══════════════════════════════════════════
st.markdown(
    hero_header(
        "🏭 POSCO 투자비 물가보정 AI Agent",
        "ECOS API × AI Agent × 시나리오 분석 × 포트폴리오 환산 — 투자엔지니어링 실무 올인원 대시보드",
    ),
    unsafe_allow_html=True,
)


# 상단 KPI 스트립 (총지수 현황)
def fetch_top_kpi():
    """ECOS 총지수 최신 3개월 데이터 → KPI 카드용"""
    try:
        if use_demo:
            # DEMO 데이터
            return {
                "total": 118.5, "yoy": 2.1, "mom": 0.3,
                "latest_period": "2026-03", "source": "DEMO",
            }
        client = ECOSClient()
        # 총지수 (404Y014 통계표의 '*AA')
        end = datetime.now().strftime("%Y%m")
        start = (datetime.now().replace(day=1).replace(year=datetime.now().year - 1)).strftime("%Y%m")
        try:
            df = client.get_ppi("*AA", start, end)
            df = df.sort_values("TIME").reset_index(drop=True)
            latest = float(df["DATA_VALUE"].iloc[-1])
            prev_m = float(df["DATA_VALUE"].iloc[-2]) if len(df) >= 2 else latest
            prev_y = float(df["DATA_VALUE"].iloc[-13]) if len(df) >= 13 else latest
            return {
                "total": latest,
                "yoy": (latest / prev_y - 1) * 100,
                "mom": (latest / prev_m - 1) * 100,
                "latest_period": df["TIME"].iloc[-1],
                "source": "ECOS",
            }
        except Exception:
            return None
    except Exception:
        return None


kpi_data = fetch_top_kpi()
if kpi_data:
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(kpi_card(
            "생산자물가 총지수", f"{kpi_data['total']:.2f}",
            delta=f"기준 2020=100", delta_type="neutral", icon="📊",
        ), unsafe_allow_html=True)
    with k2:
        yoy = kpi_data["yoy"]
        st.markdown(kpi_card(
            "전년 동월비 (YoY)", f"{yoy:+.2f}%",
            delta=f"{'상승' if yoy > 0 else '하락'}",
            delta_type="up" if yoy > 0 else "down", icon="📈",
        ), unsafe_allow_html=True)
    with k3:
        mom = kpi_data["mom"]
        st.markdown(kpi_card(
            "전월비 (MoM)", f"{mom:+.2f}%",
            delta=f"{'상승' if mom > 0 else '하락'}",
            delta_type="up" if mom > 0 else "down", icon="📉",
        ), unsafe_allow_html=True)
    with k4:
        st.markdown(kpi_card(
            "기준 시점", kpi_data["latest_period"],
            delta=f"소스: {kpi_data['source']}", delta_type="neutral", icon="🕐",
        ), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)


# ═══════════════════════════════════════════
# 탭 정의 (7개)
# ═══════════════════════════════════════════
tab_ai, tab_ppi, tab_multi, tab_scn, tab_port, tab_heat, tab_share = st.tabs([
    "🤖 AI Agent 환산",
    "🔍 설비별 PPI 조회",
    "📊 다중 설비 비교",
    "🧪 시나리오 분석",
    "📦 포트폴리오 환산",
    "🗺️ 히트맵 & 상관관계",
    "🔗 공유/내보내기",
])


# ═══════════════════════════════════════════
# 공통 헬퍼: 기간 프리셋 버튼
# ═══════════════════════════════════════════
def period_preset_buttons(key_prefix: str, default_start="201501", default_end="202612"):
    """기간 프리셋 버튼 + 시작/종료 입력"""
    st.markdown("##### 📅 기간 설정")
    p1, p2, p3, p4, p5, p6 = st.columns(6)
    today = datetime.now()
    preset = None

    def _ym(year, month):
        return f"{year:04d}{month:02d}"

    if p1.button("최근 1년", key=f"{key_prefix}_p1", use_container_width=True):
        preset = (_ym(today.year - 1, today.month), _ym(today.year, today.month))
    if p2.button("최근 3년", key=f"{key_prefix}_p3", use_container_width=True):
        preset = (_ym(today.year - 3, today.month), _ym(today.year, today.month))
    if p3.button("최근 5년", key=f"{key_prefix}_p5", use_container_width=True):
        preset = (_ym(today.year - 5, today.month), _ym(today.year, today.month))
    if p4.button("최근 10년", key=f"{key_prefix}_p10", use_container_width=True):
        preset = (_ym(today.year - 10, today.month), _ym(today.year, today.month))
    if p5.button("팬데믹 이후", key=f"{key_prefix}_p_covid", use_container_width=True):
        preset = ("202001", _ym(today.year, today.month))
    if p6.button("전체(2010~)", key=f"{key_prefix}_p_all", use_container_width=True):
        preset = ("201001", _ym(today.year, today.month))

    if preset:
        st.session_state[f"{key_prefix}_start"] = preset[0]
        st.session_state[f"{key_prefix}_end"] = preset[1]

    c1, c2 = st.columns(2)
    with c1:
        start = st.text_input(
            "시작 (YYYYMM)",
            value=st.session_state.get(f"{key_prefix}_start", default_start),
            key=f"{key_prefix}_start_input",
        )
    with c2:
        end = st.text_input(
            "종료 (YYYYMM)",
            value=st.session_state.get(f"{key_prefix}_end", default_end),
            key=f"{key_prefix}_end_input",
        )
    return start, end


# ═══════════════════════════════════════════
# Tab 1: AI Agent 환산
# ═══════════════════════════════════════════
with tab_ai:
    st.markdown(section_title("🤖 자연어 입력 → 자동 환산"), unsafe_allow_html=True)

    examples = [
        "(직접 입력)",
        "2020년 1월 800억원 펌프 설비를 2026년 1월 기준으로 환산",
        "2018년 3월 변압기 1,200억원을 2026년 1월 현재가로",
        "2019년 6월 시멘트 공사 500억원의 2026년 환산금액은?",
        "2017년 5월 철강 300억원을 2026년 1월 기준으로",
    ]
    col_ex, col_ov = st.columns([2, 1])
    with col_ex:
        selected_ex = st.selectbox("💡 예시 선택", examples)
    with col_ov:
        override_code = st.text_input("⚙️ 강제 ITEM_CODE (선택)", "",
                                       help="자동 매칭 대신 특정 코드 사용")

    default_q = "" if selected_ex == "(직접 입력)" else selected_ex
    user_query = st.text_area("요청 내용", value=default_q, height=80,
                               placeholder="예: 2020년 1월 800억원 펌프 2026년 1월 환산")

    if st.button("🚀 AI Agent 실행", type="primary", use_container_width=True):
        if not user_query.strip():
            st.warning("요청 내용을 입력해 주세요.")
        elif not use_demo and not os.getenv("ECOS_API_KEY"):
            st.error("⚠️ LIVE 모드에서는 ECOS API Key가 필요합니다.")
        else:
            with st.spinner("🤖 AI Agent 분석 중..."):
                try:
                    result = run_ppi_agent(
                        user_query, use_demo=use_demo, llm_provider=llm_provider,
                        override_code=(override_code.strip() or None),
                    )

                    # 데이터 소스
                    st.caption(f"{result['data_source']}  |  🧠 {result['used_llm']}")

                    # 자동 매칭 결과
                    if result["parsed"].get("auto_matched"):
                        ami = result["parsed"].get("auto_match_info", {})
                        st.success(
                            f"🎯 **자동 매칭**: 「{ami.get('matched_keyword','')}」 → "
                            f"`{ami.get('code','')}` ({ami.get('name','')}) · 점수 {ami.get('score',0):.1f}"
                        )

                    # 고급 KPI 카드 4개
                    parsed = result["parsed"]
                    factor = result["factor"]
                    orig = parsed["original_cost"]
                    adj = result["adjusted_cost"]
                    diff = adj - orig

                    kc1, kc2, kc3, kc4 = st.columns(4)
                    with kc1:
                        st.markdown(kpi_card(
                            "원금", f"{orig:,.0f} 억",
                            delta=parsed.get("base_period", ""),
                            icon="💰",
                        ), unsafe_allow_html=True)
                    with kc2:
                        st.markdown(kpi_card(
                            "보정계수", f"{factor:.4f}",
                            delta=f"{(factor-1)*100:+.2f}%",
                            delta_type="up" if factor > 1 else "down",
                            icon="⚖️",
                        ), unsafe_allow_html=True)
                    with kc3:
                        st.markdown(kpi_card(
                            "증감액", f"{diff:+,.1f} 억",
                            delta="현재가 기준",
                            delta_type="up" if diff > 0 else "down",
                            icon="📊",
                        ), unsafe_allow_html=True)
                    with kc4:
                        st.markdown(kpi_card(
                            "환산금액", f"{adj:,.1f} 억",
                            delta=parsed.get("target_period", ""),
                            delta_type="neutral",
                            icon="🎯",
                            highlight=True,
                        ), unsafe_allow_html=True)

                    st.markdown("<br>", unsafe_allow_html=True)

                    # PPI 추이 차트 (rangeslider + fill)
                    st.markdown(section_title("📈 PPI 추이 분석"), unsafe_allow_html=True)
                    try:
                        client = get_client()
                        df_full = client.get_ppi(
                            parsed["recommended_code"],
                            "201501",
                            parsed.get("target_period", "202612"),
                        )
                        df_full["TIME_DT"] = pd.to_datetime(df_full["TIME"], format="%Y%m")

                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=df_full["TIME_DT"], y=df_full["DATA_VALUE"],
                            mode="lines", name="PPI",
                            line=dict(color=POSCO_COLORS["primary"], width=2.5),
                            fill="tozeroy",
                            fillcolor="rgba(0,94,184,0.08)",
                            hovertemplate="<b>%{x|%Y년 %m월}</b><br>PPI: %{y:.2f}<extra></extra>",
                        ))

                        # 기준/목표 시점 마커
                        def _mark(period, label, color):
                            try:
                                t = pd.to_datetime(period, format="%Y%m")
                                v = df_full[df_full["TIME"] == period]["DATA_VALUE"]
                                if len(v) > 0:
                                    fig.add_trace(go.Scatter(
                                        x=[t], y=[float(v.iloc[0])],
                                        mode="markers+text",
                                        marker=dict(size=14, color=color, line=dict(color="white", width=2)),
                                        text=[label], textposition="top center",
                                        textfont=dict(size=11, color=color),
                                        showlegend=False,
                                        hovertemplate=f"<b>{label}</b><br>%{{x|%Y년 %m월}}<br>PPI: %{{y:.2f}}<extra></extra>",
                                    ))
                            except Exception:
                                pass
                        _mark(parsed["base_period"], "📍 기준", POSCO_COLORS["accent"])
                        _mark(parsed["target_period"], "🎯 목표", POSCO_COLORS["danger"])

                        fig.update_layout(
                            title=f"{result['item_info'].get('name','품목')} PPI 시계열",
                            xaxis=dict(rangeslider=dict(visible=True, thickness=0.05)),
                            yaxis_title="PPI (2020=100)",
                            height=480,
                            hovermode="x unified",
                        )
                        st.plotly_chart(fig, use_container_width=True)

                        # 보고서
                        st.markdown(section_title("📝 AI 분석 보고서"), unsafe_allow_html=True)
                        st.markdown(result["report"])

                        # 내보내기
                        st.markdown("##### 📤 내보내기")
                        ex1, ex2, ex3 = st.columns(3)
                        with ex1:
                            pdf_bytes = generate_pdf_report(
                                title=f"투자비 물가보정 리포트 — {result['item_info'].get('name', '')}",
                                summary={
                                    "품목": result["item_info"].get("name", ""),
                                    "기준 시점": parsed["base_period"],
                                    "목표 시점": parsed["target_period"],
                                    "기준 PPI": f"{result['base_ppi']:.2f}",
                                    "목표 PPI": f"{result['target_ppi']:.2f}",
                                    "보정계수": f"{factor:.4f}",
                                    "원금": f"{orig:,.1f} 억원",
                                    "환산금액": f"{adj:,.1f} 억원",
                                    "증감": f"{diff:+,.1f} 억원 ({(factor-1)*100:+.2f}%)",
                                },
                                body_text=result["report"],
                                table_df=df_full[["TIME", "DATA_VALUE"]].rename(
                                    columns={"TIME": "시점", "DATA_VALUE": "PPI"}
                                ),
                            )
                            st.download_button(
                                "📄 PDF 다운로드", pdf_bytes,
                                f"PPI_리포트_{parsed['base_period']}_{parsed['target_period']}.pdf",
                                "application/pdf", use_container_width=True,
                            )
                        with ex2:
                            xlsx = to_excel_bytes({
                                "요약": pd.DataFrame([{
                                    "항목": k, "값": v,
                                } for k, v in {
                                    "품목": result["item_info"].get("name", ""),
                                    "원금(억)": orig,
                                    "환산금액(억)": adj,
                                    "보정계수": factor,
                                    "기준시점": parsed["base_period"],
                                    "목표시점": parsed["target_period"],
                                }.items()]),
                                "PPI시계열": df_full[["TIME", "DATA_VALUE"]],
                            })
                            st.download_button(
                                "📊 Excel 다운로드", xlsx,
                                f"PPI_데이터_{parsed['base_period']}_{parsed['target_period']}.xlsx",
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True,
                            )
                        with ex3:
                            share_url = (
                                f"?code={parsed['recommended_code']}"
                                f"&from={parsed['base_period']}&to={parsed['target_period']}"
                            )
                            st.code(share_url, language="text")
                            st.caption("↑ URL 뒤에 붙이면 동일 화면")

                    except Exception as e:
                        st.warning(f"차트 생성 실패: {e}")

                    # ───────────────────────────────────────────
                    # 🆕 상승 원인 분석 (Gemini)
                    # ───────────────────────────────────────────
                    st.markdown("---")
                    st.markdown("### 📰 상승 원인 분석 (AI)")
                    st.caption("Gemini가 PPI 추이와 거시경제 이벤트를 연결해 왜 움직였는지 해설합니다.")

                    if st.button("🧠 Gemini로 원인 분석 실행", key="explain_btn", use_container_width=True):
                        if not os.getenv("GEMINI_API_KEY", "").strip():
                            st.warning("⚠️ Gemini API Key가 설정되지 않았습니다. 좌측 사이드바에서 입력하세요.")
                        else:
                            try:
                                from agents.ppi_agent import explain_price_change_gemini
                                with st.spinner("Gemini가 거시경제 맥락을 분석 중입니다... (10~20초)"):
                                    explanation = explain_price_change_gemini(
                                        item_name=result["item_info"].get("name", ""),
                                        item_code=parsed["recommended_code"],
                                        ppi_df=df_full.rename(columns={"TIME": "date", "DATA_VALUE": "value"}),
                                        base_period=parsed["base_period"],
                                        target_period=parsed["target_period"],
                                        factor=factor,
                                    )
                                st.markdown(
                                    f"<div style='background:linear-gradient(135deg,#f8fbff,#eef4ff);"
                                    f"padding:1.5rem;border-radius:12px;border-left:4px solid #005EB8;"
                                    f"margin-top:0.8rem'>{explanation}</div>",
                                    unsafe_allow_html=True,
                                )
                            except Exception as e:
                                st.error(f"원인 분석 실패: {e}")

                    with st.expander("🔧 파싱 상세"):
                        st.json(parsed)

                except Exception as e:
                    err_str = str(e)
                    st.error(f"❌ 실행 오류: {e}")
                    if "INFO-100" in err_str:
                        st.info("💡 INFO-100: ECOS 키 확인 (따옴표/공백 제거 · 발급 후 1시간 대기)")
                    elif "INFO-200" in err_str:
                        st.info("💡 INFO-200: ⚙️ 강제 ITEM_CODE에 실제 코드를 넣어보세요")


# ═══════════════════════════════════════════
# Tab 2: 설비별 PPI 조회
# ═══════════════════════════════════════════
with tab_ppi:
    st.markdown(section_title("🔍 ECOS 실제 품목 단일 조회"), unsafe_allow_html=True)

    if use_demo:
        st.info("📦 DEMO 모드 — 가상 데이터 조회")
        active_code = "DEMO"
        active_name = "데모 품목"
    elif not os.getenv("ECOS_API_KEY"):
        st.warning("⚠️ ECOS API Key가 필요합니다.")
        st.stop()
    else:
        mode = st.radio(
            "입력 방식",
            ["📂 카테고리 필터", "🔍 이름 검색", "⌨️ 코드 직접 입력"],
            horizontal=True,
        )
        catalog = get_catalog(api_key=os.getenv("ECOS_API_KEY"))
        if catalog is None or len(catalog) == 0:
            st.error("카탈로그 로드 실패")
            st.stop()

        active_code, active_name = None, None
        if mode.startswith("📂"):
            c1, c2 = st.columns([1, 2])
            with c1:
                cat = st.selectbox("대분류", list(CATEGORY_FILTERS.keys()))
            filtered = filter_catalog_by_category(catalog, cat)
            with c2:
                if len(filtered) == 0:
                    st.warning("매칭 품목 없음")
                else:
                    opts = filtered.apply(lambda r: f"{r['ITEM_NAME']} [코드: {r['ITEM_CODE']}]", axis=1).tolist()
                    sel = st.selectbox(f"ECOS 품목 ({len(filtered)}개)", opts)
                    idx = opts.index(sel)
                    active_code = str(filtered.iloc[idx]["ITEM_CODE"])
                    active_name = str(filtered.iloc[idx]["ITEM_NAME"])
        elif mode.startswith("🔍"):
            kw = st.text_input("품목명 검색", placeholder="예: 펌프, 변압기, 시멘트")
            if kw.strip():
                m = catalog[catalog["ITEM_NAME"].astype(str).str.contains(kw.strip(), na=False)]
                if len(m) == 0:
                    st.warning("매칭 없음")
                else:
                    opts = m.apply(lambda r: f"{r['ITEM_NAME']} [코드: {r['ITEM_CODE']}]", axis=1).tolist()
                    sel = st.selectbox(f"결과 ({len(m)}개)", opts)
                    idx = opts.index(sel)
                    active_code = str(m.iloc[idx]["ITEM_CODE"])
                    active_name = str(m.iloc[idx]["ITEM_NAME"])
        else:
            c1, c2 = st.columns([1, 2])
            active_code = c1.text_input("ITEM_CODE", st.session_state.get("qp_code", ""),
                                         placeholder="예: 41001")
            active_name = c2.text_input("품목명", "사용자 지정")

        if active_code:
            st.info(f"📌 **{active_name}** · 코드 `{active_code}`")

    start, end = period_preset_buttons("ppi",
        default_start=st.session_state.get("qp_from", "201501"),
        default_end=st.session_state.get("qp_to", "202612"),
    )

    if st.button("📊 조회 및 분석", type="primary", key="ppi_btn"):
        if not active_code:
            st.error("품목을 선택하세요.")
        else:
            try:
                client = get_client()
                df = client.get_ppi(active_code, start, end)
                df["TIME_DT"] = pd.to_datetime(df["TIME"], format="%Y%m")

                # KPI 카드
                first_v, last_v = float(df["DATA_VALUE"].iloc[0]), float(df["DATA_VALUE"].iloc[-1])
                change = (last_v / first_v - 1) * 100
                k1, k2, k3, k4 = st.columns(4)
                k1.markdown(kpi_card("데이터 포인트", f"{len(df)}개",
                                      delta=f"{start}~{end}", icon="📍"), unsafe_allow_html=True)
                k2.markdown(kpi_card("시작 PPI", f"{first_v:.2f}",
                                      delta=str(df['TIME'].iloc[0]), icon="🟢"), unsafe_allow_html=True)
                k3.markdown(kpi_card("종료 PPI", f"{last_v:.2f}",
                                      delta=str(df['TIME'].iloc[-1]), icon="🔴"), unsafe_allow_html=True)
                k4.markdown(kpi_card("기간 변동률", f"{change:+.2f}%",
                                      delta="상승" if change > 0 else "하락",
                                      delta_type="up" if change > 0 else "down",
                                      icon="📈", highlight=True), unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)

                # 메인 차트 (rangeslider)
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=df["TIME_DT"], y=df["DATA_VALUE"],
                    mode="lines", name=active_name,
                    line=dict(color=POSCO_COLORS["primary"], width=2.8),
                    fill="tozeroy",
                    fillcolor="rgba(0,94,184,0.1)",
                    hovertemplate="<b>%{x|%Y년 %m월}</b><br>PPI: %{y:.2f}<extra></extra>",
                ))
                fig.add_hline(y=100, line_dash="dash", line_color=POSCO_COLORS["accent"],
                              annotation_text="2020 기준 (100)")
                fig.update_layout(
                    title=f"{active_name} PPI 추이",
                    xaxis=dict(rangeslider=dict(visible=True, thickness=0.06)),
                    yaxis_title="PPI (2020=100)",
                    height=520,
                )
                st.plotly_chart(fig, use_container_width=True)

                # YoY 바차트
                df["YEAR"] = df["TIME_DT"].dt.year
                yr = df.groupby("YEAR")["DATA_VALUE"].mean().reset_index()
                yr["YoY(%)"] = yr["DATA_VALUE"].pct_change() * 100
                yr = yr.dropna()
                if len(yr) > 0:
                    fig_y = px.bar(
                        yr, x="YEAR", y="YoY(%)",
                        color="YoY(%)", color_continuous_scale=[[0, POSCO_COLORS["success"]],
                                                                  [0.5, POSCO_COLORS["neutral_200"]],
                                                                  [1, POSCO_COLORS["danger"]]],
                        title="📊 연도별 전년대비 변동률",
                    )
                    fig_y.update_layout(height=360)
                    st.plotly_chart(fig_y, use_container_width=True)

                # 데이터 + 다운로드
                with st.expander("📋 원본 데이터"):
                    st.dataframe(df[["TIME", "ITEM_NAME1", "DATA_VALUE"]],
                                  use_container_width=True, hide_index=True)
                    csv = df.to_csv(index=False).encode("utf-8-sig")
                    d1, d2 = st.columns(2)
                    d1.download_button("📥 CSV", csv, f"PPI_{active_name}.csv",
                                       "text/csv", use_container_width=True)
                    xlsx = to_excel_bytes({"PPI 데이터": df[["TIME", "DATA_VALUE"]]})
                    d2.download_button("📊 Excel", xlsx, f"PPI_{active_name}.xlsx",
                                       use_container_width=True)
            except Exception as e:
                st.error(f"조회 실패: {e}")


# ═══════════════════════════════════════════
# Tab 3: 다중 설비 비교
# ═══════════════════════════════════════════
with tab_multi:
    st.markdown(section_title("📊 여러 설비 PPI 동시 비교"), unsafe_allow_html=True)

    if use_demo:
        st.warning("DEMO 모드에서는 제한. LIVE로 전환하세요.")
        selected_rows = []
    elif not os.getenv("ECOS_API_KEY"):
        st.warning("ECOS Key 필요")
        selected_rows = []
    else:
        catalog = get_catalog(api_key=os.getenv("ECOS_API_KEY"))
        if catalog is None or len(catalog) == 0:
            st.error("카탈로그 로드 실패")
            selected_rows = []
        else:
            cats = st.multiselect(
                "🗂️ 카테고리 필터",
                list(CATEGORY_FILTERS.keys()),
                default=["🏭 기계 설비", "⚡ 전기 설비", "🏗️ 토건/구조 설비"],
            )
            if cats:
                pool = pd.concat([filter_catalog_by_category(catalog, c) for c in cats]
                                 ).drop_duplicates("ITEM_CODE").reset_index(drop=True)
            else:
                pool = catalog
            st.caption(f"🔎 풀: {len(pool)}개 · 2~6개 선택 권장")

            labels = pool.apply(lambda r: f"{r['ITEM_NAME']} [코드: {r['ITEM_CODE']}]", axis=1).tolist()
            default_sel = labels[:4]
            sel_labels = st.multiselect("비교할 품목", labels, default=default_sel)
            selected_rows = []
            for l in sel_labels:
                idx = labels.index(l)
                selected_rows.append({
                    "code": str(pool.iloc[idx]["ITEM_CODE"]),
                    "name": str(pool.iloc[idx]["ITEM_NAME"]),
                })

    start_m, end_m = period_preset_buttons("multi", "201801", "202612")
    normalize = st.checkbox("시작점=100 정규화 (변동 폭만 비교)", value=True)

    if st.button("📊 비교 차트 생성", type="primary", key="multi_btn"):
        if not selected_rows:
            st.warning("품목 선택 필요")
        else:
            try:
                client = get_client()
                fig = go.Figure()
                summary = []
                skipped = []
                prog = st.progress(0, text="조회 중...")
                all_series = {}

                for i, item in enumerate(selected_rows):
                    try:
                        df = client.get_ppi(item["code"], start_m, end_m)
                        df["TIME_DT"] = pd.to_datetime(df["TIME"], format="%Y%m")
                        y = df["DATA_VALUE"].values
                        y_plot = y / y[0] * 100 if normalize and y[0] != 0 else y

                        all_series[item["name"]] = pd.Series(
                            df["DATA_VALUE"].values, index=df["TIME"].values
                        )

                        fig.add_trace(go.Scatter(
                            x=df["TIME_DT"], y=y_plot, mode="lines",
                            name=item["name"],
                            line=dict(color=SERIES_COLORS[i % len(SERIES_COLORS)], width=2.3),
                            hovertemplate="<b>%{fullData.name}</b><br>%{x|%Y-%m}<br>"
                                          + ("정규화: " if normalize else "PPI: ") + "%{y:.2f}<extra></extra>",
                        ))
                        summary.append({
                            "품목": item["name"],
                            "ECOS 코드": item["code"],
                            "시작 PPI": round(float(y[0]), 2),
                            "종료 PPI": round(float(y[-1]), 2),
                            "변동률(%)": round((y[-1] / y[0] - 1) * 100, 2),
                        })
                    except Exception as e:
                        skipped.append((item["name"], str(e)))
                    prog.progress((i + 1) / len(selected_rows), text=f"{i + 1}/{len(selected_rows)}")
                prog.empty()

                if skipped:
                    with st.expander(f"⚠️ 조회 실패 {len(skipped)}건"):
                        for n, e in skipped:
                            st.markdown(f"- **{n}**: {e}")

                if summary:
                    if normalize:
                        fig.add_hline(y=100, line_dash="dash", line_color=POSCO_COLORS["neutral_500"],
                                      annotation_text="시작점=100")
                    fig.update_layout(
                        title="📈 다중 설비 PPI 비교" + (" (정규화)" if normalize else ""),
                        xaxis=dict(rangeslider=dict(visible=True, thickness=0.05)),
                        yaxis_title="정규화 지수" if normalize else "PPI (2020=100)",
                        height=560, hovermode="x unified",
                        legend=dict(orientation="h", y=1.02, x=0),
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    df_sum = pd.DataFrame(summary).sort_values("변동률(%)", ascending=False)
                    st.dataframe(df_sum, use_container_width=True, hide_index=True)

                    fig_bar = px.bar(
                        df_sum, x="품목", y="변동률(%)", text="변동률(%)",
                        color="변동률(%)",
                        color_continuous_scale=[[0, POSCO_COLORS["success"]],
                                                 [0.5, "#F1F5F9"],
                                                 [1, POSCO_COLORS["danger"]]],
                        title="💹 기간 누적 변동률 순위",
                    )
                    fig_bar.update_traces(texttemplate="%{text:+.1f}%", textposition="outside")
                    fig_bar.update_layout(height=420)
                    st.plotly_chart(fig_bar, use_container_width=True)

                    # 결과 저장 (다른 탭에서 재사용)
                    st.session_state["multi_series"] = all_series
                    st.session_state["multi_summary"] = df_sum

                    # 내보내기
                    xlsx = to_excel_bytes({"비교 요약": df_sum})
                    st.download_button(
                        "📊 Excel 다운로드", xlsx,
                        f"다중설비_{start_m}_{end_m}.xlsx",
                        use_container_width=True,
                    )

                    # 세션에 Gemini 분석용 데이터 저장
                    st.session_state["multi_items_info"] = [
                        {
                            "name": row["품목"],
                            "code": row["ECOS 코드"],
                            "factor": row["종료 PPI"] / row["시작 PPI"] if row["시작 PPI"] else 1.0,
                            "df": pd.DataFrame({
                                "date": pd.to_datetime(all_series[row["품목"]].index, format="%Y%m"),
                                "value": all_series[row["품목"]].values,
                            }) if row["품목"] in all_series else None,
                        }
                        for _, row in df_sum.iterrows()
                    ]
                    st.session_state["multi_period"] = (start_m, end_m)
            except Exception as e:
                st.error(f"오류: {e}")

    # ───────────────────────────────────────────
    # 🆕 AI 비교 분석 (Gemini) — Tab 3 하단
    # ───────────────────────────────────────────
    if "multi_items_info" in st.session_state and st.session_state["multi_items_info"]:
        st.markdown("---")
        st.markdown("### 📰 AI 비교 분석")
        st.caption("Gemini가 품목별로 왜 다르게 움직였는지 거시·산업 맥락으로 해설합니다.")

        if st.button("🧠 Gemini로 비교 분석 실행", key="multi_explain_btn", use_container_width=True):
            if not os.getenv("GEMINI_API_KEY", "").strip():
                st.warning("⚠️ Gemini API Key가 설정되지 않았습니다. 좌측 사이드바에서 입력하세요.")
            else:
                try:
                    from agents.ppi_agent import explain_multi_comparison_gemini
                    s_m, e_m = st.session_state.get("multi_period", (start_m, end_m))
                    with st.spinner("Gemini가 품목 간 차이를 분석 중입니다... (15~25초)"):
                        explanation = explain_multi_comparison_gemini(
                            items_info=st.session_state["multi_items_info"],
                            base_period=s_m,
                            target_period=e_m,
                        )
                    st.markdown(
                        f"<div style='background:linear-gradient(135deg,#fff9f0,#fef3e2);"
                        f"padding:1.5rem;border-radius:12px;border-left:4px solid #F29F05;"
                        f"margin-top:0.8rem'>{explanation}</div>",
                        unsafe_allow_html=True,
                    )
                except Exception as e:
                    st.error(f"비교 분석 실패: {e}")


# ═══════════════════════════════════════════
# Tab 4: 시나리오 분석 (What-if)
# ═══════════════════════════════════════════
with tab_scn:
    st.markdown(section_title("🧪 What-if 시나리오 분석"), unsafe_allow_html=True)
    st.caption("원금·보정계수·외부 충격 변동 시 환산금액 변화를 실시간 시뮬레이션")

    s1, s2, s3 = st.columns(3)
    base_cost = s1.number_input("💰 기준 원금 (억원)", 0.0, 100000.0, 800.0, step=10.0)
    base_factor = s2.number_input("⚖️ 기준 보정계수", 0.1, 5.0, 1.23, step=0.01, format="%.4f")
    base_label = s3.text_input("🏷️ 시나리오 이름", "2020년 펌프 800억")

    st.markdown("##### 🎛️ What-if 변수")
    v1, v2, v3 = st.columns(3)
    cost_shock = v1.slider("원금 변동 (%)", -50, 50, 0, help="자재비/인건비 변동 가정")
    ppi_shock = v2.slider("PPI 추가 변동 (%)", -30, 30, 0, help="원자재 급등/급락 시뮬")
    fx_shock = v3.slider("환율 변동 (%)", -20, 20, 0, help="수입자재 비중 영향")

    # 민감도 (기본 50%/30%/20% 가중 예시)
    fx_sensitivity = 0.3  # 환율 1% → 환산 0.3% 영향 가정
    adj_orig = base_cost * base_factor
    new_cost = base_cost * (1 + cost_shock / 100)
    new_factor = base_factor * (1 + ppi_shock / 100) * (1 + fx_shock * fx_sensitivity / 100)
    new_adj = new_cost * new_factor
    delta = new_adj - adj_orig

    st.markdown("<br>", unsafe_allow_html=True)
    r1, r2, r3, r4 = st.columns(4)
    r1.markdown(kpi_card("기준 환산금액", f"{adj_orig:,.1f} 억",
                          delta=f"{base_cost:.0f} × {base_factor:.4f}", icon="📍"),
                 unsafe_allow_html=True)
    r2.markdown(kpi_card("새 원금", f"{new_cost:,.1f} 억",
                          delta=f"{cost_shock:+d}%", delta_type="up" if cost_shock > 0 else "down",
                          icon="💰"), unsafe_allow_html=True)
    r3.markdown(kpi_card("새 보정계수", f"{new_factor:.4f}",
                          delta=f"PPI{ppi_shock:+d}% · FX{fx_shock:+d}%",
                          icon="⚖️"), unsafe_allow_html=True)
    r4.markdown(kpi_card(
        "새 환산금액", f"{new_adj:,.1f} 억",
        delta=f"{delta:+,.1f} 억 ({(new_adj/adj_orig - 1)*100:+.2f}%)",
        delta_type="up" if delta > 0 else "down",
        icon="🎯", highlight=True,
    ), unsafe_allow_html=True)

    # 토네이도 차트 (민감도 분석)
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(section_title("🌪️ 민감도 토네이도 분석"), unsafe_allow_html=True)
    st.caption("각 변수 ±10% 변동 시 환산금액 영향 크기")

    tornado_data = []
    for var_name, shock_pct in [("원금 (자재비)", 10), ("PPI (원자재)", 10), ("환율 (수입)", 10)]:
        if "원금" in var_name:
            low = base_cost * (1 - shock_pct/100) * base_factor
            high = base_cost * (1 + shock_pct/100) * base_factor
        elif "PPI" in var_name:
            low = base_cost * base_factor * (1 - shock_pct/100)
            high = base_cost * base_factor * (1 + shock_pct/100)
        else:
            low = base_cost * base_factor * (1 - shock_pct * fx_sensitivity/100)
            high = base_cost * base_factor * (1 + shock_pct * fx_sensitivity/100)
        tornado_data.append({
            "변수": var_name, "낮음 (-10%)": low, "높음 (+10%)": high,
            "영향폭": high - low,
        })
    tornado_df = pd.DataFrame(tornado_data).sort_values("영향폭", ascending=True)

    fig_t = go.Figure()
    fig_t.add_trace(go.Bar(
        y=tornado_df["변수"],
        x=tornado_df["높음 (+10%)"] - adj_orig,
        base=adj_orig,
        orientation="h", name="+10%",
        marker_color=POSCO_COLORS["danger"],
        hovertemplate="%{y}: %{x:+.1f}억<extra></extra>",
    ))
    fig_t.add_trace(go.Bar(
        y=tornado_df["변수"],
        x=tornado_df["낮음 (-10%)"] - adj_orig,
        base=adj_orig,
        orientation="h", name="-10%",
        marker_color=POSCO_COLORS["success"],
        hovertemplate="%{y}: %{x:+.1f}억<extra></extra>",
    ))
    fig_t.add_vline(x=adj_orig, line_dash="dash", line_color=POSCO_COLORS["neutral_700"],
                    annotation_text=f"기준 {adj_orig:.1f}")
    fig_t.update_layout(
        barmode="overlay", height=300,
        title="변수별 ±10% 변동 영향",
        xaxis_title="환산금액 (억)", showlegend=True,
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig_t, use_container_width=True)

    # 시나리오 테이블
    with st.expander("🎭 3가지 시나리오 비교 (낙관/기본/비관)"):
        scenarios = pd.DataFrame([
            {"시나리오": "🟢 낙관", "원금(%)": -10, "PPI(%)": -5, "FX(%)": -5,
             "환산금액(억)": base_cost*0.9 * base_factor*0.95*(1-0.05*fx_sensitivity/100)},
            {"시나리오": "⚪ 기본", "원금(%)": 0, "PPI(%)": 0, "FX(%)": 0,
             "환산금액(억)": adj_orig},
            {"시나리오": "🔴 비관", "원금(%)": 15, "PPI(%)": 10, "FX(%)": 10,
             "환산금액(억)": base_cost*1.15 * base_factor*1.10*(1+0.10*fx_sensitivity/100)},
        ])
        scenarios["증감(%)"] = ((scenarios["환산금액(억)"] / adj_orig - 1) * 100).round(2)
        st.dataframe(scenarios, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════
# Tab 5: 포트폴리오 환산기
# ═══════════════════════════════════════════
with tab_port:
    st.markdown(section_title("📦 설비 구성비 기반 포트폴리오 환산"), unsafe_allow_html=True)
    st.caption("한 프로젝트의 여러 설비(기계/전기/토건)를 가중평균으로 통합 환산")

    p1, p2 = st.columns([1, 1])
    total_cost = p1.number_input("💰 총 투자비 (억원)", 0.0, 1000000.0, 1000.0, step=10.0)
    base_period = p2.text_input("기준 시점", "202001")
    target_period = st.text_input("목표 시점", "202601")

    st.markdown("##### 🧩 설비 구성")
    st.caption("각 설비 구성비를 입력하세요 (합계 100%)")

    # 기본 포트폴리오 예시
    default_portfolio = pd.DataFrame([
        {"설비": "펌프", "ITEM_CODE": "", "비중(%)": 30.0},
        {"설비": "변압기", "ITEM_CODE": "", "비중(%)": 20.0},
        {"설비": "시멘트", "ITEM_CODE": "", "비중(%)": 30.0},
        {"설비": "케이블", "ITEM_CODE": "", "비중(%)": 20.0},
    ])

    # 사용자가 카탈로그에서 골라 채우도록 지원
    if not use_demo and os.getenv("ECOS_API_KEY"):
        catalog_all = get_catalog(api_key=os.getenv("ECOS_API_KEY"))
        if catalog_all is not None and len(catalog_all) > 0:
            with st.expander("➕ ECOS 카탈로그에서 빠르게 추가"):
                c1, c2, c3 = st.columns([2, 1, 1])
                kw = c1.text_input("품목 검색", key="port_search", placeholder="예: 펌프")
                pct = c2.number_input("비중(%)", 0.0, 100.0, 10.0, step=1.0, key="port_pct")
                if kw.strip():
                    m = catalog_all[catalog_all["ITEM_NAME"].astype(str).str.contains(kw.strip(), na=False)]
                    if len(m) > 0:
                        opts = m.apply(lambda r: f"{r['ITEM_NAME']} [{r['ITEM_CODE']}]", axis=1).tolist()
                        sel = st.selectbox("선택", opts, key="port_sel")
                        idx = opts.index(sel)
                        if c3.button("추가", use_container_width=True):
                            new_row = pd.DataFrame([{
                                "설비": str(m.iloc[idx]["ITEM_NAME"]),
                                "ITEM_CODE": str(m.iloc[idx]["ITEM_CODE"]),
                                "비중(%)": pct,
                            }])
                            if "portfolio_df" in st.session_state:
                                st.session_state["portfolio_df"] = pd.concat(
                                    [st.session_state["portfolio_df"], new_row], ignore_index=True,
                                )
                            else:
                                st.session_state["portfolio_df"] = pd.concat(
                                    [default_portfolio, new_row], ignore_index=True,
                                )
                            st.rerun()

    portfolio_df = st.data_editor(
        st.session_state.get("portfolio_df", default_portfolio),
        num_rows="dynamic",
        column_config={
            "설비": st.column_config.TextColumn("설비", required=True),
            "ITEM_CODE": st.column_config.TextColumn("ECOS 코드", help="비우면 자동 매칭 시도"),
            "비중(%)": st.column_config.NumberColumn("비중(%)", min_value=0, max_value=100, step=1.0),
        },
        use_container_width=True,
        key="portfolio_editor",
    )
    st.session_state["portfolio_df"] = portfolio_df

    total_pct = portfolio_df["비중(%)"].sum()
    if abs(total_pct - 100) > 0.5:
        st.warning(f"⚠️ 비중 합계: {total_pct:.1f}% (100%가 되도록 조정 권장)")
    else:
        st.success(f"✅ 비중 합계: {total_pct:.1f}%")

    if st.button("🚀 포트폴리오 환산 실행", type="primary", key="port_btn"):
        if not use_demo and not os.getenv("ECOS_API_KEY"):
            st.error("LIVE 모드에서는 ECOS Key 필요")
        else:
            try:
                client = get_client()
                catalog_p = get_catalog(api_key=os.getenv("ECOS_API_KEY")) if not use_demo else None

                results = []
                for _, row in portfolio_df.iterrows():
                    name = str(row["설비"])
                    code = str(row["ITEM_CODE"]).strip()
                    pct = float(row["비중(%)"])

                    # 코드 비어있으면 자동 매칭
                    if not code and catalog_p is not None:
                        from utils.ecos_catalog import auto_match_code
                        best, _ = auto_match_code(name, catalog_p)
                        if best:
                            code = best["code"]
                            name = f"{name} → {best['name']}"

                    if not code:
                        results.append({
                            "설비": name, "코드": "없음", "비중(%)": pct,
                            "기준 PPI": None, "목표 PPI": None, "보정계수": None,
                            "소요금액(억)": total_cost * pct / 100,
                            "환산금액(억)": None, "상태": "❌ 코드 매칭 실패",
                        })
                        continue
                    try:
                        base_p = client.get_ppi_at(code, base_period)
                        target_p = client.get_ppi_at(code, target_period)
                        factor = target_p / base_p
                        allocated = total_cost * pct / 100
                        adj = allocated * factor
                        results.append({
                            "설비": name, "코드": code, "비중(%)": pct,
                            "기준 PPI": round(base_p, 2),
                            "목표 PPI": round(target_p, 2),
                            "보정계수": round(factor, 4),
                            "소요금액(억)": round(allocated, 2),
                            "환산금액(억)": round(adj, 2),
                            "상태": "✅",
                        })
                    except Exception as e:
                        results.append({
                            "설비": name, "코드": code, "비중(%)": pct,
                            "기준 PPI": None, "목표 PPI": None, "보정계수": None,
                            "소요금액(억)": total_cost * pct / 100,
                            "환산금액(억)": None, "상태": f"❌ {str(e)[:30]}",
                        })

                rdf = pd.DataFrame(results)
                st.session_state["port_results"] = rdf

                # 통합 결과 KPI
                successful = rdf[rdf["상태"] == "✅"]
                if len(successful) > 0:
                    total_allocated = float(successful["소요금액(억)"].sum())
                    total_adj = float(successful["환산금액(억)"].sum())
                    blended_factor = total_adj / total_allocated if total_allocated > 0 else 1.0
                    delta = total_adj - total_allocated

                    k1, k2, k3, k4 = st.columns(4)
                    k1.markdown(kpi_card(
                        "원 투자비", f"{total_allocated:,.1f} 억",
                        delta=f"{len(successful)}개 설비", icon="💼",
                    ), unsafe_allow_html=True)
                    k2.markdown(kpi_card(
                        "블렌드 보정계수", f"{blended_factor:.4f}",
                        delta=f"{(blended_factor-1)*100:+.2f}%",
                        delta_type="up" if blended_factor > 1 else "down", icon="⚖️",
                    ), unsafe_allow_html=True)
                    k3.markdown(kpi_card(
                        "증감액", f"{delta:+,.1f} 억",
                        delta=f"{base_period} → {target_period}",
                        delta_type="up" if delta > 0 else "down", icon="📊",
                    ), unsafe_allow_html=True)
                    k4.markdown(kpi_card(
                        "통합 환산금액", f"{total_adj:,.1f} 억",
                        delta="포트폴리오 기준",
                        delta_type="neutral", icon="🎯", highlight=True,
                    ), unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)
                st.dataframe(rdf, use_container_width=True, hide_index=True)

                # 도넛 차트 (구성비)
                if len(successful) > 0:
                    d1, d2 = st.columns(2)
                    with d1:
                        fig_pie = px.pie(
                            successful, values="소요금액(억)", names="설비",
                            hole=0.5, title="💼 투자비 구성비",
                            color_discrete_sequence=SERIES_COLORS,
                        )
                        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
                        fig_pie.update_layout(height=380)
                        st.plotly_chart(fig_pie, use_container_width=True)
                    with d2:
                        fig_cmp = go.Figure()
                        fig_cmp.add_trace(go.Bar(
                            name="원금", x=successful["설비"],
                            y=successful["소요금액(억)"],
                            marker_color=POSCO_COLORS["neutral_500"],
                        ))
                        fig_cmp.add_trace(go.Bar(
                            name="환산금액", x=successful["설비"],
                            y=successful["환산금액(억)"],
                            marker_color=POSCO_COLORS["primary"],
                        ))
                        fig_cmp.update_layout(
                            title="💹 설비별 원금 vs 환산",
                            barmode="group", height=380,
                            yaxis_title="억원",
                        )
                        st.plotly_chart(fig_cmp, use_container_width=True)

                # 내보내기
                ex1, ex2 = st.columns(2)
                xlsx = to_excel_bytes({"포트폴리오 환산": rdf})
                ex1.download_button("📊 Excel", xlsx,
                                    f"포트폴리오_{base_period}_{target_period}.xlsx",
                                    use_container_width=True)
                try:
                    pdf_bytes = generate_pdf_report(
                        title="포트폴리오 투자비 환산 리포트",
                        summary={
                            "총 원 투자비": f"{total_allocated:,.1f} 억원",
                            "통합 환산금액": f"{total_adj:,.1f} 억원",
                            "블렌드 보정계수": f"{blended_factor:.4f}",
                            "기준 시점": base_period,
                            "목표 시점": target_period,
                            "설비 수": f"{len(successful)}개",
                        },
                        body_text=f"본 리포트는 {len(successful)}개 설비 포트폴리오를 "
                                  f"{base_period}에서 {target_period}로 환산한 결과입니다.",
                        table_df=rdf,
                    )
                    ex2.download_button("📄 PDF", pdf_bytes,
                                        f"포트폴리오_{base_period}_{target_period}.pdf",
                                        "application/pdf", use_container_width=True)
                except Exception as e:
                    ex2.caption(f"PDF 생성 실패: {e}")

            except Exception as e:
                st.error(f"실행 오류: {e}")


# ═══════════════════════════════════════════
# Tab 6: 히트맵 & 상관관계
# ═══════════════════════════════════════════
with tab_heat:
    st.markdown(section_title("🗺️ 다품목 × 연도 히트맵 + 상관관계 매트릭스"), unsafe_allow_html=True)
    st.caption("여러 품목의 연도별 변동률을 매트릭스로, 품목 간 동조 패턴을 상관계수로 표현")

    if "multi_series" not in st.session_state or not st.session_state["multi_series"]:
        st.info(
            "👉 **Tab 3 (다중 설비 비교)** 에서 먼저 품목들을 선택하고 "
            "비교 차트를 생성하세요. 그 데이터를 여기서 히트맵으로 볼 수 있습니다."
        )
    else:
        series_dict = st.session_state["multi_series"]

        # 연도별 평균 PPI 매트릭스
        rows = []
        for name, s in series_dict.items():
            df = pd.DataFrame({"TIME": s.index, "PPI": s.values})
            df["YEAR"] = df["TIME"].astype(str).str[:4].astype(int)
            yr = df.groupby("YEAR")["PPI"].mean()
            yoy = yr.pct_change() * 100
            for year, val in yoy.items():
                if not pd.isna(val):
                    rows.append({"품목": name, "연도": int(year), "YoY(%)": round(float(val), 2)})
        hm = pd.DataFrame(rows)

        if len(hm) == 0:
            st.warning("히트맵 데이터 부족")
        else:
            # 피벗해서 히트맵
            pivot = hm.pivot(index="품목", columns="연도", values="YoY(%)")
            fig_h = px.imshow(
                pivot, color_continuous_scale=[[0, POSCO_COLORS["success"]],
                                                 [0.5, "#F8FAFC"],
                                                 [1, POSCO_COLORS["danger"]]],
                aspect="auto", text_auto=".1f",
                title="🔥 품목별 연도 변동률 히트맵 (YoY %)",
                color_continuous_midpoint=0,
            )
            fig_h.update_layout(height=max(300, 50 * len(pivot)))
            st.plotly_chart(fig_h, use_container_width=True)

            # 상관계수 매트릭스
            st.markdown(section_title("🔗 품목 간 가격 동조 상관계수"), unsafe_allow_html=True)
            df_wide = pd.DataFrame(series_dict)
            df_wide = df_wide.apply(pd.to_numeric, errors="coerce")
            corr = df_wide.corr()

            fig_c = px.imshow(
                corr, color_continuous_scale="RdBu_r",
                zmin=-1, zmax=1, text_auto=".2f",
                title="상관계수 매트릭스 (1에 가까울수록 동조)",
            )
            fig_c.update_layout(height=max(350, 50 * len(corr)))
            st.plotly_chart(fig_c, use_container_width=True)

            st.caption(
                "💡 해석: 상관계수가 높은 품목끼리는 가격이 같은 방향으로 움직입니다. "
                "포트폴리오 구성 시 상관이 낮은 품목을 섞으면 전체 변동 리스크가 줄어듭니다."
            )


# ═══════════════════════════════════════════
# Tab 7: 공유 / 내보내기 가이드
# ═══════════════════════════════════════════
with tab_share:
    st.markdown(section_title("🔗 결과 공유 & 내보내기"), unsafe_allow_html=True)

    st.markdown("""
    이 앱의 결과를 **동료에게 공유**하거나 **문서로 저장**하는 방법을 안내합니다.
    """)

    with st.container():
        st.markdown("#### 📋 방법 1 — URL 링크 공유")
        st.markdown("""
        Tab 2 (설비별 PPI 조회)에서 조회한 결과는 URL 파라미터로 저장할 수 있습니다.

        **포맷**: `?code={ITEM_CODE}&from=YYYYMM&to=YYYYMM`

        예:
        """)
        st.code(
            "https://your-app.streamlit.app/?code=41001&from=202001&to=202601",
            language="text",
        )
        st.caption("링크를 열면 동일한 품목/기간으로 바로 조회됩니다.")

    st.divider()

    with st.container():
        st.markdown("#### 📄 방법 2 — PDF / Excel 내보내기")
        st.markdown("""
        각 탭 하단의 **다운로드 버튼** 으로 바로 받을 수 있습니다.

        - **Tab 1 AI Agent 환산** → PDF 리포트 + Excel 데이터
        - **Tab 2 설비별 PPI 조회** → CSV, Excel
        - **Tab 3 다중 설비 비교** → Excel 요약
        - **Tab 5 포트폴리오 환산** → PDF 리포트 + Excel
        """)

    st.divider()

    with st.container():
        st.markdown("#### 📸 방법 3 — 스크린샷 / 차트 이미지")
        st.markdown("""
        각 Plotly 차트 오른쪽 위 카메라 아이콘 📷 으로 PNG 이미지 저장 가능.
        """)

    st.divider()

    # 세션 상태 요약
    with st.container():
        st.markdown("#### 💾 현재 세션 요약")
        session_summary = {
            "실행 모드": "DEMO" if use_demo else "LIVE (ECOS)",
            "ECOS Key": "✅ 설정됨" if os.getenv("ECOS_API_KEY") else "❌ 없음",
            "카탈로그": f"{len(get_catalog(api_key=os.getenv('ECOS_API_KEY'))):,}개"
                         if (not use_demo and os.getenv("ECOS_API_KEY")) else "DEMO",
            "LLM": llm_provider if not use_demo else "DEMO (None)",
            "Tab 3 비교 결과": "✅ 저장됨" if "multi_series" in st.session_state else "❌ 없음",
            "Tab 5 포트폴리오": "✅ 저장됨" if "port_results" in st.session_state else "❌ 없음",
        }
        st.json(session_summary)


# ═══════════════════════════════════════════
# 푸터
# ═══════════════════════════════════════════
st.divider()
st.markdown(
    f"""
    <div style="text-align:center; color:#94A3B8; font-size:12px; padding:20px 0;">
        🏭 <b>POSCO 투자비 물가보정 AI Agent v8</b> · 한국은행 ECOS API 기반 · 교육용 데모
        <br>
        <span style="font-size:11px;">© 2026 포스코 투자엔지니어링실</span>
    </div>
    """,
    unsafe_allow_html=True,
)
