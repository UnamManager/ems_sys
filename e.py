import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, datetime
import json

# 1. 페이지 설정 및 최적화
st.set_page_config(page_title="EMS 통합 관리 시스템", layout="wide")
st.markdown("""
    <style>
    [data-testid="stElementToolbar"] { display: none !important; }
    .stButton>button { width: 100%; height: 3em; }
    </style>
    """, unsafe_allow_html=True)

# =========================
# 🔑 세션 상태 및 설정
# =========================
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "user_id" not in st.session_state: st.session_state.user_id = ""
if "auth_res" not in st.session_state: st.session_state.auth_res = False
if "auth_manage" not in st.session_state: st.session_state.auth_manage = False

ADMIN_PASSWORD_RES = "3090"      
ADMIN_PASSWORD_MANAGE = "ua0952"  

# =========================
# 📊 구글 시트 연결 및 데이터 로드 (최적화 핵심)
# =========================
@st.cache_resource
def get_gspread_client():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"시트 연결 실패: {e}")
        return None

client = get_gspread_client()

# [중요] 시트 전체 데이터를 한 번에 가져와서 메모리에 저장 (API 호출 최소화)
@st.cache_data(ttl=600)
def load_full_system_data():
    if not client: return None, {}
    try:
        sh = client.open("EMS")
        # 1. 사용자 목록 로드
        user_ws = sh.worksheet("사용자목록")
        u_raw = user_ws.get_all_values()
        user_dict = {str(row[0]).strip(): str(row[1]).strip() for row in u_raw[1:] if len(row) >= 2}
        
        # 2. 매물 데이터 통합 로드
        sheets = ["1단지_매매","1단지_임대","2단지_매매","2단지_임대","3단지_매매","3단지_임대"]
        cols = ["NO.","분양구분","동","호수","타입","매물구분","매매가","월세","거래여부", "비고"]
        df_list = []
        for s in sheets:
            ws = sh.worksheet(s)
            data = ws.get_all_values()
            if len(data) > 1:
                df = pd.DataFrame(data[1:], columns=cols)
                df["단지"] = s.split("_")[0]
                df["거래유형"] = s.split("_")[1]
                df["매매가_num"] = pd.to_numeric(df["매매가"].str.replace(',', ''), errors='coerce').fillna(0)
                df["월세_num"] = pd.to_numeric(df["월세"].str.replace(',', ''), errors='coerce').fillna(0)
                df["동_num"] = pd.to_numeric(df["동"], errors='coerce').fillna(0)
                df["호_num"] = pd.to_numeric(df["호수"], errors='coerce').fillna(0)
                df_list.append(df)
        
        full_df = pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()
        if not full_df.empty:
            full_df = full_df.sort_values(by=["단지", "동_num", "호_num"])
            
        return full_df, user_dict
    except Exception as e:
        st.error(f"데이터 로드 에러: {e}")
        return pd.DataFrame(), {}

# 데이터 실행
df_total, user_dict = load_full_system_data()

# =========================
# 🔒 로그인 로직
# =========================
if not st.session_state.logged_in:
    st.title("🔒 EMS 협력사 시스템")
    with st.form("login"):
        u_id = st.text_input("아이디(상호)").strip()
        u_pw = st.text_input("비밀번호", type="password").strip()
        if st.form_submit_button("로그인"):
            if u_id in user_dict and user_dict[u_id] == u_pw:
                st.session_state.logged_in = True
                st.session_state.user_id = u_id
                st.rerun()
            else: st.error("❌ 정보를 확인해주세요.")
    st.stop()

# =========================
# 🏠 메인 메뉴 설정 (버그 원천 차단)
# =========================
menu_options = ["📊 실시간 매물 현황", "🔍 등록 매물 조회"]
if st.session_state.auth_res: menu_options.append("📅 세대관람 예약")
if st.session_state.auth_manage: menu_options.append("⚙️ 매물 통합 관리")

with st.sidebar:
    st.success(f"👤 {st.session_state.user_id}님")
    choice = st.radio("메뉴 이동", menu_options)
    
    with st.expander("🛠️ 시스템 인증"):
        code = st.text_input("관리자 코드", type="password")
        if code == ADMIN_PASSWORD_RES and not st.session_state.auth_res:
            st.session_state.auth_res = True
            st.rerun()
        elif code == ADMIN_PASSWORD_MANAGE and not st.session_state.auth_manage:
            st.session_state.auth_manage = True
            st.rerun()
            
    if st.button("🔄 새로고침"):
        st.cache_data.clear()
        st.rerun()
    if st.button("🚪 로그아웃"):
        st.session_state.clear()
        st.rerun()

# --- 헬퍼 함수 ---
def show_styled_df(df):
    cols_to_show = ["분양구분","동","호수","타입","매물구분","매매가","월세","거래여부","비고"]
    st.dataframe(df[cols_to_show], use_container_width=True, hide_index=True)

# =========================
# 📋 페이지별 콘텐츠
# =========================
if choice == "📊 실시간 매물 현황":
    st.title("📊 실시간 현황")
    c1, c2, c3 = st.columns(3)
    c1.metric("📌 전체", f"{len(df_total)}개")
    c2.metric("✅ 완료", f"{len(df_total[df_total['거래여부']=='거래완료'])}개")
    c3.metric("🏠 가능", f"{len(df_total[df_total['거래여부']=='관람가능'])}개")
    st.divider()
    show_styled_df(df_total[df_total["거래여부"]=="거래완료"])

elif choice == "🔍 등록 매물 조회":
    st.title("🔍 매물 조회")
    f1, f2, f3 = st.columns(3)
    danji = f1.multiselect("단지", df_total["단지"].unique())
    bunyang = f2.multiselect("분양구분", df_total["분양구분"].unique())
    gubun = f3.multiselect("매물구분", df_total["매물구분"].unique())
    
    d1, d2 = st.columns(2)
    s_dong = d1.text_input("🏢 동")
    s_ho = d2.text_input("🔑 호수")
    
    res = df_total.copy()
    if danji: res = res[res["단지"].isin(danji)]
    if bunyang: res = res[res["분양구분"].isin(bunyang)]
    if gubun: res = res[res["매물구분"].isin(gubun)]
    if s_dong: res = res[res["동"] == s_dong]
    if s_ho: res = res[res["호수"] == s_ho]
    show_styled_df(res)

elif choice == "📅 세대관람 예약":
    st.title("📅 세대관람 예약")
    # [인증된 경우에만 로직 실행]
    res_dj = st.selectbox("단지 선택", ["1단지", "2단지", "3단지"])
    f_unit = df_total[df_total["단지"] == res_dj]
    
    with st.form("res_form"):
        c1, c2, c3 = st.columns(3)
        dong = c1.selectbox("동", sorted(f_unit["동"].unique()))
        ho = c2.selectbox("호수", sorted(f_unit[f_unit["동"]==dong]["호수"].unique()))
        r_name = c3.text_input("성함")
        if st.form_submit_button("예약하기"):
            try:
                sh = client.open("EMS")
                ws = sh.worksheet(f"{res_dj}_관람예약")
                ws.append_row([str(date.today()), r_name, st.session_state.user_id, "1세대", dong, ho])
                st.success("예약 신청 완료!"); st.cache_data.clear()
            except: st.error("기록 실패")

elif choice == "⚙️ 매물 통합 관리":
    st.title("⚙️ 매물 통합 관리")
    # [인증된 경우에만 로직 실행]
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        e_dj = c1.selectbox("단지", ["1단지", "2단지", "3단지"], key="e1")
        e_dong = c2.text_input("동", key="e2")
        e_ho = c3.text_input("호수", key="e3")
        
        if e_dong and e_ho:
            target = df_total[(df_total["단지"] == e_dj) & (df_total["동"] == e_dong) & (df_total["호수"] == e_ho)]
            if not target.empty:
                curr = target.iloc[0]
                with st.form("edit"):
                    st.write(f"현재 상태: {curr['거래여부']}")
                    new_st = st.selectbox("변경 상태", ["관람가능", "거래완료"])
                    if st.form_submit_button("상태 업데이트"):
                        try:
                            sh = client.open("EMS")
                            ws = sh.worksheet(f"{e_dj}_{curr['거래유형']}")
                            rows = ws.get_all_values()
                            idx = next(i+1 for i,r in enumerate(rows) if r[2]==e_dong and r[3]==e_ho)
                            ws.update_cell(idx, 9, new_st)
                            st.success("업데이트 완료!"); st.cache_data.clear(); st.rerun()
                        except: st.error("업데이트 실패")
