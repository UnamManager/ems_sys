import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date
from st_aggrid import AgGrid, GridOptionsBuilder
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
    div[data-testid="stMetricValue"] { font-size: 24px; color: #004c7a; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='text-align:center;color:#002b45;'>🏢 EMS 매물등록관리시스템</h1>", unsafe_allow_html=True)

# ------------------------------
# 데이터 로딩 함수
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
choice = st.sidebar.selectbox("메뉴 선택", ["🏠 통합 대시보드", "🔍 매물 상세조회", "🔐 관리자 페이지"])

# =========================
# 1️⃣ 통합 대시보드
# =========================
if choice == "🏠 통합 대시보드":
    if df_total.empty:
        st.warning("⚠️ 데이터가 없습니다.")
    else:
        total_m = len(df_total)
        avail_m = len(df_total[df_total["거래여부"] == "관람가능"])
        m1, m2, m3 = st.columns(3)
        m1.metric("📌 전체 매물", f"{total_m}개")
        m2.metric("✅ 관람 가능", f"{avail_m}개")
        m3.metric("📅 오늘", date.today().strftime("%m/%d"))

        st.divider()
        status_opt = df_total["거래여부"].unique().tolist()
        status_default = ["관람가능"] if "관람가능" in status_opt else status_opt
        st.multiselect("거래여부 필터", status_opt, default=status_default, key="main_filter")
        
        gb = GridOptionsBuilder.from_dataframe(df_total)
        gb.configure_pagination(paginationAutoPageSize=True)
        AgGrid(df_total, gridOptions=gb.build(), height=500, theme='balham')

# =========================
# 2️⃣ 매물 상세조회
# =========================
elif choice == "🔍 매물 상세조회":
    c1, c2 = st.columns(2)
    sel_danji = c1.selectbox("단지 선택", ["1단지","2단지","3단지"])
    sel_type = c2.selectbox("거래유형", ["매매","임대"])
    df_view = df_total[(df_total["단지"] == sel_danji) & (df_total["거래유형"] == sel_type)]
    st.dataframe(df_view, use_container_width=True)

# =========================
# 3️⃣ 관리자 페이지
# =========================
elif choice == "🔐 관리자 페이지":
    if not st.session_state.admin_auth:
        pwd = st.text_input("관리자 비밀번호", type="password")
        if pwd == ADMIN_PASSWORD:
            st.session_state.admin_auth = True
            st.rerun()
        st.stop()

    tab1, tab2, tab3 = st.tabs(["📅 예약등록", "📊 현황표", "⚙️ 관리"])

    # --- 📅 예약등록 (에러 수정됨) ---
    with tab1:
        res_danji = st.selectbox("단지 선택", ["1단지","2단지","3단지"], key="res_dj_box")
        f_unit = df_total[df_total["단지"] == res_danji]
        
        if f_unit.empty:
            st.error("해당 단지에 매물 데이터가 없습니다.")
        else:
            with st.form("res_form_new"):
                res_name = st.text_input("예약자/업체명")
                res_count = st.number_input("관람 세대수", 1, 3, 1)
                
                final_list = []
                has_error = False
                
                for i in range(res_count):
                    c1, c2, c3 = st.columns(3)
                    d_list = sorted(f_unit["동"].unique())
                    d_val = c1.selectbox(f"{i+1} 동", d_list, key=f"res_d_{i}")
                    
                    h_list = sorted(f_unit[f_unit["동"] == d_val]["호수"].unique())
                    h_val = c2.selectbox(f"{i+1} 호", h_list, key=f"res_h_{i}")
                    
                    # 💡 IndexError 방지 로직
                    match = f_unit[(f_unit["동"]==d_val) & (f_unit["호수"]==h_val)]
                    if not match.empty:
                        m_info = match.iloc[0]
                        c3.info(f"{m_info['타입']} / {m_info['거래여부']}")
                        if m_info['거래여부'] == "거래완료": has_error = True
                        final_list.append({"동":d_val, "호수":h_val, "타입":m_info['타입']})
                
                t_val = st.selectbox("시간", [f"{h:02d}:00~{h+1:02d}:00" for h in range(8,21)])
                
                # 💡 폼 제출 버튼 (Missing Submit Button 해결)
                submitted = st.form_submit_button("예약 확정 저장")
                
                if submitted:
                    if not res_name:
                        st.error("예약자 이름을 입력해주세요.")
                    elif has_error:
                        st.error("거래완료된 세대가 포함되어 있습니다.")
                    else:
                        ws_target = f"{res_danji}_관람예약" if int(t_val[:2]) < 16 else "야간_관람예약"
                        ws = sheet.worksheet(ws_target)
                        rows = [[date.today().strftime("%Y-%m-%d"), res_name, "", f"{res_count}세대", s["동"], s["호수"], s["타입"], t_val, "", ""] for s in final_list]
                        ws.append_rows(rows)
                        st.success("✅ 예약이 저장되었습니다!")
                        st.cache_data.clear()

    # --- 📊 현황표 ---
    with tab2:
        v_dj = st.selectbox("조회 단지", ["1단지","2단지","3단지","야간"])
        v_date = st.date_input("조회 날짜", date.today())
        try:
            ws_n = f"{v_dj}_관람예약" if v_dj != "야간" else "야간_관람예약"
            v_data = sheet.worksheet(ws_n).get_all_values()
            df_v = pd.DataFrame(v_data[1:], columns=["예약날짜","예약자","중개업소","관람세대수","동","호수","타입","예약시간","동행매니저","비고"])
            df_v = df_v[df_v["예약날짜"] == v_date.strftime("%Y-%m-%d")]
            if df_v.empty: st.info("예약 없음")
            else: st.table(df_v[["예약시간", "동", "호수", "예약자"]])
        except: st.error("시트를 불러올 수 없습니다.")

    # --- ⚙️ 관리 ---
    with tab3:
        if st.button("🔄 시스템 새로고침"):
            st.cache_data.clear()
            st.rerun()
        
        st.divider()
        u_dj = st.selectbox("상태변경 단지", ["1단지","2단지","3단지"])
        u_f = df_total[df_total["단지"] == u_dj]
        if not u_f.empty:
            c1, c2 = st.columns(2)
            u_d = c1.selectbox("동", sorted(u_f["동"].unique()), key="u_d_sel")
            u_h = c2.selectbox("호수", sorted(u_f[u_f["동"] == u_d]["호수"].unique()), key="u_h_sel")
            
            # 💡 상태변경 시에도 IndexError 방지
            u_match = u_f[(u_f["동"]==u_d) & (u_f["호수"]==u_h)]
            if not u_match.empty:
                u_curr = u_match.iloc[0]
                new_s = st.radio("상태 변경", ["관람가능", "거래완료"], index=0 if u_curr["거래여부"]=="관람가능" else 1)
                if st.button("💾 즉시 반영"):
                    ws = sheet.worksheet(f"{u_dj}_{u_curr['거래유형']}")
                    vals = ws.get_all_values()
                    for idx, r in enumerate(vals):
                        if r[2] == u_d and r[3] == u_h:
                            ws.update_cell(idx+1, 9, new_s)
                            break
                    st.success("반영 완료!")
                    st.cache_data.clear()
                    st.rerun()
