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
        gap: 1px;
    }
    .stTabs [aria-selected="true"] { background-color: #004c7a !important; color: white !important; }
</style>
""", unsafe_allow_html=True)

# 헤더
st.markdown("<h1 style='text-align:center;color:#002b45;padding-bottom:20px;'>🏢 EMS 매물등록관리시스템</h1>", unsafe_allow_html=True)

# ------------------------------
# 데이터 로딩 함수 (캐싱 적용)
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
    st.image("https://cdn-icons-png.flaticon.com/512/609/609803.png", width=80) # 예시 아이콘
    st.title("EMS Menu")
    choice = st.selectbox("이동할 메뉴를 선택하세요", ["🏠 통합 대시보드", "🔍 매물 상세조회", "🔐 관리자 페이지"])

# =========================
# 1️⃣ 통합 대시보드 (UI 업그레이드: 지표카드 + 필터)
# =========================
if choice == "🏠 통합 대시보드":
    # 상단 요약 지표 (UI 업그레이드)
    total_m = len(df_total)
    avail_m = len(df_total[df_total["거래여부"] == "관람가능"])
    
    m1, m2, m3 = st.columns(3)
    m1.metric("📌 전체 관리 매물", f"{total_m}개")
    m2.metric("✅ 현재 관람 가능", f"{avail_m}개", delta=f"{(avail_m/total_m*100):.1f}%")
    m3.metric("📅 오늘의 날짜", date.today().strftime("%m/%d"))

    st.divider()

    # 필터 섹션 (UI 업그레이드: Pills 활용)
    st.subheader("🔍 빠른 필터링")
    f_col1, f_col2 = st.columns([1, 2])
    
    danji_filter = f_col1.multiselect("단지 선택", df_total["단지"].unique(), default=df_total["단지"].unique())
    # 상태 필터는 버튼 형식으로 (UI 업그레이드)
    status_filter = st.multiselect("거래여부 필터", df_total["거래여부"].unique(), default=["관람가능"])

    df_filtered = df_total[
        (df_total["단지"].isin(danji_filter)) & 
        (df_total["거래여부"].isin(status_filter))
    ]

    # 데이터 표 (AgGrid 유지)
    gb = GridOptionsBuilder.from_dataframe(df_filtered)
    gb.configure_pagination(paginationAutoPageSize=True)
    gb.configure_default_column(resizable=True, filterable=True)
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
# 3️⃣ 관리자 페이지 (UI 업그레이드: 카드형 현황표)
# =========================
elif choice == "🔐 관리자 페이지":
    if not st.session_state.admin_auth:
        pwd = st.text_input("관리자 비밀번호", type="password")
        if pwd == ADMIN_PASSWORD:
            st.session_state.admin_auth = True
            st.rerun()
        elif pwd: st.error("❌ 비밀번호가 틀렸습니다.")
        st.stop()

    tab1, tab2, tab3 = st.tabs(["📅 관람 예약등록", "📊 실시간 현황표", "⚙️ 시스템 관리"])

    # --- 📅 관람 예약등록 ---
    with tab1:
        res_danji = st.selectbox("단지 선택", ["1단지","2단지","3단지"], key="r_dj")
        filtered_unit = df_total[df_total["단지"] == res_danji]
        
        with st.form("res_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            name = col1.text_input("예약자/중개업소")
            time_sel = col2.selectbox("예약시간", [f"{h:02d}:00~{h+1:02d}:00" for h in range(8,21)])
            
            count = st.slider("관람 세대수", 1, 3, 1)
            세대목록 = []
            for i in range(count):
                cols = st.columns(3)
                dongs = sorted(filtered_unit["동"].unique())
                dong = cols[0].selectbox(f"{i+1}번째 동", dongs, key=f"d_{i}")
                hosus = sorted(filtered_unit[filtered_unit["동"] == dong]["호수"].unique())
                ho = cols[1].selectbox(f"{i+1}번째 호수", hosus, key=f"h_{i}")
                
                m = filtered_unit[(filtered_unit["동"]==dong) & (filtered_unit["호수"]==ho)].iloc[0]
                cols[2].info(f"{m['타입']} / {m['거래여부']}")
                세대목록.append({"동":dong, "호수":ho, "타입":m['타입'], "상태":m['거래여부']})
            
            submit = st.form_submit_button("✅ 예약 저장")
            if submit:
                if any(s["상태"] == "거래완료" for s in 세대목록):
                    st.error("❌ 거래완료 세대가 포함되어 예약할 수 없습니다.")
                else:
                    # 저장 로직 (배치 업데이트)
                    target_name = f"{res_danji}_관람예약" if int(time_sel[:2]) < 16 else "야간_관람예약"
                    ws = sheet.worksheet(target_name)
                    new_rows = [[date.today().strftime("%Y-%m-%d"), name, "", f"{count}세대", s["동"], s["호수"], s["타입"], time_sel, "", ""] for s in 세대목록]
                    ws.append_rows(new_rows)
                    st.success("🎉 예약이 완료되었습니다!")
                    st.cache_data.clear()

    # --- 📊 실시간 현황표 (UI 업그레이드: 카드형 레이아웃) ---
    with tab2:
        v_col1, v_col2 = st.columns(2)
        v_danji = v_col1.selectbox("단지", ["1단지","2단지","3단지","야간"], key="v_dj")
        v_date = v_col2.date_input("날짜", date.today())
        
        ws_name = f"{v_danji}_관람예약" if v_danji != "야간" else "야간_관람예약"
        data = sheet.worksheet(ws_name).get_all_values()
        df_res = pd.DataFrame(data[1:], columns=["예약날짜","예약자","중개업소","관람세대수","동","호수","타입","예약시간","동행매니저","비고"])
        df_today = df_res[df_res["예약날짜"] == v_date.strftime("%Y-%m-%d")]

        if df_today.empty:
            st.info("ℹ️ 해당 날짜에 예약이 없습니다.")
        else:
            for _, r in df_today.iterrows():
                with st.container(border=True): # UI 업그레이드: 카드형 컨테이너
                    c1, c2, c3 = st.columns([2, 3, 1])
                    c1.markdown(f"**⏰ {r['예약시간']}**")
                    c2.markdown(f"**🏠 {r['동']}동 {r['호수']}호** ({r['타입']})")
                    c3.write(f"{r['예약자']}")

    # --- ⚙️ 시스템 관리 ---
    with tab3:
        if st.button("🔄 데이터 전체 강제 새로고침"):
            st.cache_data.clear()
            st.rerun()
            
        st.divider()
        st.subheader("📍 매물 상태 즉시 변경")
        u_col1, u_col2, u_col3 = st.columns(3)
        u_dj = u_col1.selectbox("단지", ["1단지","2단지","3단지"], key="u_dj")
        u_dong = u_col2.selectbox("동", sorted(df_total[df_total["단지"]==u_dj]["동"].unique()), key="u_dg")
        u_ho = u_col3.selectbox("호수", sorted(df_total[(df_total["단지"]==u_dj) & (df_total["동"]==u_dong)]["호수"].unique()), key="u_h")
        
        curr = df_total[(df_total["단지"]==u_dj) & (df_total["동"]==u_dong) & (df_total["호수"]==u_ho)].iloc[0]
        new_stat = st.radio("변경할 상태", ["관람가능", "거래완료"], index=0 if curr["거래여부"]=="관람가능" else 1, horizontal=True)
        
        if st.button("💾 상태 업데이트"):
            ws = sheet.worksheet(f"{u_dj}_{curr['거래유형']}")
            all_v = ws.get_all_values()
            for i, row in enumerate(all_v):
                if row[2] == u_dong and row[3] == u_ho:
                    ws.update_cell(i+1, 9, new_stat)
                    break
            st.success("✅ 변경 완료!")
            st.cache_data.clear()
            st.rerun()
