"""
포스코 투자엔지니어링실 - 물가보정 AI Agent
Streamlit 데모 앱

실행 모드:
  1) 🎬 DEMO 모드: API 키 없이 가상 데이터로 전체 기능 시연
  2) 🏦 LIVE 모드: 실제 ECOS API + OpenAI 호출
"""
import os
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from data.ppi_categories import EQUIPMENT_CATEGORIES, get_all_items
from utils.ecos_client import ECOSClient
from utils.demo_data import DemoECOSClient
from agents.ppi_agent import run_ppi_agent

# ═══════════════════════════════════════════
# 페이지 설정
# ═══════════════════════════════════════════
st.set_page_config(
    page_title="물가보정 AI Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 커스텀 CSS
st.markdown("""
<style>
    .main-header {
        padding: 1.2rem;
        background: linear-gradient(135deg, #005EB8 0%, #003d7a 100%);
        border-radius: 10px;
        color: white;
        margin-bottom: 1rem;
    }
    .main-header h1 { color: white; margin: 0; font-size: 1.8rem; }
    .main-header p { color: #cce0f4; margin: 0.3rem 0 0 0; }
    .demo-badge {
        background: #ff6b35;
        color: white;
        padding: 0.2rem 0.6rem;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: bold;
    }
    .live-badge {
        background: #10b981;
        color: white;
        padding: 0.2rem 0.6rem;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: bold;
    }
    div[data-testid="metric-container"] {
        background: #f8f9fa;
        padding: 0.8rem;
        border-radius: 8px;
        border-left: 4px solid #005EB8;
    }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════
# 사이드바 - 모드 선택 및 API 키
# ═══════════════════════════════════════════
with st.sidebar:
    st.markdown("### ⚙️ 실행 모드")
    mode = st.radio(
        "모드를 선택하세요",
        ["🎬 DEMO 모드 (API 키 불필요)", "🏦 LIVE 모드 (실제 API 호출)"],
        help="DEMO 모드는 가상 데이터로 전체 기능을 시연합니다.",
    )
    use_demo = mode.startswith("🎬")

    st.divider()

    if use_demo:
        st.success("✅ DEMO 모드\n\n가상 PPI 데이터로 동작합니다. API 키 없이 모든 기능을 체험할 수 있습니다.")
        llm_provider = "none"
    else:
        st.markdown("### 🔑 API 키 입력")

        # ECOS 키
        try:
            default_ecos = st.secrets["ECOS_API_KEY"]
        except Exception:
            default_ecos = os.getenv("ECOS_API_KEY", "")

        ecos_key = st.text_input("ECOS API Key", type="password", value=default_ecos)
        if ecos_key:
            os.environ["ECOS_API_KEY"] = ecos_key

        st.divider()
        st.markdown("### 🧠 LLM 선택 (선택)")
        llm_provider = st.radio(
            "자연어 파싱에 사용할 LLM",
            ["🆓 Gemini (무료, 추천)", "💰 OpenAI", "📐 사용 안 함 (규칙 기반)"],
            help="Gemini는 무료 할당량이 넉넉합니다. 미사용 시 규칙 기반 파서가 동작합니다.",
        )

        # Gemini 키
        if llm_provider.startswith("🆓"):
            try:
                default_gemini = st.secrets["GEMINI_API_KEY"]
            except Exception:
                default_gemini = os.getenv("GEMINI_API_KEY", "")
            gemini_key = st.text_input("Gemini API Key", type="password", value=default_gemini,
                                        help="https://aistudio.google.com/apikey 에서 무료 발급")
            if gemini_key:
                os.environ["GEMINI_API_KEY"] = gemini_key
            llm_provider = "gemini"

        # OpenAI 키
        elif llm_provider.startswith("💰"):
            try:
                default_openai = st.secrets["OPENAI_API_KEY"]
            except Exception:
                default_openai = os.getenv("OPENAI_API_KEY", "")
            openai_key = st.text_input("OpenAI API Key", type="password", value=default_openai)
            if openai_key:
                os.environ["OPENAI_API_KEY"] = openai_key
            llm_provider = "openai"
        else:
            llm_provider = "none"

        st.markdown("##### 🔗 키 발급 링크")
        st.markdown("- [ECOS API](https://ecos.bok.or.kr/api/) (무료)")
        st.markdown("- [Gemini API](https://aistudio.google.com/apikey) 🆓 **무료 추천**")
        st.markdown("- [OpenAI API](https://platform.openai.com/api-keys) (유료)")

    st.divider()
    st.markdown("### 📖 소개")
    st.markdown("""
    **투자비 물가보정 AI Agent**

    신규 설비 투자 검토 시 과거 유사 프로젝트의 투자비를
    현재 시점으로 자동 환산합니다.

    - 🏭 기계 / ⚡ 전기 / 🏗️ 토건 / 🔧 계측 설비별 세분화
    - 📈 PPI 시계열 추이 그래프
    - 🤖 자연어 요청 → AI Agent 자동 처리
    """)
    st.caption("📚 포스코 투자엔지니어링실 교육용 데모")


# ═══════════════════════════════════════════
# 메인 헤더
# ═══════════════════════════════════════════
badge = '<span class="demo-badge">🎬 DEMO</span>' if use_demo else '<span class="live-badge">🏦 LIVE</span>'
st.markdown(f"""
<div class="main-header">
    <h1>📊 투자비 물가보정 AI Agent {badge}</h1>
    <p>한국은행 ECOS API + AI Agent | 포스코 투자엔지니어링실 교육용 데모</p>
</div>
""", unsafe_allow_html=True)


def get_client():
    """현재 모드에 맞는 ECOS 클라이언트 반환"""
    if use_demo:
        return DemoECOSClient()
    return ECOSClient()


# ═══════════════════════════════════════════
# 4개 탭
# ═══════════════════════════════════════════
tab1, tab2, tab3, tab4 = st.tabs([
    "🤖 AI Agent 환산",
    "🔍 설비별 PPI 조회",
    "📈 다중 설비 비교",
    "🧮 수동 계산기",
])

# ═══════════════════════════════════════════
# Tab 1: AI Agent
# ═══════════════════════════════════════════
with tab1:
    st.subheader("🤖 자연어로 물가보정 요청")
    st.caption("자연어로 입력하면 Agent가 ① 정보 추출 → ② 적합 품목 선택 → ③ PPI 조회 → ④ 환산 → ⑤ 보고서 생성까지 자동 수행")

    col_ex, _ = st.columns([2, 1])
    with col_ex:
        examples = [
            "(직접 입력)",
            "2020년 1월 800억원 압연기 설비를 2026년 1월 기준으로 환산",
            "2018년 3월 변압기 1,200억원을 2026년 1월 현재가로",
            "2019년 6월 콘크리트 공사 500억원의 2026년 환산금액은?",
            "2017년 5월 크레인 300억원을 2026년 1월 기준으로",
            "2020년 7월 케이블 설치 150억원 2026년 1월 환산",
        ]
        selected_ex = st.selectbox("💡 예시 선택", examples)

    default_query = "" if selected_ex == "(직접 입력)" else selected_ex
    user_query = st.text_area(
        "요청 내용",
        value=default_query,
        height=80,
        placeholder="예: 2020년 1월 코크스 설비 800억원을 2026년 1월 기준으로 환산해줘",
    )

    run_btn = st.button("🚀 AI Agent 실행", type="primary", use_container_width=True)

    if run_btn:
        if not user_query.strip():
            st.warning("요청 내용을 입력해 주세요.")
        elif not use_demo and not os.getenv("ECOS_API_KEY"):
            st.error("⚠️ LIVE 모드에서는 ECOS API Key가 필요합니다. 사이드바에서 입력해 주세요.")
        else:
            with st.spinner("🤖 AI Agent가 분석 중입니다..."):
                try:
                    result = run_ppi_agent(user_query, use_demo=use_demo, llm_provider=llm_provider)

                    # 데이터 소스 표시
                    st.info(f"데이터 소스: {result['data_source']} | "
                            f"🧠 {result['used_llm']}")

                    # 핵심 지표 4개
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("원금", f"{result['parsed']['original_cost']:,.0f} 억")
                    c2.metric("보정계수", f"{result['factor']:.4f}")
                    c3.metric("변동률", f"{(result['factor']-1)*100:+.2f}%")
                    c4.metric(
                        "환산금액",
                        f"{result['adjusted_cost']:,.1f} 억",
                        f"{result['adjusted_cost']-result['parsed']['original_cost']:+,.1f}",
                    )

                    st.divider()

                    # PPI 변동 차트 (기준~비교 구간)
                    try:
                        client = get_client()
                        base = result["parsed"]["base_period"]
                        target = result["parsed"]["target_period"]
                        code = result["parsed"]["recommended_code"]
                        df_trend = client.get_ppi(code, base, target)
                        df_trend["TIME_DT"] = pd.to_datetime(df_trend["TIME"], format="%Y%m")

                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=df_trend["TIME_DT"], y=df_trend["DATA_VALUE"],
                            mode="lines+markers", name="PPI",
                            line=dict(color="#005EB8", width=2.5),
                            fill="tozeroy", fillcolor="rgba(0,94,184,0.1)",
                        ))
                        fig.add_hline(y=result["base_ppi"], line_dash="dot", line_color="orange",
                                      annotation_text=f"기준 {result['base_ppi']:.2f}")
                        fig.add_hline(y=result["target_ppi"], line_dash="dot", line_color="red",
                                      annotation_text=f"비교 {result['target_ppi']:.2f}")
                        fig.update_layout(
                            title=f"📈 {result['item_info']['full_path']} PPI 추이",
                            xaxis_title="시점", yaxis_title="PPI (2020=100)",
                            height=380, hovermode="x unified",
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    except Exception as e:
                        st.warning(f"추이 차트 생성 실패: {e}")

                    # 보고서
                    st.markdown(result["report"])

                    with st.expander("🔧 파싱 상세 정보"):
                        st.json(result["parsed"])

                except Exception as e:
                    st.error(f"❌ 실행 오류: {e}")
                    st.exception(e)


# ═══════════════════════════════════════════
# Tab 2: 설비별 PPI 조회
# ═══════════════════════════════════════════
with tab2:
    st.subheader("🔍 설비 카테고리별 PPI 시계열 조회")
    st.caption("대분류 → 중분류 → 세부 품목 순으로 선택해 해당 설비의 PPI 추이를 확인")

    col1, col2 = st.columns(2)
    with col1:
        major = st.selectbox("1️⃣ 대분류", list(EQUIPMENT_CATEGORIES.keys()))
    with col2:
        mid_options = list(EQUIPMENT_CATEGORIES[major].keys())
        mid = st.selectbox("2️⃣ 중분류", mid_options)

    sub_items = EQUIPMENT_CATEGORIES[major][mid]
    sub_labels = [f"{it['name']} — {it['desc']}" for it in sub_items]
    sub_idx = st.selectbox(
        "3️⃣ 세부 품목",
        range(len(sub_labels)),
        format_func=lambda i: sub_labels[i],
    )
    selected_item = sub_items[sub_idx]

    st.info(f"📌 선택: **{selected_item['name']}** | ECOS 코드: `{selected_item['code']}` | {selected_item['desc']}")

    col_a, col_b = st.columns(2)
    with col_a:
        start = st.text_input("시작 (YYYYMM)", "201501")
    with col_b:
        end = st.text_input("종료 (YYYYMM)", "202612")

    if st.button("📊 조회 및 시각화", type="primary", key="tab2_btn"):
        try:
            with st.spinner("데이터 조회 중..."):
                client = get_client()
                df = client.get_ppi(selected_item["code"], start, end)
                df["TIME_DT"] = pd.to_datetime(df["TIME"], format="%Y%m")

            # 요약 지표
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("데이터 포인트", f"{len(df)}개")
            c2.metric("최저 PPI", f"{df['DATA_VALUE'].min():.2f}")
            c3.metric("최고 PPI", f"{df['DATA_VALUE'].max():.2f}")
            change = (df["DATA_VALUE"].iloc[-1] / df["DATA_VALUE"].iloc[0] - 1) * 100
            c4.metric("기간 변동률", f"{change:+.2f}%")

            # 메인 차트
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df["TIME_DT"], y=df["DATA_VALUE"],
                mode="lines+markers", name=selected_item["name"],
                line=dict(color="#005EB8", width=2.5),
                fill="tozeroy", fillcolor="rgba(0,94,184,0.1)",
            ))
            fig.add_hline(y=100, line_dash="dash", line_color="red",
                          annotation_text="2020년 기준 (100)")
            fig.update_layout(
                title=f"📈 {selected_item['name']} PPI 추이",
                xaxis_title="시점", yaxis_title="PPI (2020=100)",
                height=500, hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True)

            # 연간 변동률 바차트
            df["YEAR"] = df["TIME_DT"].dt.year
            yearly = df.groupby("YEAR")["DATA_VALUE"].mean().reset_index()
            yearly["YoY(%)"] = yearly["DATA_VALUE"].pct_change() * 100
            yearly = yearly.dropna()

            if len(yearly) > 0:
                fig_yoy = px.bar(
                    yearly, x="YEAR", y="YoY(%)",
                    color="YoY(%)", color_continuous_scale="RdYlGn_r",
                    title="📊 연도별 전년 대비 변동률 (YoY)",
                )
                fig_yoy.update_layout(height=350)
                st.plotly_chart(fig_yoy, use_container_width=True)

            # 원본 데이터
            with st.expander("📋 원본 데이터"):
                st.dataframe(df[["TIME", "ITEM_NAME1", "DATA_VALUE"]], use_container_width=True)
                csv = df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "📥 CSV 다운로드", csv,
                    f"PPI_{selected_item['name']}_{start}_{end}.csv",
                    "text/csv",
                )
        except Exception as e:
            st.error(f"❌ 조회 실패: {e}")


# ═══════════════════════════════════════════
# Tab 3: 다중 설비 비교
# ═══════════════════════════════════════════
with tab3:
    st.subheader("📈 여러 설비 PPI 추이 비교")
    st.caption("기계 vs 전기 vs 토건 설비의 물가 변동을 한 화면에서 비교 — 투자 우선순위 판단에 활용")

    all_items = get_all_items()
    # 종합지수는 기본 선택에서 제외
    default_candidates = [i for i, it in enumerate(all_items) if it["major"] != "📊 종합 지수"]
    item_labels = [f"{it['major'].split()[0]} {it['name']}" for it in all_items]

    selected_indices = st.multiselect(
        "비교할 품목 선택 (2~6개 권장)",
        range(len(item_labels)),
        default=default_candidates[:4] if len(default_candidates) >= 4 else default_candidates,
        format_func=lambda i: item_labels[i],
    )

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        start_m = st.text_input("시작", "201801", key="multi_start")
    with col_b:
        end_m = st.text_input("종료", "202612", key="multi_end")
    with col_c:
        normalize = st.checkbox("시작점=100 정규화", value=True,
                                 help="체크 시 각 시계열의 시작값을 100으로 맞춰 변동 폭만 비교")

    if st.button("📊 비교 차트 생성", type="primary", key="tab3_btn"):
        if not selected_indices:
            st.warning("품목을 1개 이상 선택해 주세요.")
        else:
            try:
                client = get_client()
                fig = go.Figure()
                colors = px.colors.qualitative.Set2
                summary_data = []
                progress = st.progress(0, text="데이터 조회 중...")

                for idx, item_idx in enumerate(selected_indices):
                    item = all_items[item_idx]
                    try:
                        df = client.get_ppi(item["code"], start_m, end_m)
                        df["TIME_DT"] = pd.to_datetime(df["TIME"], format="%Y%m")

                        y_vals = df["DATA_VALUE"].values
                        if normalize and y_vals[0] != 0:
                            y_plot = y_vals / y_vals[0] * 100
                        else:
                            y_plot = y_vals

                        fig.add_trace(go.Scatter(
                            x=df["TIME_DT"], y=y_plot,
                            mode="lines", name=item["name"],
                            line=dict(color=colors[idx % len(colors)], width=2.2),
                        ))
                        change = (y_vals[-1] / y_vals[0] - 1) * 100
                        summary_data.append({
                            "품목": item["name"],
                            "카테고리": item["major"],
                            "시작 PPI": round(float(y_vals[0]), 2),
                            "종료 PPI": round(float(y_vals[-1]), 2),
                            "변동률(%)": round(change, 2),
                        })
                    except Exception as e:
                        st.warning(f"⚠️ {item['name']}: {e}")
                    progress.progress((idx + 1) / len(selected_indices),
                                      text=f"{idx + 1}/{len(selected_indices)} 완료")

                progress.empty()
                title = "📊 설비별 PPI 추이 비교"
                title += " (시작점=100 정규화)" if normalize else " (원본 지수)"
                if normalize:
                    fig.add_hline(y=100, line_dash="dash", line_color="gray",
                                  annotation_text="시작점")
                fig.update_layout(
                    title=title,
                    xaxis_title="시점",
                    yaxis_title="정규화 지수" if normalize else "PPI (2020=100)",
                    height=550, hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                )
                st.plotly_chart(fig, use_container_width=True)

                # 변동률 비교
                if summary_data:
                    st.markdown("### 📊 기간 변동률 요약")
                    df_sum = pd.DataFrame(summary_data).sort_values("변동률(%)", ascending=False)
                    st.dataframe(df_sum, use_container_width=True, hide_index=True)

                    fig_bar = px.bar(
                        df_sum, x="품목", y="변동률(%)",
                        color="변동률(%)", color_continuous_scale="RdYlGn_r",
                        title="💹 기간 누적 변동률 비교 (내림차순)",
                        text="변동률(%)",
                    )
                    fig_bar.update_traces(texttemplate="%{text:+.1f}%", textposition="outside")
                    fig_bar.update_layout(height=420)
                    st.plotly_chart(fig_bar, use_container_width=True)

                    # 인사이트
                    top = df_sum.iloc[0]
                    bot = df_sum.iloc[-1]
                    st.markdown(f"""
                    #### 💡 분석 인사이트
                    - 가장 큰 상승: **{top['품목']}** ({top['변동률(%)']:+.2f}%)
                    - 가장 작은 상승: **{bot['품목']}** ({bot['변동률(%)']:+.2f}%)
                    - 품목 간 변동률 격차: **{top['변동률(%)'] - bot['변동률(%)']:.2f}%p**
                    - 👉 투자 의사결정 시 설비별 물가 민감도 차이를 감안해 예비비 배분 검토 필요
                    """)
            except Exception as e:
                st.error(f"❌ 오류: {e}")


# ═══════════════════════════════════════════
# Tab 4: 수동 계산기
# ═══════════════════════════════════════════
with tab4:
    st.subheader("🧮 PPI 수동 환산 계산기")
    st.caption("API 호출 없이 PPI 값을 이미 알고 있을 때 빠르게 계산")

    c1, c2, c3 = st.columns(3)
    cost = c1.number_input("원금 (억원)", value=800.0, step=10.0, min_value=0.0)
    base = c2.number_input("기준시점 PPI", value=95.0, step=0.1, min_value=0.1)
    target = c3.number_input("목표시점 PPI", value=120.0, step=0.1, min_value=0.1)

    if base > 0:
        factor = target / base
        adjusted = cost * factor

        st.divider()
        m1, m2, m3 = st.columns(3)
        m1.metric("보정계수", f"{factor:.4f}")
        m2.metric("변동률", f"{(factor - 1) * 100:+.2f}%")
        m3.metric("환산금액", f"{adjusted:,.2f} 억원",
                  f"{adjusted - cost:+,.2f}")

        # 시각화
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=["원금", "환산금액"],
            y=[cost, adjusted],
            text=[f"{cost:,.1f}", f"{adjusted:,.1f}"],
            textposition="outside",
            marker_color=["#94a3b8", "#005EB8"],
        ))
        fig.update_layout(
            title="💰 원금 vs 환산금액",
            yaxis_title="억원", height=350,
        )
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("📐 계산식"):
            st.latex(r"\text{환산금액} = \text{원금} \times \frac{\text{목표시점 PPI}}{\text{기준시점 PPI}}")
            st.code(f"{cost:,.2f} × ({target:.2f} / {base:.2f}) = {cost:,.2f} × {factor:.4f} = {adjusted:,.2f}",
                    language="text")


# ═══════════════════════════════════════════
# 푸터
# ═══════════════════════════════════════════
st.divider()
st.caption("""
⚠️ 본 도구는 교육/참고용 데모입니다. 실제 투자 결정 시 사내 표준 절차를 따르고 전문가 검토를 거치세요.
DEMO 모드의 데이터는 실제 PPI가 아닌 가상 시계열이며, LIVE 모드는 한국은행 ECOS 데이터를 사용합니다.
""")
