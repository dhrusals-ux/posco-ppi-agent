"""
🏭 POSCO 투자비 물가보정 AI Agent v8
ECOS API + AI Agent + 시나리오 분석 + 포트폴리오 환산 + 고급 시각화
"""
import os
import io
import re
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

from agents.ppi_agent import run_ppi_agent
from utils.ecos_client import ECOSClient
from utils.kosis_client import KOSISClient
from utils.construction_catalog import get_construction_catalog, catalog_to_options
from utils.ecos_catalog import get_catalog
from utils.forecast import forecast_index, MAX_HORIZON
from utils.monitor import build_monitor
from utils.batch_adjust import (
    read_table, guess_columns, suggest_matches, approval_blockers,
    run_batch, summarize, MAX_ROWS, fmt_eok, eok_unit,
    CONF_HIGH, CONF_MEDIUM, CONF_LOW, CONF_NONE, CONF_ICON,
)
from data.steel_plant_items import STEEL_PLANT_ITEMS, get_processes, get_all_items_flat
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
    """ECOS 클라이언트 (LIVE 전용)"""
    return ECOSClient()


def get_construction_client():
    """KOSIS(건설공사비지수) 클라이언트 (LIVE 전용) — 준비 중"""
    return KOSISClient()


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
    # 항상 LIVE(ECOS) 전용 — DEMO 제거
    use_demo = False
    st.session_state["use_demo"] = False

    st.markdown("### 데이터 연결")

    # ── ECOS 키: secrets 우선, 없으면 입력란 폴백 ──
    ecos_from_secrets = ""
    try:
        ecos_from_secrets = st.secrets["ECOS_API_KEY"]
    except Exception:
        ecos_from_secrets = os.getenv("ECOS_API_KEY", "")

    if ecos_from_secrets:
        # 배포 환경: 키가 이미 설정됨 → 사용자는 키를 몰라도 됨
        os.environ["ECOS_API_KEY"] = ecos_from_secrets.strip().strip('"').strip("'").strip()
        st.success("✅ 한국은행 ECOS 연결됨")
    else:
        # 로컬/미설정: 입력란 폴백
        st.info("ECOS 인증키가 설정되지 않았습니다. 아래에 입력하세요.")
        ecos_key = st.text_input(
            "ECOS API Key", type="password",
            help="관리자가 secrets에 등록하면 이 입력란은 사라집니다.",
        )
        if ecos_key:
            cleaned = ecos_key.strip().strip('"').strip("'").strip()
            os.environ["ECOS_API_KEY"] = cleaned

    # ── KOSIS 키 (건설공사비지수 / 공사비 보정) ──
    kosis_from_secrets = ""
    try:
        kosis_from_secrets = st.secrets["KOSIS_API_KEY"]
    except Exception:
        kosis_from_secrets = os.getenv("KOSIS_API_KEY", "")

    if kosis_from_secrets:
        os.environ["KOSIS_API_KEY"] = kosis_from_secrets.strip().strip('"').strip("'").strip()
        st.success("✅ KOSIS 연결됨 (공사비)")
    else:
        kosis_key = st.text_input(
            "KOSIS API Key (공사비)", type="password",
            help="건설공사비지수 조회용 · kosis.kr 공유서비스에서 무료 발급. 없으면 공사비 탭은 비활성화됩니다.",
        )
        if kosis_key:
            os.environ["KOSIS_API_KEY"] = kosis_key.strip().strip('"').strip("'").strip()

    st.divider()

    # ── LLM (자연어 파싱 고도화, 선택) ──
    st.markdown("### 자연어 파싱 LLM")
    st.caption("미설정 시 규칙 기반 파서로 동작합니다.")
    llm_choice = st.radio(
        "LLM 선택",
        ["📐 규칙 기반 (기본)", "🆓 Gemini", "💰 OpenAI"],
        label_visibility="collapsed",
    )
    if llm_choice.startswith("🆓"):
        try:
            default_gem = st.secrets["GEMINI_API_KEY"]
        except Exception:
            default_gem = os.getenv("GEMINI_API_KEY", "")
        if default_gem:
            os.environ["GEMINI_API_KEY"] = default_gem.strip().strip('"').strip("'")
            st.success("✅ Gemini 연결됨")
        else:
            gk = st.text_input("Gemini Key", type="password")
            if gk:
                os.environ["GEMINI_API_KEY"] = gk.strip().strip('"').strip("'")
        llm_provider = "gemini"
        gemini_model_choice = st.selectbox(
            "Gemini 모델",
            ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-flash-latest", "gemini-2.0-flash"],
            index=0,
            help="특정 모델이 차단될 경우 다른 모델로 전환하세요.",
        )
        os.environ["GEMINI_MODEL"] = gemini_model_choice
    elif llm_choice.startswith("💰"):
        try:
            default_oai = st.secrets["OPENAI_API_KEY"]
        except Exception:
            default_oai = os.getenv("OPENAI_API_KEY", "")
        if default_oai:
            os.environ["OPENAI_API_KEY"] = default_oai.strip().strip('"').strip("'")
            st.success("✅ OpenAI 연결됨")
        else:
            ok = st.text_input("OpenAI Key", type="password")
            if ok:
                os.environ["OPENAI_API_KEY"] = ok.strip().strip('"').strip("'")
        llm_provider = "openai"
    else:
        llm_provider = "none"

    st.divider()
    st.markdown("### ECOS 품목 카탈로그")
    if os.getenv("ECOS_API_KEY"):
        try:
            catalog = get_catalog(api_key=os.getenv("ECOS_API_KEY"))
            if catalog is not None and len(catalog) > 0:
                st.success(f"품목 **{len(catalog):,}개** 로드됨")
                if st.button("🔄 카탈로그 새로고침", use_container_width=True):
                    st.cache_data.clear()
                    st.rerun()
            else:
                st.warning("카탈로그 비어있음")
        except Exception as e:
            st.error(f"로드 실패: {e}")
    else:
        st.caption("ECOS 연결 후 품목 카탈로그가 표시됩니다.")

    st.divider()
    st.markdown("### 소개")
    st.caption(
        "**POSCO 투자엔지니어링실 투자비 물가보정 도구**\n\n"
        "한국은행 ECOS 생산자물가지수(PPI)로 과거 설비 투자비를 "
        "현재 시점 가치로 환산합니다."
    )
    st.markdown(live_badge("ECOS LIVE"), unsafe_allow_html=True)



# ═══════════════════════════════════════════
# 상단 Hero 헤더 + 실시간 PPI KPI
# ═══════════════════════════════════════════
st.markdown(
    hero_header(
        "POSCO 투자비 물가보정 시스템",
        "한국은행 ECOS 생산자물가지수(설비비) · 한국건설기술연구원 건설공사비지수(공사비) "
        "실시간 조회 기반 현재가치 환산 — 투자엔지니어링실 내부 검토용",
    ),
    unsafe_allow_html=True,
)

# ── 키 미설정 게이트: ECOS 연결 전에는 본문 차단 ──
if not os.getenv("ECOS_API_KEY"):
    st.warning(
        "🔌 **한국은행 ECOS 인증키가 설정되지 않았습니다.**\n\n"
        "왼쪽 사이드바에 키를 입력하거나, 배포 환경에서는 관리자가 "
        "`secrets.toml`(또는 Streamlit Cloud Secrets)에 `ECOS_API_KEY`를 등록해야 합니다.\n\n"
        "→ ECOS 인증키 무료 발급: https://ecos.bok.or.kr/api/"
    )
    st.stop()


# 상단 KPI 스트립 (총지수 현황)
def fetch_top_kpi():
    """ECOS 총지수 최신 데이터 → KPI 카드용"""
    if not os.getenv("ECOS_API_KEY"):
        return None
    try:
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
# 탭 정의 (11개)
# ═══════════════════════════════════════════
(tab_mon, tab_ai, tab_batch, tab_ppi, tab_cci, tab_multi, tab_scn,
 tab_port, tab_heat, tab_fcst, tab_share) = st.tabs([
    "품목 모니터링",
    "AI Agent 환산",
    "엑셀 일괄 보정",
    "설비별 PPI 조회",
    "공사비 물가보정",
    "다중 설비 비교",
    "시나리오 분석",
    "포트폴리오 환산",
    "히트맵 & 상관관계",
    "물가 예측",
    "공유/내보내기",
])


# ═══════════════════════════════════════════
# 공통 헬퍼: 기간 프리셋 버튼
# ═══════════════════════════════════════════
def period_preset_buttons(key_prefix: str, default_start="201501", default_end="202612"):
    """기간 프리셋 버튼 + 시작/종료 입력 (프리셋 클릭 시 즉시 반영)"""
    st.markdown("##### 기간 설정")

    start_key = f"{key_prefix}_start_input"
    end_key = f"{key_prefix}_end_input"

    # 최초 1회 초기값 세팅 (위젯 key 자체에 저장)
    if start_key not in st.session_state:
        st.session_state[start_key] = default_start
    if end_key not in st.session_state:
        st.session_state[end_key] = default_end

    today = datetime.now()

    def _ym(year, month):
        return f"{year:04d}{month:02d}"

    def _apply(preset_start, preset_end):
        """위젯 key에 직접 써서 다음 렌더에 즉시 반영되게 한다."""
        st.session_state[start_key] = preset_start
        st.session_state[end_key] = preset_end

    p1, p2, p3, p4, p5, p6 = st.columns(6)
    if p1.button("최근 1년", key=f"{key_prefix}_p1", use_container_width=True):
        _apply(_ym(today.year - 1, today.month), _ym(today.year, today.month))
        st.rerun()
    if p2.button("최근 3년", key=f"{key_prefix}_p3", use_container_width=True):
        _apply(_ym(today.year - 3, today.month), _ym(today.year, today.month))
        st.rerun()
    if p3.button("최근 5년", key=f"{key_prefix}_p5", use_container_width=True):
        _apply(_ym(today.year - 5, today.month), _ym(today.year, today.month))
        st.rerun()
    if p4.button("최근 10년", key=f"{key_prefix}_p10", use_container_width=True):
        _apply(_ym(today.year - 10, today.month), _ym(today.year, today.month))
        st.rerun()
    if p5.button("팬데믹 이후", key=f"{key_prefix}_p_covid", use_container_width=True):
        _apply("202001", _ym(today.year, today.month))
        st.rerun()
    if p6.button("전체(2010~)", key=f"{key_prefix}_p_all", use_container_width=True):
        _apply("201001", _ym(today.year, today.month))
        st.rerun()

    c1, c2 = st.columns(2)
    with c1:
        start = st.text_input("시작 (YYYYMM)", key=start_key)
    with c2:
        end = st.text_input("종료 (YYYYMM)", key=end_key)

    return start, end



# =========================================================
# Tab: \U0001F4E1 품목 모니터링 (철강 플랜트 공정별)
# =========================================================
with tab_mon:
    st.markdown(section_title("철강 플랜트 설비 품목 물가 모니터링"), unsafe_allow_html=True)
    st.caption(
        "한국은행 ECOS 생산자물가지수를 자동으로 불러와 공정별 주요 설비 품목의 월별 추이를 "
        "한눈에 확인합니다. **매월 ECOS 발표가 반영되므로 수동 업데이트가 필요 없습니다.**"
    )

    mon_catalog = get_catalog(api_key=os.getenv("ECOS_API_KEY"))
    if mon_catalog is None or len(mon_catalog) == 0:
        st.error("ECOS 카탈로그 로드 실패 — 사이드바에서 인증키를 확인하세요.")
    else:
        csel1, csel2 = st.columns([2, 1])
        with csel1:
            proc_options = ["\U0001F310 전체"] + get_processes()
            sel_proc = st.radio("공정 선택", proc_options, horizontal=True, key="mon_proc")
        with csel2:
            mon_months = st.selectbox("조회 기간", [12, 24, 36, 60], index=1,
                                      format_func=lambda x: f"최근 {x}개월", key="mon_months")

        # 대상 품목 결정
        if sel_proc == "\U0001F310 전체":
            target_items, dedup = [], set()
            for _it in get_all_items_flat():
                if _it["label"] in dedup:
                    continue
                dedup.add(_it["label"])
                target_items.append(_it)
        else:
            target_items = STEEL_PLANT_ITEMS.get(sel_proc, [])

        st.caption(f"\U0001F4CC 대상 품목 **{len(target_items)}개** · 공정: {sel_proc}")

        _end = datetime.now().strftime("%Y%m")
        _start_dt = datetime.now().replace(day=1) - pd.Timedelta(days=31 * (mon_months + 2))
        _start = _start_dt.strftime("%Y%m")

        if st.button("\U0001F4E1 모니터링 실행", type="primary", use_container_width=True, key="mon_run"):
            with st.spinner(f"ECOS에서 {len(target_items)}개 품목을 조회하는 중..."):
                try:
                    mon_res = build_monitor(get_client(), target_items, mon_catalog, _start, _end)
                    st.session_state["mon_result"] = {"res": mon_res, "proc": sel_proc,
                                                      "months": mon_months}
                except Exception as e:
                    st.error(f"\u274C 모니터링 실패: {e}")
                    st.session_state.pop("mon_result", None)

        if "mon_result" in st.session_state:
            mr = st.session_state["mon_result"]
            res = mr["res"]
            rows = res["rows"]

            if not rows:
                st.warning("조회된 품목이 없습니다. 품목 키워드를 조정해야 할 수 있습니다.")
            else:
                # 요약 KPI — 상승/하락 품목 수
                ups = sum(1 for r in rows if (r.get("yoy") or 0) > 0)
                downs = sum(1 for r in rows if (r.get("yoy") or 0) < 0)
                avg_yoy = pd.Series([r["yoy"] for r in rows if r.get("yoy") is not None]).mean()
                latest_period = rows[0].get("period") or "-"

                k1, k2, k3, k4 = st.columns(4)
                k1.markdown(kpi_card("조회 품목", f"{len(rows)}개",
                                     delta=mr["proc"], icon="\U0001F4E6"), unsafe_allow_html=True)
                k2.markdown(kpi_card("전년비 상승", f"{ups}개",
                                     delta="YoY > 0", delta_type="up", icon="\U0001F4C8"), unsafe_allow_html=True)
                k3.markdown(kpi_card("전년비 하락", f"{downs}개",
                                     delta="YoY < 0", delta_type="down", icon="\U0001F4C9"), unsafe_allow_html=True)
                k4.markdown(kpi_card("평균 전년비",
                                     f"{avg_yoy:+.2f}%" if pd.notna(avg_yoy) else "-",
                                     delta=f"기준 {latest_period}", delta_type="neutral",
                                     icon="\U0001F4CA", highlight=True), unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown(section_title("품목별 현황"), unsafe_allow_html=True)

                def _arrow(v):
                    if v is None:
                        return "-"
                    if v > 1.0:
                        return f"🔴 +{v:.2f}%"
                    if v > 0:
                        return f"🟠 +{v:.2f}%"
                    if v < -1.0:
                        return f"🔵 {v:.2f}%"
                    if v < 0:
                        return f"🟢 {v:.2f}%"
                    return "⚪ 0.00%"

                tbl = pd.DataFrame([{
                    "품목": r["label"],
                    "ECOS 품목명": r["ecos_name"],
                    "코드": r["code"],
                    "최신지수": round(r["latest"], 2) if r["latest"] is not None else None,
                    "전월비": _arrow(r["mom"]),
                    "전년동월비": _arrow(r["yoy"]),
                    "기준시점": r["period"],
                    "비고": r["note"],
                } for r in rows])

                st.dataframe(tbl, use_container_width=True, hide_index=True)
                st.caption("🔴 +1%↑ · 🟠 상승 · ⚪ 보합 · 🟢 하락 · 🔵 -1%↓")

                tbl_num = pd.DataFrame([{
                    "품목": r["label"], "ECOS품목명": r["ecos_name"], "코드": r["code"],
                    "최신지수": r["latest"], "전월비(%)": r["mom"],
                    "전년동월비(%)": r["yoy"], "기준시점": r["period"], "비고": r["note"],
                } for r in rows]).round(2)
                csv = tbl_num.to_csv(index=False).encode("utf-8-sig")
                st.download_button("\U0001F4E5 현황 CSV 다운로드", csv,
                    f"품목모니터링_{latest_period}.csv", "text/csv",
                    use_container_width=True, key="mon_csv")

                # 추이 차트
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown(section_title("품목별 월별 추이"), unsafe_allow_html=True)

                pick = st.multiselect(
                    "차트에 표시할 품목 (최대 6개 권장)",
                    [r["label"] for r in rows],
                    default=[r["label"] for r in rows[:4]],
                    key="mon_pick",
                )
                if pick:
                    fig = go.Figure()
                    palette = [POSCO_COLORS["primary"], POSCO_COLORS["accent"],
                               POSCO_COLORS["danger"], "#10B981", "#8B5CF6", "#F59E0B",
                               "#06B6D4", "#EC4899"]
                    for i, r in enumerate([x for x in rows if x["label"] in pick]):
                        df_s = res["series"].get(r["code"])
                        if df_s is None or len(df_s) == 0:
                            continue
                        d = df_s.copy()
                        d["TIME_DT"] = pd.to_datetime(d["TIME"].astype(str), format="%Y%m")
                        fig.add_trace(go.Scatter(
                            x=d["TIME_DT"], y=d["DATA_VALUE"], mode="lines",
                            name=r["label"],
                            line=dict(color=palette[i % len(palette)], width=2.2),
                            hovertemplate="<b>%{x|%Y-%m}</b><br>" + r["label"] + ": %{y:.2f}<extra></extra>",
                        ))
                    fig.add_hline(y=100, line_dash="dash", line_color=POSCO_COLORS["neutral_500"],
                                  annotation_text="2020 기준 (100)")
                    fig.update_layout(
                        title=f"{mr['proc']} 품목 지수 추이 (최근 {mr['months']}개월)",
                        yaxis_title="지수 (2020=100)", height=520, hovermode="x unified",
                        xaxis=dict(rangeslider=dict(visible=True, thickness=0.05)),
                        legend=dict(orientation="h", y=1.02, x=0),
                    )
                    st.plotly_chart(fig, use_container_width=True)

                if res["unresolved"]:
                    with st.expander(f"\u26A0\uFE0F 매칭되지 않은 품목 {len(res['unresolved'])}개"):
                        st.write(", ".join(res["unresolved"]))
                        st.caption(
                            "ECOS 품목명과 키워드가 다를 수 있습니다. "
                            "`data/steel_plant_items.py`의 keywords를 실제 품목명에 맞게 보완하세요. "
                            "'설비별 PPI 조회' 탭에서 실제 품목명을 검색해 확인할 수 있습니다."
                        )


# ═══════════════════════════════════════════
# Tab 1: AI Agent 환산
# ═══════════════════════════════════════════
with tab_ai:
    st.markdown(section_title("자연어 입력 → 자동 환산"), unsafe_allow_html=True)

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

    run_clicked = st.button("🚀 AI Agent 실행", type="primary", use_container_width=True)
    if run_clicked:
        if not user_query.strip():
            st.warning("요청 내용을 입력해 주세요.")
        else:
            with st.spinner("🤖 AI Agent 분석 중..."):
                try:
                    result = run_ppi_agent(
                        user_query, use_demo=False, llm_provider=llm_provider,
                        override_code=(override_code.strip() or None),
                        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                    )
                    # 결과를 세션에 저장 — Gemini 버튼 눌러도 화면 유지
                    st.session_state["tab1_result"] = result
                except Exception as e:
                    err_str = str(e)
                    st.error(f"❌ 실행 오류: {e}")
                    if "INFO-100" in err_str:
                        st.info("💡 INFO-100: ECOS 키 확인 (따옴표/공백 제거 · 발급 후 1시간 대기)")
                    elif "INFO-200" in err_str:
                        st.info("💡 INFO-200: ⚙️ 강제 ITEM_CODE에 실제 코드를 넣어보세요")
                    st.session_state.pop("tab1_result", None)

    # 🆕 결과가 세션에 있으면 매 rerun마다 렌더 (Gemini 버튼 눌러도 유지)
    if "tab1_result" in st.session_state:
        result = st.session_state["tab1_result"]
        try:

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
            st.markdown(section_title("PPI 추이 분석"), unsafe_allow_html=True)
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
                st.markdown(section_title("AI 분석 보고서"), unsafe_allow_html=True)
                st.markdown(result["report"])

                # 내보내기
                st.markdown("##### 내보내기")
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
                        body_text=result["report"] + (
                            "\n\n---\n*본 환산 결과는 포스코 투자엔지니어링실 내부 투자비 추정·검토용입니다. "
                            "「국가를 당사자로 하는 계약에 관한 법률」상 계약금액조정(물가변동) 산식과는 다르므로, "
                            "공식 계약 근거 자료로 사용하지 마십시오.*"
                        ),
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
            st.markdown("### 상승 원인 분석 (AI)")
            st.caption("Gemini가 PPI 추이와 거시경제 이벤트를 연결해 왜 움직였는지 해설합니다.")

            if st.button("🧠 Gemini로 원인 분석 실행", key="explain_btn", use_container_width=True):
                if not os.getenv("GEMINI_API_KEY", "").strip():
                    st.warning("⚠️ Gemini API Key가 설정되지 않았습니다. 좌측 사이드바에서 입력하세요.")
                else:
                    try:
                        from agents.ppi_agent import explain_price_change_gemini
                        with st.spinner("Gemini가 거시경제 맥락을 분석 중입니다... (10~30초, 서버 혼잡 시 자동 재시도)"):
                            explanation = explain_price_change_gemini(
                                item_name=result["item_info"].get("name", ""),
                                item_code=parsed["recommended_code"],
                                ppi_df=df_full.rename(columns={"TIME": "date", "DATA_VALUE": "value"}),
                                base_period=parsed["base_period"],
                                target_period=parsed["target_period"],
                                factor=factor,
                                model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                            )
                        st.markdown(
                            f"<div style='background:linear-gradient(135deg,#f8fbff,#eef4ff);"
                            f"padding:1.5rem;border-radius:12px;border-left:4px solid #005EB8;"
                            f"margin-top:0.8rem'>{explanation}</div>",
                            unsafe_allow_html=True,
                        )
                    except Exception as e:
                        err_str = str(e)
                        if any(k in err_str for k in ["503", "UNAVAILABLE", "overloaded", "high demand"]):
                            st.warning(
                                "⏳ Google Gemini 서버가 현재 혼잡합니다. "
                                "**1~2분 후 다시 눌러주세요.** "
                                "또는 사이드바에서 `gemini-flash-latest` / `gemini-2.5-pro` 로 전환하면 해결되기도 합니다."
                            )
                        elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                            st.warning(
                                "🚦 무료 티어 분당 요청 한도 초과입니다. **30초~1분 후 재시도**하세요."
                            )
                        elif "404" in err_str or "not available" in err_str.lower():
                            st.error(
                                f"❌ 모델을 찾을 수 없습니다: {err_str}\n\n"
                                "→ 사이드바에서 **다른 Gemini 모델**로 전환해주세요."
                            )
                        else:
                            st.error(f"원인 분석 실패: {err_str}")

            with st.expander("🔧 파싱 상세"):
                st.json(parsed)

        except Exception as e:
            err_str = str(e)
            st.error(f"❌ 결과 표시 중 오류: {e}")
            if "INFO-100" in err_str:
                st.info("💡 INFO-100: ECOS 키 확인 (따옴표/공백 제거 · 발급 후 1시간 대기)")
            elif "INFO-200" in err_str:
                st.info("💡 INFO-200: ⚙️ 강제 ITEM_CODE에 실제 코드를 넣어보세요")


# ═══════════════════════════════════════════
# Tab: 📑 엑셀 일괄 보정 (견적서 → 자동제안 → 사람확인 → 승인 → 환산)
# ═══════════════════════════════════════════
with tab_batch:
    st.markdown(section_title("견적 엑셀 일괄 물가보정"), unsafe_allow_html=True)
    st.caption(
        "투자비 견적 엑셀을 올리면 각 행의 품목명을 ECOS 품목으로 **자동 제안**하고, "
        "사람이 확인·승인한 뒤 전체를 일괄 환산합니다."
    )
    st.warning(
        "⚠️ **자동 매칭은 제안일 뿐 확정이 아닙니다.**\n\n"
        "견적 품목명('냉각수 순환펌프 1식', 'BFP 3대')은 구체적이라 자동 매칭이 틀릴 수 있고, "
        "틀린 매칭은 **에러 없이 조용히 틀린 금액**을 만들어 투자 품의서에 들어갈 위험이 있습니다.\n\n"
        "→ 신뢰도가 🟢 높음이 아닌 행은 **직접 확인하고 '확인'에 체크해야** 실행됩니다."
    )

    _bat_cat = get_catalog(api_key=os.getenv("ECOS_API_KEY"))
    if _bat_cat is None or len(_bat_cat) == 0:
        st.error("ECOS 카탈로그 로드 실패 — 사이드바에서 인증키를 확인하세요.")
    else:
        # 드롭다운용 옵션: "코드 · 품목명" (사람이 다른 품목으로 갈아끼울 수 있게 전체 노출)
        _bat_opts = [""] + [
            f"{r.ITEM_CODE} · {r.ITEM_NAME}" for r in _bat_cat.itertuples()
        ]

        def _bat_label(code, name):
            code, name = str(code or "").strip(), str(name or "").strip()
            return f"{code} · {name}" if code else ""

        def _bat_parse(label):
            """'6114 · 펌프' → ('6114', '펌프')"""
            s = str(label or "")
            if " · " not in s:
                return "", ""
            code, name = s.split(" · ", 1)
            return code.strip(), name.strip()

        # ── 1) 업로드
        st.markdown("#### 1. 견적 엑셀 업로드")
        _bat_sample = to_excel_bytes({
            "견적서": pd.DataFrame({
                "품목명": ["냉각수 순환펌프 1식", "주변압기 154kV", "형강 H-300x300"],
                "규격": ["150kW", "60MVA", "SS400"],
                "투자비(원)": [1200000000, 2500000000, 180000000],
            })
        })
        c_up, c_smp = st.columns([3, 1])
        with c_up:
            _bat_file = st.file_uploader(
                "xlsx / xls / csv",
                type=["xlsx", "xls", "csv"],
                key="bat_file",
                help="품목명 컬럼과 금액 컬럼이 있으면 됩니다. 헤더는 1행에 두세요.",
            )
        with c_smp:
            st.download_button(
                "📥 샘플 양식",
                data=_bat_sample,
                file_name="견적_샘플양식.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        if _bat_file is None:
            st.info("견적 엑셀을 업로드하면 자동 매칭이 시작됩니다. 양식이 없으면 샘플을 내려받아 쓰세요.")
        else:
            try:
                _bat_raw = read_table(_bat_file, _bat_file.name)
            except Exception as e:
                _bat_raw = None
                st.error(f"파일을 읽을 수 없습니다: {e}")

            if _bat_raw is not None and len(_bat_raw) > 0:
                st.success(f"{len(_bat_raw):,}행 · {len(_bat_raw.columns)}컬럼 읽음")
                with st.expander("📄 원본 미리보기 (상위 10행)"):
                    st.dataframe(_bat_raw.head(10), use_container_width=True)

                # ── 2) 컬럼 지정
                st.markdown("#### 2. 컬럼 지정")
                _g_item, _g_amt = guess_columns(_bat_raw)
                _cols = list(_bat_raw.columns)
                cc1, cc2 = st.columns(2)
                with cc1:
                    _bat_item_col = st.selectbox(
                        "품목명 컬럼", _cols,
                        index=_cols.index(_g_item) if _g_item in _cols else 0,
                        key="bat_item_col",
                    )
                with cc2:
                    _bat_amt_col = st.selectbox(
                        "금액 컬럼", _cols,
                        index=_cols.index(_g_amt) if _g_amt in _cols else 0,
                        key="bat_amt_col",
                    )
                st.caption("자동 추정값입니다. 틀렸으면 바꿔주세요.")

                if len(_bat_raw) > MAX_ROWS:
                    st.error(
                        f"행 수 {len(_bat_raw):,}건이 상한 {MAX_ROWS}건을 초과합니다. "
                        "품목별로 개별 API 호출이 발생하므로 나눠서 처리하세요."
                    )
                elif st.button("🔎 자동 매칭 실행", type="primary", use_container_width=True):
                    with st.spinner("ECOS 품목 자동 매칭 중..."):
                        try:
                            _rev = suggest_matches(
                                _bat_raw, _bat_item_col, _bat_amt_col, _bat_cat
                            )
                            _rev["확정품목"] = [
                                _bat_label(r["제안코드"], r["제안품목"])
                                for _, r in _rev.iterrows()
                            ]
                            _rev["확인"] = _rev["신뢰도"] == CONF_HIGH
                            st.session_state["bat_review"] = _rev
                            st.session_state.pop("bat_result", None)
                        except Exception as e:
                            st.error(f"매칭 실패: {e}")

                # ── 3) 검토 · 수정 · 확인
                if "bat_review" in st.session_state:
                    _rev = st.session_state["bat_review"]

                    st.markdown("#### 3. 매칭 검토 · 수정")
                    n_hi = int((_rev["신뢰도"] == CONF_HIGH).sum())
                    n_mid = int((_rev["신뢰도"] == CONF_MEDIUM).sum())
                    n_lo = int((_rev["신뢰도"] == CONF_LOW).sum())
                    n_no = int((_rev["신뢰도"] == CONF_NONE).sum())
                    k1, k2, k3, k4 = st.columns(4)
                    for _c, _lbl, _v in [
                        (k1, "🟢 높음", n_hi), (k2, "🟠 중간", n_mid),
                        (k3, "🔴 낮음", n_lo), (k4, "⚪ 실패", n_no),
                    ]:
                        with _c:
                            st.markdown(kpi_card(_lbl, f"{_v}건"), unsafe_allow_html=True)

                    if n_lo or n_no or n_mid:
                        st.info(
                            "🟠🔴⚪ 행은 **판단근거**를 읽고 '확정품목'을 바로잡은 뒤 '확인'에 체크하세요. "
                            "드롭다운에는 ECOS 전체 품목이 들어 있습니다."
                        )

                    _show = _rev.copy()
                    _show["신뢰도"] = _show["신뢰도"].map(lambda v: CONF_ICON.get(v, v))
                    _edited = st.data_editor(
                        _show[["행", "견적품목명", "금액", "신뢰도", "확정품목", "확인", "판단근거", "금액오류"]],
                        use_container_width=True,
                        hide_index=True,
                        key="bat_editor",
                        column_config={
                            "행": st.column_config.NumberColumn("엑셀행", disabled=True, width="small"),
                            "견적품목명": st.column_config.TextColumn("견적 품목명", disabled=True),
                            "금액": st.column_config.NumberColumn(
                                "금액(원)", format="%.0f",
                                help="'800억'처럼 단위가 붙은 값은 읽지 못합니다. 여기서 숫자로 고치세요.",
                            ),
                            "신뢰도": st.column_config.TextColumn("신뢰도", disabled=True, width="small"),
                            "확정품목": st.column_config.SelectboxColumn(
                                "확정 ECOS 품목", options=_bat_opts, required=False,
                                help="자동 제안이 틀렸으면 여기서 다른 품목을 고르세요.",
                            ),
                            "확인": st.column_config.CheckboxColumn("확인", help="사람이 검토했음"),
                            "판단근거": st.column_config.TextColumn("판단근거", disabled=True, width="large"),
                            "금액오류": st.column_config.TextColumn("금액오류", disabled=True),
                        },
                    )

                    # 편집 결과를 원본 스키마로 되돌림
                    _rev2 = _rev.copy()
                    _rev2["금액"] = _edited["금액"].values
                    _rev2["확인"] = _edited["확인"].fillna(False).astype(bool).values
                    _codes, _names = zip(*[_bat_parse(v) for v in _edited["확정품목"].values]) \
                        if len(_edited) else ((), ())
                    _rev2["제안코드"] = list(_codes)
                    _rev2["제안품목"] = list(_names)
                    st.session_state["bat_review"] = _rev2

                    # ── 4) 시점 + 승인 게이트
                    st.markdown("#### 4. 기준·목표 시점")
                    _dflt_target = (datetime.now() - timedelta(days=60)).strftime("%Y%m")
                    p1, p2 = st.columns(2)
                    with p1:
                        _bat_base = st.text_input("기준시점 (YYYYMM)", value="201901", key="bat_base")
                    with p2:
                        _bat_target = st.text_input("목표시점 (YYYYMM)", value=_dflt_target, key="bat_target")
                    st.caption("환산액 = 원금 × (목표시점 지수 ÷ 기준시점 지수)")

                    _blockers = approval_blockers(_rev2)
                    if not re.fullmatch(r"\d{6}", str(_bat_base) or ""):
                        _blockers.append("기준시점 형식이 YYYYMM이 아닙니다.")
                    if not re.fullmatch(r"\d{6}", str(_bat_target) or ""):
                        _blockers.append("목표시점 형식이 YYYYMM이 아닙니다.")

                    st.markdown("#### 5. 승인 후 실행")
                    if _blockers:
                        st.error(
                            "**아래를 해결해야 실행할 수 있습니다** — 확인되지 않은 매칭으로 "
                            "금액을 만들지 않기 위한 안전장치입니다.\n\n"
                            + "\n".join(f"- {b}" for b in _blockers)
                        )
                    else:
                        st.success("✅ 전 행 검토 완료 — 실행 가능합니다.")

                    if st.button(
                        "🚀 승인 후 일괄 보정 실행",
                        type="primary", use_container_width=True,
                        disabled=bool(_blockers),
                    ):
                        _pb = st.progress(0.0, text="보정 준비 중...")

                        def _cb(done, total, label):
                            _pb.progress(done / max(total, 1), text=f"[{done}/{total}] {label}")

                        try:
                            _res = run_batch(
                                _rev2, get_client(), str(_bat_base), str(_bat_target),
                                progress_cb=_cb,
                            )
                            st.session_state["bat_result"] = _res
                        except Exception as e:
                            st.error(f"보정 실행 실패: {e}")
                        finally:
                            _pb.empty()

                # ── 6) 결과
                if "bat_result" in st.session_state:
                    _res = st.session_state["bat_result"]
                    _sm = summarize(_res)

                    st.divider()
                    st.markdown("#### 6. 보정 결과")

                    # 화면은 억 단위로 읽기 쉽게, 원 단위 전체를 바로 아래 병기.
                    # 억 표시는 반올림되므로 근거로 쓸 값은 원 단위 병기·엑셀을 봐야 한다.
                    r1, r2, r3, r4 = st.columns(4)
                    with r1:
                        st.markdown(kpi_card(
                            "원금 합계", fmt_eok(_sm["원금합계"]),
                            unit=eok_unit(_sm["원금합계"]),
                            sub=f"{_sm['원금합계']:,.0f}원",
                        ), unsafe_allow_html=True)
                    with r2:
                        st.markdown(kpi_card(
                            "환산 합계", fmt_eok(_sm["환산합계"]),
                            unit=eok_unit(_sm["환산합계"]),
                            sub=f"{_sm['환산합계']:,.0f}원",
                            highlight=True,
                        ), unsafe_allow_html=True)
                    with r3:
                        _d = _sm["증감률(%)"]
                        st.markdown(kpi_card(
                            "증감률", f"{_d:+.2f}" if _d is not None else "—",
                            unit="%" if _d is not None else None,
                            sub=f"증감 {_sm['증감액']:,.0f}원",
                            delta_type="up" if (_d or 0) > 0 else "down",
                        ), unsafe_allow_html=True)
                    with r4:
                        st.markdown(kpi_card(
                            "환산 성공", f"{_sm['성공']}",
                            unit=f"/ {_sm['건수']}건",
                            sub=f"실패 {_sm['실패']}건 · 저신뢰 {_sm['저신뢰건수']}건",
                        ), unsafe_allow_html=True)

                    if _sm["실패"]:
                        st.warning(
                            f"⚠️ {_sm['실패']}건은 환산하지 못했습니다. **합계에서 제외**했으므로 "
                            "총액이 견적 전체와 다릅니다. '오류' 열을 확인하세요."
                        )

                    # 금액은 천단위 구분, 지수·계수는 소수 자리를 고정해 자리를 맞춘다
                    st.dataframe(
                        _res, use_container_width=True, hide_index=True,
                        column_config={
                            "행": st.column_config.NumberColumn("엑셀행", width="small"),
                            "원금": st.column_config.NumberColumn("원금(원)", format="localized"),
                            "환산액": st.column_config.NumberColumn("환산액(원)", format="localized"),
                            "증감액": st.column_config.NumberColumn("증감액(원)", format="localized"),
                            "기준지수": st.column_config.NumberColumn("기준지수", format="%.2f"),
                            "목표지수": st.column_config.NumberColumn("목표지수", format="%.2f"),
                            "보정계수": st.column_config.NumberColumn("보정계수", format="%.4f"),
                            "증감률(%)": st.column_config.NumberColumn("증감률(%)", format="%.2f"),
                            "오류": st.column_config.TextColumn("오류", width="large"),
                        },
                    )

                    _disc = (
                        "본 결과는 내부 투자비 추정·검토용이며, 「국가계약법」상 계약금액조정(물가변동) "
                        "산식과 다르므로 공식 계약 근거로 사용할 수 없습니다. "
                        "품목 매칭은 자동 제안에 사람 확인을 거친 것으로, 매칭 적정성의 최종 책임은 검토자에게 있습니다."
                    )
                    st.caption(f"ℹ️ {_disc}")

                    _sum_df = pd.DataFrame([
                        {"항목": k, "값": v} for k, v in _sm.items()
                    ])
                    _meta_df = pd.DataFrame([
                        {"항목": "기준시점", "값": st.session_state.get("bat_base", "")},
                        {"항목": "목표시점", "값": st.session_state.get("bat_target", "")},
                        {"항목": "데이터 출처", "값": "한국은행 ECOS 생산자물가지수 (404Y014, 2020=100)"},
                        {"항목": "생성일시", "값": datetime.now().strftime("%Y-%m-%d %H:%M")},
                        {"항목": "면책", "값": _disc},
                    ])
                    st.download_button(
                        "📊 결과 엑셀 내려받기",
                        data=to_excel_bytes({
                            "보정결과": _res,
                            "요약": _sum_df,
                            "매칭검토": st.session_state["bat_review"].drop(columns=["후보"], errors="ignore"),
                            "산출근거": _meta_df,
                        }),
                        file_name=f"투자비_일괄보정_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )


# ═══════════════════════════════════════════
# Tab 2: 설비별 PPI 조회
# ═══════════════════════════════════════════
with tab_ppi:
    st.markdown(section_title("ECOS 품목 단일 조회"), unsafe_allow_html=True)

    if True:
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
# Tab: 🏗️ 공사비 물가보정 (KOSIS 건설공사비지수)
# ═══════════════════════════════════════════
with tab_cci:
    st.markdown(section_title("공사비 물가보정 (건설공사비지수)"), unsafe_allow_html=True)
    st.caption(
        "한국건설기술연구원 건설공사비지수(KOSIS, 2020=100)로 과거 공사비를 현재가치로 환산합니다. "
        "본 기능은 **내부 투자비 추정·검토용**이며, 「국가계약법」상 계약금액조정 산식과는 다릅니다."
    )

    _kosis_key = os.getenv("KOSIS_API_KEY", "").strip()
    if not _kosis_key:
        st.info(
            "\U0001F50C **KOSIS 인증키가 설정되지 않았습니다.**\n\n"
            "왼쪽 사이드바에 KOSIS API Key를 입력하거나 secrets에 `KOSIS_API_KEY`를 등록하면 "
            "공사비 물가보정이 활성화됩니다.\n\n"
            "\u2192 무료 발급: https://kosis.kr \ubcf5\ud569\uc11c\ube44\uc2a4(OpenAPI)"
        )
    else:
        # 공종 카탈로그 자동 발견
        with st.spinner("KOSIS 공종 분류를 불러오는 중..."):
            try:
                cci_catalog = get_construction_catalog(api_key=_kosis_key)
            except Exception as e:
                cci_catalog = None
                st.error(f"공종 카탈로그 로드 실패: {e}")

        cci_options = catalog_to_options(cci_catalog) if cci_catalog is not None else []

        if not cci_options:
            st.warning(
                "공종 분류를 불러오지 못했습니다. 키가 올바른지, 통계표 코드(DT_39701_A003)가 "
                "유효한지 확인하세요. 아래에서 공종코드(objL1)를 직접 입력할 수도 있습니다."
            )

        # 공종 선택 (자동 발견 목록 + 직접 입력 폴백)
        col_sel, col_code = st.columns([2, 1])
        with col_sel:
            if cci_options:
                labels = [f"{o['name']} [{o['code']}]" for o in cci_options]
                sel_label = st.selectbox(f"\U0001F3D7\uFE0F 공종 선택 ({len(cci_options)}개)", labels, key="cci_sel")
                sidx = labels.index(sel_label)
                cci_code = cci_options[sidx]["code"]
                cci_name = cci_options[sidx]["name"]
            else:
                cci_code, cci_name = None, None
        with col_code:
            override_cci = st.text_input("\u2699\uFE0F 공종코드 직접 입력", "",
                                         help="objL1 코드. 비우면 위 선택값 사용", key="cci_override")
            if override_cci.strip():
                cci_code = override_cci.strip()
                cci_name = f"공종 {cci_code}"

        if cci_code:
            st.caption(f"\U0001F4CC **{cci_name}** \u00b7 공종코드 `{cci_code}`")

        # 입력
        i1, i2, i3 = st.columns(3)
        cci_cost = i1.number_input("\U0001F4B0 공사 원금 (억원)", 0.0, 1_000_000.0, 500.0, step=10.0, key="cci_cost")
        cci_base = i2.text_input("기준 시점 (YYYYMM)", "202001", key="cci_base")
        # 건설공사비지수는 발표가 1~2개월 지연 → 기본 목표를 2개월 전으로
        _cci_default_target = (datetime.now().replace(day=1) - pd.Timedelta(days=60)).strftime("%Y%m")
        cci_target = i3.text_input("목표 시점 (YYYYMM)", _cci_default_target, key="cci_target",
                                   help="건설공사비지수는 발표가 1~2개월 늦습니다. 최근 발표월로 설정하세요.")

        if st.button("\U0001F3D7\uFE0F 공사비 환산 실행", type="primary", use_container_width=True, key="cci_run"):
            if not cci_code:
                st.warning("공종을 선택하거나 코드를 입력하세요.")
            else:
                try:
                    client = KOSISClient(api_key=_kosis_key)
                    base_idx = client.get_ppi_at(cci_code, cci_base)
                    target_idx = client.get_ppi_at(cci_code, cci_target)
                    factor = target_idx / base_idx
                    adjusted = cci_cost * factor
                    st.session_state["cci_result"] = {
                        "code": cci_code, "name": cci_name, "cost": cci_cost,
                        "base": cci_base, "target": cci_target,
                        "base_idx": base_idx, "target_idx": target_idx,
                        "factor": factor, "adjusted": adjusted, "diff": adjusted - cci_cost,
                    }
                except Exception as e:
                    st.error(f"\u274C 환산 실패: {e}")
                    st.session_state.pop("cci_result", None)

        if "cci_result" in st.session_state:
            res = st.session_state["cci_result"]
            st.markdown("<br>", unsafe_allow_html=True)
            c1, c2, c3, c4 = st.columns(4)
            c1.markdown(kpi_card("원금", f"{res['cost']:,.0f} 억", delta=res["base"], icon="\U0001F4B0"), unsafe_allow_html=True)
            c2.markdown(kpi_card("보정계수", f"{res['factor']:.4f}",
                                 delta=f"{(res['factor']-1)*100:+.2f}%",
                                 delta_type="up" if res["factor"] > 1 else "down", icon="\u2696\uFE0F"), unsafe_allow_html=True)
            c3.markdown(kpi_card("증감액", f"{res['diff']:+,.1f} 억", delta="현재가 기준",
                                 delta_type="up" if res["diff"] > 0 else "down", icon="\U0001F4CA"), unsafe_allow_html=True)
            c4.markdown(kpi_card("환산 공사비", f"{res['adjusted']:,.1f} 억", delta=res["target"],
                                 delta_type="neutral", icon="\U0001F3AF", highlight=True), unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(section_title("건설공사비지수 추이"), unsafe_allow_html=True)
            try:
                client = KOSISClient(api_key=_kosis_key)
                df_full = client.get_ppi(res["code"], "201501", res["target"])
                df_full["TIME_DT"] = pd.to_datetime(df_full["TIME"], format="%Y%m")
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=df_full["TIME_DT"], y=df_full["DATA_VALUE"], mode="lines",
                    name="건설공사비지수", line=dict(color=POSCO_COLORS["accent"], width=2.5),
                    fill="tozeroy", fillcolor="rgba(242,159,5,0.08)",
                    hovertemplate="<b>%{x|%Y년 %m월}</b><br>지수: %{y:.2f}<extra></extra>",
                ))
                def _mark_cci(period, label, color):
                    try:
                        t = pd.to_datetime(period, format="%Y%m")
                        v = df_full[df_full["TIME"] == period]["DATA_VALUE"]
                        if len(v) > 0:
                            fig.add_trace(go.Scatter(
                                x=[t], y=[float(v.iloc[0])], mode="markers+text",
                                marker=dict(size=14, color=color, line=dict(color="white", width=2)),
                                text=[label], textposition="top center",
                                textfont=dict(size=11, color=color), showlegend=False))
                    except Exception:
                        pass
                _mark_cci(res["base"], "\U0001F4CD 기준", POSCO_COLORS["primary"])
                _mark_cci(res["target"], "\U0001F3AF 목표", POSCO_COLORS["danger"])
                fig.add_hline(y=100, line_dash="dash", line_color=POSCO_COLORS["neutral_500"],
                              annotation_text="2020 기준 (100)")
                fig.update_layout(
                    title=f"{res['name']} 건설공사비지수 시계열",
                    xaxis=dict(rangeslider=dict(visible=True, thickness=0.05)),
                    yaxis_title="지수 (2020=100)", height=480, hovermode="x unified")
                st.plotly_chart(fig, use_container_width=True)

                st.markdown(
                    f"| 항목 | 값 |\n|---|---|\n"
                    f"| 공종 | {res['name']} (`{res['code']}`) |\n"
                    f"| 기준 {res['base']} 지수 | {res['base_idx']:.2f} |\n"
                    f"| 목표 {res['target']} 지수 | {res['target_idx']:.2f} |\n"
                    f"| 보정계수 | {res['factor']:.4f} |\n"
                    f"| 원금 | {res['cost']:,.1f} 억원 |\n"
                    f"| **환산 공사비** | **{res['adjusted']:,.1f} 억원** ({(res['factor']-1)*100:+.2f}%) |"
                )

                st.markdown("##### 내보내기")
                ex1, ex2 = st.columns(2)
                with ex1:
                    pdf_bytes = generate_pdf_report(
                        title=f"공사비 물가보정 리포트 \u2014 {res['name']}",
                        summary={
                            "공종": res["name"], "기준 시점": res["base"], "목표 시점": res["target"],
                            "기준 지수": f"{res['base_idx']:.2f}", "목표 지수": f"{res['target_idx']:.2f}",
                            "보정계수": f"{res['factor']:.4f}", "원금": f"{res['cost']:,.1f} 억원",
                            "환산 공사비": f"{res['adjusted']:,.1f} 억원",
                            "증감": f"{res['diff']:+,.1f} 억원 ({(res['factor']-1)*100:+.2f}%)",
                        },
                        body_text=(
                            f"{res['base']} 기준 {res['cost']:,.1f}억원의 {res['name']} 공사비를 "
                            f"{res['target']} 현재가치로 환산한 결과입니다. 건설공사비지수가 "
                            f"{res['base_idx']:.2f}에서 {res['target_idx']:.2f}로 변동하여 보정계수 "
                            f"{res['factor']:.4f}가 적용되었으며, 환산 공사비는 {res['adjusted']:,.1f}억원입니다."
                            "\n\n---\n*본 환산 결과는 포스코 투자엔지니어링실 내부 투자비 추정·검토용입니다. "
                            "「국가를 당사자로 하는 계약에 관한 법률」상 계약금액조정(물가변동) 산식과는 다르므로, "
                            "공식 계약 근거 자료로 사용하지 마십시오.*"
                        ),
                        table_df=df_full[["TIME", "DATA_VALUE"]].rename(columns={"TIME": "시점", "DATA_VALUE": "지수"}),
                    )
                    st.download_button("\U0001F4C4 PDF 다운로드", pdf_bytes,
                        f"공사비보정_{res['base']}_{res['target']}.pdf",
                        "application/pdf", use_container_width=True, key="cci_pdf")
                with ex2:
                    xlsx = to_excel_bytes({
                        "요약": pd.DataFrame([{"항목": k, "값": v} for k, v in {
                            "공종": res["name"], "원금(억)": res["cost"], "환산공사비(억)": res["adjusted"],
                            "보정계수": res["factor"], "기준시점": res["base"], "목표시점": res["target"],
                        }.items()]),
                        "건설공사비지수": df_full[["TIME", "DATA_VALUE"]],
                    })
                    st.download_button("\U0001F4CA Excel 다운로드", xlsx,
                        f"공사비보정_{res['base']}_{res['target']}.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True, key="cci_xlsx")
            except Exception as e:
                st.warning(f"차트 생성 실패: {e}")


# ═══════════════════════════════════════════
# Tab 3: 다중 설비 비교
# ═══════════════════════════════════════════
with tab_multi:
    st.markdown(section_title("여러 설비 PPI 동시 비교"), unsafe_allow_html=True)

    if True:
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
                summary = []
                skipped = []
                prog = st.progress(0, text="조회 중...")
                all_series = {}
                series_records = []  # 차트 재렌더용

                for i, item in enumerate(selected_rows):
                    try:
                        df = client.get_ppi(item["code"], start_m, end_m)
                        df["TIME_DT"] = pd.to_datetime(df["TIME"], format="%Y%m")
                        y = df["DATA_VALUE"].values

                        all_series[item["name"]] = pd.Series(
                            df["DATA_VALUE"].values, index=df["TIME"].values
                        )
                        series_records.append({
                            "name": item["name"],
                            "code": item["code"],
                            "time_dt": df["TIME_DT"].tolist(),
                            "values": df["DATA_VALUE"].tolist(),
                        })
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

                if summary:
                    df_sum = pd.DataFrame(summary).sort_values("변동률(%)", ascending=False)
                    # 세션에 모든 결과 저장 → 아래 렌더 블록이 매 rerun마다 그림
                    st.session_state["multi_series_records"] = series_records
                    st.session_state["multi_summary"] = df_sum
                    st.session_state["multi_series"] = all_series
                    st.session_state["multi_normalize"] = normalize
                    st.session_state["multi_skipped"] = skipped
                    st.session_state["multi_period"] = (start_m, end_m)
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
            except Exception as e:
                st.error(f"오류: {e}")

    # ───────────────────────────────────────────
    # 📊 세션 데이터 기반 차트/표 재렌더 (버튼 클릭과 무관하게 유지)
    # ───────────────────────────────────────────
    if "multi_series_records" in st.session_state and st.session_state["multi_series_records"]:
        records = st.session_state["multi_series_records"]
        df_sum = st.session_state["multi_summary"]
        normalize_render = st.session_state.get("multi_normalize", True)
        skipped_render = st.session_state.get("multi_skipped", [])

        if skipped_render:
            with st.expander(f"⚠️ 조회 실패 {len(skipped_render)}건"):
                for n, e in skipped_render:
                    st.markdown(f"- **{n}**: {e}")

        # 추이 차트
        fig = go.Figure()
        for i, rec in enumerate(records):
            y_arr = rec["values"]
            y_plot = [v / y_arr[0] * 100 for v in y_arr] if normalize_render and y_arr[0] != 0 else y_arr
            fig.add_trace(go.Scatter(
                x=rec["time_dt"], y=y_plot, mode="lines",
                name=rec["name"],
                line=dict(color=SERIES_COLORS[i % len(SERIES_COLORS)], width=2.3),
                hovertemplate="<b>%{fullData.name}</b><br>%{x|%Y-%m}<br>"
                              + ("정규화: " if normalize_render else "PPI: ") + "%{y:.2f}<extra></extra>",
            ))
        if normalize_render:
            fig.add_hline(y=100, line_dash="dash", line_color=POSCO_COLORS["neutral_500"],
                          annotation_text="시작점=100")
        fig.update_layout(
            title="📈 다중 설비 PPI 비교" + (" (정규화)" if normalize_render else ""),
            xaxis=dict(rangeslider=dict(visible=True, thickness=0.05)),
            yaxis_title="정규화 지수" if normalize_render else "PPI (2020=100)",
            height=560, hovermode="x unified",
            legend=dict(orientation="h", y=1.02, x=0),
        )
        st.plotly_chart(fig, use_container_width=True)

        # 요약표
        st.dataframe(df_sum, use_container_width=True, hide_index=True)

        # 변동률 순위 막대
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

        # 내보내기
        s_m_cur, e_m_cur = st.session_state.get("multi_period", (start_m, end_m))
        xlsx = to_excel_bytes({"비교 요약": df_sum})
        st.download_button(
            "📊 Excel 다운로드", xlsx,
            f"다중설비_{s_m_cur}_{e_m_cur}.xlsx",
            use_container_width=True,
            key="multi_xlsx_dl",
        )

    # ───────────────────────────────────────────
    # 🆕 AI 비교 분석 (Gemini) — Tab 3 하단
    # ───────────────────────────────────────────
    if "multi_items_info" in st.session_state and st.session_state["multi_items_info"]:
        st.markdown("---")
        st.markdown("### AI 비교 분석")
        st.caption("Gemini가 품목별로 왜 다르게 움직였는지 거시·산업 맥락으로 해설합니다.")

        if st.button("🧠 Gemini로 비교 분석 실행", key="multi_explain_btn", use_container_width=True):
            if not os.getenv("GEMINI_API_KEY", "").strip():
                st.warning("⚠️ Gemini API Key가 설정되지 않았습니다. 좌측 사이드바에서 입력하세요.")
            else:
                try:
                    from agents.ppi_agent import explain_multi_comparison_gemini
                    s_m, e_m = st.session_state.get("multi_period", (start_m, end_m))
                    with st.spinner("Gemini가 품목 간 차이를 분석 중입니다... (15~40초, 서버 혼잡 시 자동 재시도)"):
                        explanation = explain_multi_comparison_gemini(
                            items_info=st.session_state["multi_items_info"],
                            base_period=s_m,
                            target_period=e_m,
                            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                        )
                    st.markdown(
                        f"<div style='background:linear-gradient(135deg,#fff9f0,#fef3e2);"
                        f"padding:1.5rem;border-radius:12px;border-left:4px solid #F29F05;"
                        f"margin-top:0.8rem'>{explanation}</div>",
                        unsafe_allow_html=True,
                    )
                except Exception as e:
                    err_str = str(e)
                    if any(k in err_str for k in ["503", "UNAVAILABLE", "overloaded", "high demand"]):
                        st.warning(
                            "⏳ Google Gemini 서버가 현재 혼잡합니다. "
                            "**1~2분 후 다시 눌러주세요.** "
                            "또는 사이드바에서 `gemini-flash-latest` / `gemini-2.5-pro` 로 전환하면 해결되기도 합니다."
                        )
                    elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        st.warning(
                            "🚦 무료 티어 분당 요청 한도 초과입니다. **30초~1분 후 재시도**하세요."
                        )
                    elif "404" in err_str or "not available" in err_str.lower():
                        st.error(
                            f"❌ 모델을 찾을 수 없습니다: {err_str}\n\n"
                            "→ 사이드바에서 **다른 Gemini 모델**로 전환해주세요."
                        )
                    else:
                        st.error(f"비교 분석 실패: {err_str}")


# ═══════════════════════════════════════════
# Tab 4: 시나리오 분석 (What-if)
# ═══════════════════════════════════════════
with tab_scn:
    st.markdown(section_title("What-if 시나리오 분석"), unsafe_allow_html=True)
    st.caption("원금·보정계수·외부 충격 변동 시 환산금액 변화를 실시간 시뮬레이션")

    s1, s2, s3 = st.columns(3)
    base_cost = s1.number_input("💰 기준 원금 (억원)", 0.0, 100000.0, 800.0, step=10.0)
    base_factor = s2.number_input("⚖️ 기준 보정계수", 0.1, 5.0, 1.23, step=0.01, format="%.4f")
    base_label = s3.text_input("🏷️ 시나리오 이름", "2020년 펌프 800억")

    st.markdown("##### What-if 변수")
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
    st.markdown(section_title("민감도 토네이도 분석"), unsafe_allow_html=True)
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
    st.markdown(section_title("설비 구성비 기반 포트폴리오 환산"), unsafe_allow_html=True)
    st.caption("한 프로젝트의 여러 설비(기계/전기/토건)를 가중평균으로 통합 환산")

    p1, p2 = st.columns([1, 1])
    total_cost = p1.number_input("💰 총 투자비 (억원)", 0.0, 1000000.0, 1000.0, step=10.0)
    base_period = p2.text_input("기준 시점", "202001")
    target_period = st.text_input("목표 시점", "202601")

    st.markdown("##### 설비 구성")
    st.caption("각 설비 구성비를 입력하세요 (합계 100%)")

    # 기본 포트폴리오 예시
    default_portfolio = pd.DataFrame([
        {"설비": "펌프", "ITEM_CODE": "", "비중(%)": 30.0},
        {"설비": "변압기", "ITEM_CODE": "", "비중(%)": 20.0},
        {"설비": "시멘트", "ITEM_CODE": "", "비중(%)": 30.0},
        {"설비": "케이블", "ITEM_CODE": "", "비중(%)": 20.0},
    ])

    # 사용자가 카탈로그에서 골라 채우도록 지원
    if os.getenv("ECOS_API_KEY"):
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
        if True:
            try:
                client = get_client()
                catalog_p = get_catalog(api_key=os.getenv("ECOS_API_KEY"))

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
# Tab 6: 히트맵 & 상관관계 (v10 강화팩)
# ═══════════════════════════════════════════
with tab_heat:
    st.markdown(section_title("원가 인텔리전스 히트맵"), unsafe_allow_html=True)
    st.caption("다중 뷰 · 정렬 · 드릴다운 · 자동 인사이트 · AI 자연어 질의 · 자동 리포트")

    if "multi_series" not in st.session_state or not st.session_state["multi_series"]:
        st.info(
            "👉 **Tab 3 (다중 설비 비교)** 에서 먼저 품목들을 선택하고 "
            "비교 차트를 생성하세요. 그 데이터를 여기서 히트맵으로 활용합니다."
        )
    else:
        series_dict = st.session_state["multi_series"]

        # ─── 1) 원본 월별 데이터프레임 (모든 계산의 기반)
        monthly_rows = []
        for name, s in series_dict.items():
            for ym, val in s.items():
                try:
                    monthly_rows.append({
                        "품목": name,
                        "YM": str(ym),
                        "YEAR": int(str(ym)[:4]),
                        "MONTH": int(str(ym)[4:6]) if len(str(ym)) >= 6 else 1,
                        "PPI": float(val),
                    })
                except Exception:
                    continue
        df_month = pd.DataFrame(monthly_rows)
        # 사실상 series_dict가 있으면 df_month는 비어있지 않음 — 방어 차원으로 체크만
        if df_month.empty:
            st.warning("데이터 부족 — Tab 3에서 먼저 비교 차트를 생성해주세요.")
            df_month = pd.DataFrame([{"품목": "", "YM": "202001", "YEAR": 2020, "MONTH": 1, "PPI": 100.0}])

        # ─── 2) 연도별 평균 + YoY / 누적 / Z-score / 절대지수 계산
        yearly = df_month.groupby(["품목", "YEAR"])["PPI"].mean().reset_index()

        # YoY
        yearly["YoY(%)"] = yearly.groupby("품목")["PPI"].pct_change() * 100

        # 누적 (품목별 첫 연도 대비)
        yearly["기준PPI"] = yearly.groupby("품목")["PPI"].transform("first")
        yearly["누적(%)"] = (yearly["PPI"] / yearly["기준PPI"] - 1) * 100

        # Z-score (YoY 기준)
        def _zscore(g):
            if g.std() == 0 or pd.isna(g.std()):
                return g * 0
            return (g - g.mean()) / g.std()
        yearly["Z-score"] = yearly.groupby("품목")["YoY(%)"].transform(_zscore)

        # ─── 3) Tier 1-① 다중 뷰 토글
        st.markdown("#### 뷰 & 필터")
        vc1, vc2, vc3, vc4 = st.columns([1.2, 1.2, 1.2, 1.4])
        with vc1:
            view_mode = st.radio(
                "뷰 모드",
                ["YoY (%)", "누적 (%)", "Z-score", "절대지수"],
                horizontal=False, key="heat_view",
                help="같은 데이터를 4가지 관점으로 봅니다.",
            )
        with vc2:
            sort_mode = st.selectbox(
                "정렬 기준",
                ["품목명(가나다)", "누적 변동률 ↓", "평균 YoY ↓", "변동성(σ) ↓", "최근연도 YoY ↓"],
                key="heat_sort",
            )
        with vc3:
            threshold_pct = st.slider(
                "하이라이트 상/하위 %",
                min_value=0, max_value=50, value=0, step=5,
                help="0=전체 표시, 20=상위·하위 20% 외 셀은 흐리게",
                key="heat_threshold",
            )
        with vc4:
            show_events = st.checkbox("📌 거시이벤트 이모지 주석", value=True, key="heat_events")
            show_text = st.checkbox("셀 값 표시", value=True, key="heat_text")

        # ─── 4) 뷰 모드별 pivot 만들기
        value_col = {
            "YoY (%)": "YoY(%)",
            "누적 (%)": "누적(%)",
            "Z-score": "Z-score",
            "절대지수": "PPI",
        }[view_mode]

        pivot = yearly.pivot(index="품목", columns="YEAR", values=value_col)
        pivot = pivot.dropna(how="all", axis=1)

        # ─── 5) Tier 1-② 정렬 옵션
        if sort_mode == "품목명(가나다)":
            pivot = pivot.sort_index()
        elif sort_mode == "누적 변동률 ↓":
            cum_last = yearly.groupby("품목").apply(lambda g: g["누적(%)"].dropna().iloc[-1] if g["누적(%)"].dropna().size else 0)
            pivot = pivot.reindex(cum_last.sort_values(ascending=False).index)
        elif sort_mode == "평균 YoY ↓":
            avg = pivot.mean(axis=1).sort_values(ascending=False)
            pivot = pivot.reindex(avg.index)
        elif sort_mode == "변동성(σ) ↓":
            stdv = pivot.std(axis=1).sort_values(ascending=False)
            pivot = pivot.reindex(stdv.index)
        elif sort_mode == "최근연도 YoY ↓":
            last_year = pivot.columns.max()
            pivot = pivot.sort_values(by=last_year, ascending=False, na_position="last")

        # ─── 6) Tier 1-④ 임계값 필터 (분위수 기반 마스킹)
        pivot_display = pivot.copy()
        if threshold_pct > 0 and view_mode != "절대지수":
            q_low = pivot.stack().quantile(threshold_pct / 100)
            q_high = pivot.stack().quantile(1 - threshold_pct / 100)
            # 상·하위 % 벗어나는 것만 유지, 나머진 NaN
            mask = (pivot_display < q_low) | (pivot_display > q_high)
            pivot_display = pivot_display.where(mask, other=None)

        # ─── 7) Tier 3-⑩ 연도 이벤트 주석
        YEAR_EVENTS = {
            2015: "🛢️", 2016: "", 2017: "", 2018: "🇨🇳", 2019: "",
            2020: "🦠", 2021: "📦", 2022: "⚔️", 2023: "📈", 2024: "🤖", 2025: "", 2026: "",
        }
        x_labels = [
            f"{int(y)}{' ' + YEAR_EVENTS.get(int(y), '') if show_events and YEAR_EVENTS.get(int(y)) else ''}"
            for y in pivot_display.columns
        ]

        # ─── 8) 히트맵 렌더링
        colorscale = (
            [[0, POSCO_COLORS["success"]],
             [0.5, "#F8FAFC"],
             [1, POSCO_COLORS["danger"]]]
            if view_mode != "절대지수"
            else "Blues"
        )
        midpoint = 0 if view_mode != "절대지수" else None

        fig_h = px.imshow(
            pivot_display.values,
            x=x_labels,
            y=[str(i) for i in pivot_display.index],
            color_continuous_scale=colorscale,
            aspect="auto",
            text_auto=".1f" if show_text else False,
            title=f"🔥 품목 × 연도 히트맵 — {view_mode}"
                  + (f" (상/하위 {threshold_pct}% 하이라이트)" if threshold_pct > 0 else ""),
            color_continuous_midpoint=midpoint,
        )
        fig_h.update_layout(
            height=max(360, 42 * len(pivot_display)),
            xaxis_title="연도", yaxis_title="품목",
        )
        st.plotly_chart(fig_h, use_container_width=True)

        if show_events:
            st.caption("🦠 COVID · 📦 공급망 대란 · ⚔️ 러·우 전쟁 · 📈 연준 금리 · 🤖 AI CAPEX · 🛢️ 저유가 · 🇨🇳 미-중 무역")

        # ─── 9) Tier 3-⑨ 자동 인사이트 Top 5
        st.markdown("---")
        st.markdown("#### 자동 인사이트 Top 5")

        yoy_pivot = yearly.pivot(index="품목", columns="YEAR", values="YoY(%)").dropna(how="all", axis=1)

        # 급등/급락
        stacked = yoy_pivot.stack()
        top_up = stacked.nlargest(3)
        top_dn = stacked.nsmallest(3)

        # 변동성
        vol = yoy_pivot.std(axis=1).sort_values(ascending=False).head(3)

        # 상관계수
        df_wide = pd.DataFrame(series_dict).apply(pd.to_numeric, errors="coerce")
        corr = df_wide.corr()
        corr_pairs = []
        items_list = list(corr.columns)
        for i in range(len(items_list)):
            for j in range(i + 1, len(items_list)):
                corr_pairs.append((items_list[i], items_list[j], corr.iloc[i, j]))
        corr_pairs.sort(key=lambda x: -abs(x[2]) if not pd.isna(x[2]) else 0)
        top_corr = corr_pairs[:3]

        ic1, ic2 = st.columns(2)
        with ic1:
            st.markdown("**🔴 최대 급등 Top 3**")
            for (item, year), v in top_up.items():
                st.markdown(f"- **{item}** `{int(year)}년` → **+{v:.1f}%**")
            st.markdown("**🟢 최대 급락 Top 3**")
            for (item, year), v in top_dn.items():
                st.markdown(f"- **{item}** `{int(year)}년` → **{v:.1f}%**")
        with ic2:
            st.markdown("**📊 변동성 Top 3 (YoY 표준편차)**")
            for item, s in vol.items():
                st.markdown(f"- **{item}** → σ = **{s:.2f}%**")
            st.markdown("**🔗 가장 동조하는 품목 쌍 Top 3**")
            for a, b, v in top_corr:
                if pd.isna(v):
                    continue
                st.markdown(f"- **{a} ↔ {b}** → ρ = **{v:+.2f}**")

        # ─── 10) Tier 1-③ 셀 드릴다운 + Gemini 원인 분석
        st.markdown("---")
        st.markdown("#### 셀 드릴다운 — 특정 품목·연도 심층 분석")

        dc1, dc2, dc3 = st.columns([1.3, 1, 1])
        with dc1:
            drill_item = st.selectbox("품목 선택", list(pivot.index), key="drill_item")
        with dc2:
            drill_year = st.selectbox("연도 선택", list(pivot.columns), key="drill_year")
        with dc3:
            st.write("")
            st.write("")
            run_drill = st.button("📍 분석", key="drill_btn", use_container_width=True)

        if run_drill or "drill_last" in st.session_state:
            if run_drill:
                st.session_state["drill_last"] = (drill_item, drill_year)
            cur_item, cur_year = st.session_state["drill_last"]

            sub = df_month[(df_month["품목"] == cur_item) & (df_month["YEAR"] == int(cur_year))]
            if sub.empty:
                st.warning("해당 데이터 없음")
            else:
                yoy_val = yoy_pivot.loc[cur_item, int(cur_year)] if int(cur_year) in yoy_pivot.columns else None
                yoy_txt = f"{yoy_val:+.2f}%" if yoy_val is not None and not pd.isna(yoy_val) else "N/A"
                st.markdown(
                    f"**{cur_item}** · **{int(cur_year)}년** · YoY **{yoy_txt}** · "
                    f"평균 PPI **{sub['PPI'].mean():.2f}**"
                )

                # 월별 미니 차트
                sub = sub.sort_values("MONTH")
                fig_mini = go.Figure()
                fig_mini.add_trace(go.Scatter(
                    x=sub["MONTH"], y=sub["PPI"], mode="lines+markers",
                    line=dict(color=POSCO_COLORS["primary"], width=2.5),
                    marker=dict(size=8),
                    hovertemplate="%{x}월<br>PPI: %{y:.2f}<extra></extra>",
                ))
                fig_mini.update_layout(
                    height=260, title=f"{int(cur_year)}년 월별 PPI 추이",
                    xaxis=dict(tickmode="linear", dtick=1, title="월"),
                    yaxis_title="PPI",
                )
                st.plotly_chart(fig_mini, use_container_width=True)

                # Gemini 원인 분석 버튼 (기존 함수 재활용)
                if st.button("🧠 이 구간 Gemini 원인 분석", key="drill_explain_btn", use_container_width=True):
                    if not os.getenv("GEMINI_API_KEY", "").strip():
                        st.warning("⚠️ Gemini API Key가 설정되지 않았습니다.")
                    else:
                        try:
                            from agents.ppi_agent import explain_price_change_gemini
                            item_series = series_dict[cur_item]
                            df_item = pd.DataFrame({
                                "date": pd.to_datetime(item_series.index, format="%Y%m"),
                                "value": item_series.values,
                            })
                            factor_d = (sub["PPI"].iloc[-1] / sub["PPI"].iloc[0]) if len(sub) > 1 else 1.0
                            with st.spinner("Gemini가 분석 중... (10~30초)"):
                                explanation = explain_price_change_gemini(
                                    item_name=cur_item,
                                    item_code="(히트맵 드릴다운)",
                                    ppi_df=df_item,
                                    base_period=f"{int(cur_year)}01",
                                    target_period=f"{int(cur_year)}12",
                                    factor=factor_d,
                                    model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                                )
                            st.markdown(
                                f"<div style='background:linear-gradient(135deg,#f8fbff,#eef4ff);"
                                f"padding:1.2rem;border-radius:12px;border-left:4px solid #005EB8;"
                                f"margin-top:0.6rem'>{explanation}</div>",
                                unsafe_allow_html=True,
                            )
                        except Exception as e:
                            st.error(f"분석 실패: {e}")

        # ─── 11) #14 AI 자연어 질의 박스
        st.markdown("---")
        st.markdown("#### AI에게 데이터 질문하기")
        st.caption("예: \"2020년 이후 변동성이 가장 낮은 품목 5개는?\" · \"2022년에 가장 많이 오른 품목 3개 이유는?\"")

        # 예시 질문 버튼
        eq1, eq2, eq3 = st.columns(3)
        sample_queries = [
            "2020년 이후 변동성이 가장 낮은 품목 5개를 알려줘",
            "2022년에 가장 많이 오른 품목 3개와 그 이유는?",
            "서로 가장 다르게 움직이는 품목 쌍을 찾아줘 (분산투자용)",
        ]
        if eq1.button("💡 " + sample_queries[0][:18] + "…", key="sq1", use_container_width=True):
            st.session_state["heat_q"] = sample_queries[0]
        if eq2.button("💡 " + sample_queries[1][:18] + "…", key="sq2", use_container_width=True):
            st.session_state["heat_q"] = sample_queries[1]
        if eq3.button("💡 " + sample_queries[2][:18] + "…", key="sq3", use_container_width=True):
            st.session_state["heat_q"] = sample_queries[2]

        user_q = st.text_area(
            "질문 입력",
            value=st.session_state.get("heat_q", ""),
            height=80,
            placeholder="히트맵 데이터에 대해 궁금한 것을 한국어로 질문해주세요.",
            key="heat_q_input",
        )

        if st.button("🚀 AI에게 물어보기", type="primary", key="heat_ask_btn", use_container_width=True):
            if not user_q.strip():
                st.warning("질문을 입력해주세요.")
            elif not os.getenv("GEMINI_API_KEY", "").strip():
                st.warning("⚠️ Gemini API Key가 설정되지 않았습니다.")
            else:
                try:
                    from agents.ppi_agent import explain_heatmap_query_gemini
                    with st.spinner("Gemini가 히트맵 데이터를 분석 중... (10~30초)"):
                        answer = explain_heatmap_query_gemini(
                            user_question=user_q,
                            heatmap_df=yoy_pivot,
                            corr_df=corr,
                            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                        )
                    st.session_state["heat_last_answer"] = answer
                except Exception as e:
                    err_str = str(e)
                    if any(k in err_str for k in ["503", "UNAVAILABLE", "overloaded"]):
                        st.warning("⏳ Google Gemini 서버 혼잡. 1~2분 후 다시 시도하세요.")
                    else:
                        st.error(f"질의 실패: {err_str}")

        if "heat_last_answer" in st.session_state:
            st.markdown(
                f"<div style='background:linear-gradient(135deg,#fff9f0,#fef3e2);"
                f"padding:1.5rem;border-radius:12px;border-left:4px solid #F29F05;"
                f"margin-top:0.8rem'>{st.session_state['heat_last_answer']}</div>",
                unsafe_allow_html=True,
            )

        # ─── 12) Tier 3-⑪ 자동 리포트 생성 버튼
        st.markdown("---")
        st.markdown("#### 임원 보고용 자동 리포트")
        rc1, rc2 = st.columns(2)
        with rc1:
            if st.button("🧾 Gemini 요약 리포트 생성", key="heat_report_btn", use_container_width=True):
                if not os.getenv("GEMINI_API_KEY", "").strip():
                    st.warning("⚠️ Gemini API Key가 설정되지 않았습니다.")
                else:
                    try:
                        from agents.ppi_agent import generate_heatmap_report_gemini
                        with st.spinner("Gemini가 리포트 작성 중... (15~40초)"):
                            rep = generate_heatmap_report_gemini(
                                heatmap_df=yoy_pivot,
                                corr_df=corr,
                                model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                            )
                        st.session_state["heat_report"] = rep
                    except Exception as e:
                        st.error(f"리포트 생성 실패: {e}")
        with rc2:
            if "heat_report" in st.session_state and st.session_state["heat_report"]:
                # 리포트를 PDF로 다운로드
                try:
                    pdf_bytes = generate_pdf_report(
                        title="히트맵 자동 리포트 (Gemini)",
                        summary={
                            "분석 품목 수": str(len(pivot.index)),
                            "분석 기간": f"{int(pivot.columns.min())}~{int(pivot.columns.max())}년",
                        },
                        body_text=st.session_state["heat_report"],
                        table_df=yoy_pivot.round(2).reset_index(),
                    )
                    st.download_button(
                        "📄 리포트 PDF 다운로드",
                        pdf_bytes,
                        f"히트맵리포트_{int(pivot.columns.min())}_{int(pivot.columns.max())}.pdf",
                        "application/pdf",
                        use_container_width=True,
                        key="heat_pdf_dl",
                    )
                except Exception as e:
                    st.caption(f"PDF 변환 실패: {e}")

        if "heat_report" in st.session_state and st.session_state["heat_report"]:
            st.markdown(
                f"<div style='background:linear-gradient(135deg,#f0f9ff,#ecfeff);"
                f"padding:1.5rem;border-radius:12px;border-left:4px solid #0891B2;"
                f"margin-top:0.8rem'>{st.session_state['heat_report']}</div>",
                unsafe_allow_html=True,
            )

        # ─── 13) Tier 3-⑫ 시간 애니메이션 Playback (월별)
        st.markdown("---")
        st.markdown("#### 시간 Playback — 월별 rolling 12M YoY")
        st.caption("재생 버튼을 눌러 12개월 YoY의 월별 변화를 애니메이션으로 확인합니다.")

        try:
            # 월별 rolling 12M YoY 계산
            dfw = df_month.pivot_table(index="YM", columns="품목", values="PPI", aggfunc="mean").sort_index()
            roll_yoy = (dfw / dfw.shift(12) - 1) * 100
            roll_yoy = roll_yoy.dropna(how="all")

            if len(roll_yoy) > 1:
                # 애니메이션용 long format
                anim_rows = []
                for ym, row in roll_yoy.iterrows():
                    for item, val in row.items():
                        if pd.notna(val):
                            anim_rows.append({"YM": str(ym), "품목": item, "YoY12M(%)": round(float(val), 2)})
                df_anim = pd.DataFrame(anim_rows)

                if not df_anim.empty:
                    fig_anim = px.bar(
                        df_anim, x="품목", y="YoY12M(%)", color="YoY12M(%)",
                        animation_frame="YM",
                        color_continuous_scale=[[0, POSCO_COLORS["success"]],
                                                [0.5, "#F8FAFC"],
                                                [1, POSCO_COLORS["danger"]]],
                        color_continuous_midpoint=0,
                        range_y=[df_anim["YoY12M(%)"].min() - 5, df_anim["YoY12M(%)"].max() + 5],
                        title="월별 12M YoY 변화 (재생 ▶ 클릭)",
                    )
                    fig_anim.update_layout(height=460)
                    st.plotly_chart(fig_anim, use_container_width=True)
                else:
                    st.caption("애니메이션용 데이터 부족 (12개월 이상 필요)")
            else:
                st.caption("rolling 12M YoY 계산을 위해 12개월 이상의 데이터가 필요합니다.")
        except Exception as e:
            st.caption(f"애니메이션 생성 실패: {e}")

        # ─── 14) 상관계수 매트릭스 (기존 유지)
        st.markdown("---")
        st.markdown(section_title("품목 간 가격 동조 상관계수"), unsafe_allow_html=True)
        fig_c = px.imshow(
            corr, color_continuous_scale="RdBu_r",
            zmin=-1, zmax=1, text_auto=".2f",
            title="상관계수 매트릭스 (1=동조, -1=역방향)",
        )
        fig_c.update_layout(height=max(350, 50 * len(corr)))
        st.plotly_chart(fig_c, use_container_width=True)
        st.caption(
            "💡 해석: 상관이 높은 품목끼리는 같이 움직여 **리스크 집중**. "
            "낮거나 음(-)의 상관 품목을 섞으면 **포트폴리오 분산 효과**."
        )



# =========================================================
# Tab: \U0001F52E 물가 예측 (과거 추세 기반)
# =========================================================
with tab_fcst:
    st.markdown(section_title("물가지수 예측 (과거 추세 기반)"), unsafe_allow_html=True)
    st.warning(
        "\u26A0\uFE0F **예측값은 과거 추세의 연장일 뿐, 확정값이 아닙니다.** "
        "원자재 급등·정책 변화 등 외부 충격은 반영되지 않습니다. "
        "미래 투자 계획의 **참고 지표**로만 활용하세요."
    )

    src = st.radio(
        "예측 대상",
        ["\U0001F3ED 설비비 (ECOS PPI)", "\U0001F3D7\uFE0F 공사비 (KOSIS 건설공사비지수)"],
        horizontal=True, key="fcst_src",
    )
    is_ecos = src.startswith("\U0001F3ED")

    fcst_code, fcst_name = None, None
    if is_ecos:
        catalog_f = get_catalog(api_key=os.getenv("ECOS_API_KEY"))
        if catalog_f is None or len(catalog_f) == 0:
            st.error("ECOS 카탈로그 로드 실패")
        else:
            kw = st.text_input("품목 검색", placeholder="예: 변압기, 펌프, 형강", key="fcst_kw")
            if kw.strip():
                m = catalog_f[catalog_f["ITEM_NAME"].astype(str).str.contains(kw.strip(), na=False)]
                if len(m) > 0:
                    opts = m.apply(lambda r: f"{r['ITEM_NAME']} [{r['ITEM_CODE']}]", axis=1).tolist()
                    sel = st.selectbox(f"품목 ({len(m)}개)", opts, key="fcst_ecos_sel")
                    idx = opts.index(sel)
                    fcst_code = str(m.iloc[idx]["ITEM_CODE"])
                    fcst_name = str(m.iloc[idx]["ITEM_NAME"])
                else:
                    st.warning("매칭 품목 없음")
    else:
        _kk = os.getenv("KOSIS_API_KEY", "").strip()
        if not _kk:
            st.info("공사비 예측을 쓰려면 사이드바에 KOSIS 키가 필요합니다.")
        else:
            cat_f = get_construction_catalog(api_key=_kk)
            opts_c = catalog_to_options(cat_f)
            if opts_c:
                labels = [f"{o['name']} [{o['code']}]" for o in opts_c]
                sel = st.selectbox(f"공종 ({len(opts_c)}개)", labels, key="fcst_cci_sel")
                i = labels.index(sel)
                fcst_code = opts_c[i]["code"]; fcst_name = opts_c[i]["name"]

    c1, c2 = st.columns(2)
    horizon = c1.slider("예측 기간 (개월)", 1, MAX_HORIZON, 12, key="fcst_h")
    use_seasonal = c2.checkbox("계절성 반영 (24개월 이상 데이터 권장)", value=True, key="fcst_seasonal")

    if st.button("\U0001F52E 예측 실행", type="primary", use_container_width=True, key="fcst_run"):
        if not fcst_code:
            st.warning("예측할 품목/공종을 선택하세요.")
        else:
            try:
                client_f = get_client() if is_ecos else KOSISClient(api_key=os.getenv("KOSIS_API_KEY"))
                hist_df = client_f.get_ppi(fcst_code, "201501", datetime.now().strftime("%Y%m"))
                if len(hist_df) < 6:
                    st.error("예측에 필요한 과거 데이터가 부족합니다(최소 6개월).")
                else:
                    res_f = forecast_index(hist_df, horizon=horizon, seasonal=use_seasonal)
                    st.session_state["fcst_result"] = {
                        "name": fcst_name, "code": fcst_code, "is_ecos": is_ecos, "res": res_f,
                    }
            except Exception as e:
                st.error(f"\u274C 예측 실패: {e}")
                st.session_state.pop("fcst_result", None)

    if "fcst_result" in st.session_state:
        fr = st.session_state["fcst_result"]
        resf = fr["res"]
        hist, fc, lo, hi = resf["history"], resf["forecast"], resf["lower"], resf["upper"]

        st.caption(f"\U0001F4D0 방법: {resf['method']}")

        last_v = float(hist.iloc[-1]); end_v = float(fc.iloc[-1])
        chg = (end_v / last_v - 1) * 100
        k1, k2, k3 = st.columns(3)
        k1.markdown(kpi_card("현재 지수", f"{last_v:.2f}",
                             delta=hist.index[-1].strftime("%Y-%m"), icon="\U0001F4CD"), unsafe_allow_html=True)
        k2.markdown(kpi_card(f"{len(fc)}개월 후 예측", f"{end_v:.2f}",
                             delta=f"{chg:+.2f}%", delta_type="up" if chg > 0 else "down",
                             icon="\U0001F52E", highlight=True), unsafe_allow_html=True)
        k3.markdown(kpi_card("예측 범위", f"{float(lo.iloc[-1]):.1f}~{float(hi.iloc[-1]):.1f}",
                             delta="95% 신뢰구간", delta_type="neutral", icon="\U0001F4CA"), unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=list(hi.index) + list(lo.index[::-1]),
            y=list(hi.values) + list(lo.values[::-1]),
            fill="toself", fillcolor="rgba(0,94,184,0.12)",
            line=dict(color="rgba(0,0,0,0)"), name="95% 신뢰구간", hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=hist.index, y=hist.values, mode="lines", name="과거 실측",
            line=dict(color=POSCO_COLORS["primary"], width=2.5),
            hovertemplate="<b>%{x|%Y-%m}</b><br>실측: %{y:.2f}<extra></extra>",
        ))
        fc_x = [hist.index[-1]] + list(fc.index)
        fc_y = [float(hist.iloc[-1])] + list(fc.values)
        fig.add_trace(go.Scatter(
            x=fc_x, y=fc_y, mode="lines+markers", name="예측",
            line=dict(color=POSCO_COLORS["danger"], width=2.5, dash="dash"),
            marker=dict(size=5),
            hovertemplate="<b>%{x|%Y-%m}</b><br>예측: %{y:.2f}<extra></extra>",
        ))
        fig.update_layout(
            title=f"{fr['name']} 지수 예측 ({len(fc)}개월)",
            yaxis_title="지수 (2020=100)", height=500, hovermode="x unified",
            legend=dict(orientation="h", y=1.02, x=0),
        )
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("\U0001F4CB 예측값 상세"):
            tblf = pd.DataFrame({
                "시점": [d.strftime("%Y-%m") for d in fc.index],
                "예측 지수": fc.round(2).values,
                "하한(95%)": lo.round(2).values,
                "상한(95%)": hi.round(2).values,
            })
            st.dataframe(tblf, use_container_width=True, hide_index=True)
            csvf = tblf.to_csv(index=False).encode("utf-8-sig")
            st.download_button("\U0001F4E5 예측 CSV", csvf,
                f"예측_{fr['name']}_{len(fc)}개월.csv", "text/csv",
                use_container_width=True, key="fcst_csv")

        st.caption("\u26A0\uFE0F " + resf["warning"])


# ═══════════════════════════════════════════
# Tab 7: 공유 / 내보내기 가이드
# ═══════════════════════════════════════════
with tab_share:
    st.markdown(section_title("결과 공유 & 내보내기"), unsafe_allow_html=True)

    st.markdown("""
    이 앱의 결과를 **동료에게 공유**하거나 **문서로 저장**하는 방법을 안내합니다.
    """)

    with st.container():
        st.markdown("#### 방법 1 — URL 링크 공유")
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
        st.markdown("#### 방법 2 — PDF / Excel 내보내기")
        st.markdown("""
        각 탭 하단의 **다운로드 버튼** 으로 바로 받을 수 있습니다.

        - **Tab 1 AI Agent 환산** → PDF 리포트 + Excel 데이터
        - **Tab 2 설비별 PPI 조회** → CSV, Excel
        - **Tab 3 다중 설비 비교** → Excel 요약
        - **Tab 5 포트폴리오 환산** → PDF 리포트 + Excel
        """)

    st.divider()

    with st.container():
        st.markdown("#### 방법 3 — 스크린샷 / 차트 이미지")
        st.markdown("""
        각 Plotly 차트 오른쪽 위 카메라 아이콘 📷 으로 PNG 이미지 저장 가능.
        """)

    st.divider()

    # 세션 상태 요약
    with st.container():
        st.markdown("#### 현재 세션 요약")
        session_summary = {
            "데이터 소스": "한국은행 ECOS (LIVE)",
            "ECOS Key": "✅ 설정됨" if os.getenv("ECOS_API_KEY") else "❌ 없음",
            "카탈로그": f"{len(get_catalog(api_key=os.getenv('ECOS_API_KEY'))):,}개"
                         if os.getenv("ECOS_API_KEY") else "미연결",
            "LLM": llm_provider,
            "Tab 3 비교 결과": "✅ 저장됨" if "multi_series" in st.session_state else "❌ 없음",
            "Tab 5 포트폴리오": "✅ 저장됨" if "port_results" in st.session_state else "❌ 없음",
        }
        st.json(session_summary)


# ═══════════════════════════════════════════
# 푸터
# ═══════════════════════════════════════════
st.divider()
st.markdown(
    '<div style="text-align:center; color:#848484; font-size:12px; padding:22px 0;">'
    "<b>POSCO 투자비 물가보정 시스템</b> · 한국은행 ECOS 생산자물가지수 · "
    "한국건설기술연구원 건설공사비지수(KOSIS)<br>"
    '<span style="font-size:11px;">© 2026 포스코 투자엔지니어링실 · 내부 검토용 — '
    "「국가계약법」상 계약금액조정 산식과 다르므로 공식 계약 근거로 사용 금지</span>"
    "</div>",
    unsafe_allow_html=True,
)
