import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date
from st_aggrid import AgGrid, GridOptionsBuilder
import smtplib
from email.mime.text import MIMEText
import json
import os

# 페이지 설정
st.set_page_config(page_title="EMS 관람예약 시스템", layout="wide")

# =========================
# 🔐 관리자 세션 및 환경 설정
# =========================
if "admin_auth" not in st.session_state:
    st.session_state.admin_auth = False

ADMIN_PASSWORD = "3090"

# 구글 시트 인증
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("EMS")

# =========================
# CSS (디자인 업그레이드)
# =========================
st.markdown("""
<style>
    .main {background-color: #f8f9fa;}
    div[data-testid="stMetricValue"] { font-size: 28px; color: #004c7a; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #f0f2f6;
        border-radius: 5px 5px 0px 0px;
    }
    .stTabs [aria-selected="true"] { background-color: #004c7a !important; color: white !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='text-align:center;color:#002b45;padding-bottom:20px;'>🏢 EMS 매물등록관리시스템</h1>", unsafe_allow_html=True)

# ------------------------------
# 데이터 로딩 함수 (캐싱 및 에러 방지)
# ------------------------------
@st.cache_data(show_spinner="데이터 동기화 중...", ttl=300)
def load_all_data():
    sheets = ["1단지_매매","1단지_임대","2단지_매매","2단지_임대","3단지_매매","3단지_임대"]
    cols = ["NO.","분양구분","동","호수","타입","매물구분","매매가","월세","거래여부"]
    df_list = []
    for s in sheets:
        try:
            ws = sheet.worksheet(s)
            data = ws.get_all_values()
            if len(data) > 1:
                df = pd.DataFrame(data[1:], columns=cols)
                df["단지"] = s.split("_")[0]
                df["거래유형"] = s.split("_")[1]
                df_list.append(df)
        except: continue
    return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame(columns=cols + ["단지", "거래유형"])

df_total = load_all_data()

# ------------------------------
# 사이드바 메뉴
# ------------------------------
with st.sidebar:
    st.title("EMS Menu")
    choice = st.selectbox("메뉴 선택", ["🏠 통합 대시보드", "🔍 매물 상세조회", "🔐 관리자 페이지"])

# =========================
# 1️⃣ 통합 대시보드 (에러 방지 로직 포함)
# =========================
if choice == "🏠 통합 대시보드":
    if df_total.empty:
        st.warning("⚠️ 표시할 매물 데이터가 없습니다. 시트를 확인하거나 새로고침 해주세요.")
        if st.button("데이터 다시 읽기"):
            st.cache_data.clear()
            st.rerun()
    else:
        # 상단 요약 지표 (ZeroDivisionError 방지)
        total_m = len(df_total)
        avail_m = len(df_total[df_total["거래여부"] == "관람가능"])
        
        m1, m2, m3 = st.columns(3)
        m1.metric("📌 전체 관리 매물", f"{total_m}개")
        if total_m > 0:
            m2.metric("✅ 현재 관람 가능", f"{avail_m}개", delta=f"{(avail_m/total_m*100):.1f}%")
        else:
            m2.metric("✅ 현재 관람 가능", "0개")
        m3.metric("📅 오늘의 날짜", date.today().strftime("%m/%d"))

        st.divider()

        # 필터 섹션 (StreamlitAPIException 방지)
        st.subheader("🔍 필터링")
        f_col1, f_col2 = st.columns(2)
        
        danji_opt = df_total["단지"].unique().tolist()
        danji_filter = f_col1.multiselect("단지 선택", danji_opt, default=danji_opt)
        
        status_opt = df_total["거래여부"].unique().tolist()
        # "관람가능"이 데이터에 있을 때만 기본값으로 설정
        status_default = ["관람가능"] if "관람가능" in status_opt else status_opt
        status_filter = f_col2.multiselect("거래여부 필터", status_opt, default=status_default)

        df_filtered = df_total[(df_total["단지"].isin(danji_filter)) & (df_total["거래여부"].isin(status_filter))]

        gb = GridOptionsBuilder.from_dataframe(df_filtered)
        gb.configure_pagination(paginationAutoPageSize=True)
        AgGrid(df_filtered, gridOptions=gb.build(), height=500, theme='balham')

# =========================
# 2️⃣ 매물 상세조회
# =========================
elif choice == "🔍 매물 상세조회":
    c1, c2 = st.columns(2)
    sel_danji = c1.selectbox("단지 선택", ["1단지","2단지","3단지"])
    sel_type = c2.selectbox("거래유형", ["매매","임대"])
    df_view = df_total[(df_total["단지"] == sel_danji) & (df_total["거래유형"] == sel_type)]
    st.dataframe(df_view, use_container_width=True, hide_index=True)

# =========================
# 3️⃣ 관리자 페이지
# =========================
elif choice == "🔐 관리자 페이지":
    if not st.session_state.admin_auth:
        pwd = st.text_input("관리자 비밀번호", type="password")
        if pwd == ADMIN_PASSWORD:
            st.session_state.admin_auth = True
            st.rerun()
        elif pwd: st.error("❌ 비밀번호 오류")
        st.stop()

    tab1, tab2, tab3 = st.tabs(["📅 관람 예약등록", "📊 실시간 현황표", "⚙️ 시스템 관리"])

    with tab1:
        res_danji = st.selectbox("단지 선택", ["1단지","2단지","3단지"])
        f_unit = df_total[df_total["단지"] == res_danji]
        
        with st.form("res_form", clear_on_submit=True):
            name = st.text_input("예약자/업체명")
            count = st.number_input("관람 세대수", 1, 3)
            세대목록 = []
            for i in range(count):
                cols = st.columns(3)
                dong = cols[0].selectbox(f"{i+1} 동", sorted(f_unit["동"].unique()), key=f"d_{i}")
                ho = cols[1].selectbox(f"{i+1} 호", sorted(f_unit[f_unit["동"] == dong]["호수"].unique()), key=f"h_{i}")
                m = f_unit[(f_unit["동"]==dong) & (f_unit["호수"]==ho)].iloc[0]
                cols[2].info(f"{m['타입']} / {m['거래여부']}")
                세대목록.append({"동":dong, "호수":ho, "타입":m['타입'], "상태":m['거래여부']})
            
            t_sel = st.selectbox("시간", [f"{h:02d}:00~{h+1:02d}:00" for h in range(8,21)])
            if st.form_submit_button("예약 저장"):
                if any(s["상태"] == "거래완료" for s in 세대목록):
                    st.error("❌ 거래완료 세대 포함")
                else:
                    target = f"{res_danji}_관람예약" if int(t_sel[:2]) < 16 else "야간_관람예약"
                    ws = sheet.worksheet(target)
                    new_rows = [[date.today().strftime("%Y-%m-%d"), name, "", f"{count}세대", s["동"], s["호수"], s["타입"], t_sel, "", ""] for s in 세대목록]
                    ws.append_rows(new_rows)
                    st.success("✅ 예약 완료!")
                    st.cache_data.clear()

    with tab2:
        v_dj = st.selectbox("현황 단지", ["1단지","2단지","3단지","야간"])
        v_date = st.date_input("날짜", date.today())
        ws_n = f"{v_dj}_관람예약" if v_dj != "야간" else "야간_관람예약"
        data = sheet.worksheet(ws_n).get_all_values()
        df_res = pd.DataFrame(data[1:], columns=["예약날짜","예약자","중개업소","관람세대수","동","호수","타입","예약시간","동행매니저","비고"])
        df_today = df_res[df_res["예약날짜"] == v_date.strftime("%Y-%m-%d")]
        if df_today.empty: st.info("예약 없음")
        else:
            for _, r in df_today.iterrows():
                with st.container(border=True):
                    c1, c2 = st.columns([1, 2])
                    c1.write(f"⏰ {r['예약시간']}")
                    c2.write(f"🏠 {r['동']}동 {r['호수']}호 ({r['예약자']})")

    with tab3:
        st.subheader("📍 매물 상태 실시간 변경")
        if st.button("🔄 전체 캐시 새로고침"):
            st.cache_data.clear()
            st.rerun()
            
        u_dj = st.selectbox("단지 선택", ["1단지","2단지","3단지"])
        u_unit = df_total[df_total["단지"] == u_dj]
        u_dong = st.selectbox("동", sorted(u_unit["동"].unique()))
        u_ho = st.selectbox("호수", sorted(u_unit[u_unit["동"] == u_dong]["호수"].unique()))
        
        curr = u_unit[(u_unit["동"]==u_dong) & (u_unit["호수"]==u_ho)].iloc[0]
        st.write(f"현재: **{curr['거래여부']}**")
        new_stat = st.radio("변경", ["관람가능", "거래완료"], horizontal=True)
        
        if st.button("💾 상태 즉시 반영"):
            ws = sheet.worksheet(f"{u_dj}_{curr['거래유형']}")
            all_v = ws.get_all_values()
            for i, row in enumerate(all_v):
                if row[2] == u_dong and row[3] == u_ho:
                    ws.update_cell(i+1, 9, new_stat)
                    break
            st.success("업데이트 성공!")
            st.cache_data.clear() # 💡 핵심 팁: 변경 후 캐시를 비워야 대시보드에 즉시 반영됨
            st.rerun()
