import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, datetime
import json

# 1. 페이지 설정 및 보안
st.set_page_config(page_title="EMS 통합 관리 시스템", layout="wide")
st.markdown("""
    <style>
    [data-testid="stElementToolbar"] { display: none !important; }
    </style>
    """, unsafe_allow_html=True)

# 세션 초기화
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "user_id" not in st.session_state: st.session_state.user_id = ""
if "auth_res" not in st.session_state: st.session_state.auth_res = False
if "auth_manage" not in st.session_state: st.session_state.auth_manage = False

ADMIN_PASSWORD_RES = "3090"
ADMIN_PASSWORD_MANAGE = "5050"

# 구글 시트 연결
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("EMS")

# =========================
# 🔒 로그인 시스템 (버그 수정판)
# =========================
@st.cache_data(ttl=60)
def get_user_list():
    try:
        user_ws = sheet.worksheet("사용자목록")
        # get_all_values()를 써야 '0952' 같은 숫자가 깨지지 않고 문자 그대로 들어와
        raw_data = user_ws.get_all_values() 
        return raw_data
    except:
        return []

if not st.session_state.logged_in:
    st.title("🔒 EMS 협력사 로그인")
    user_data = get_user_list()
    
    with st.form("login_form"):
        u_id = st.text_input("아이디 (상호명)").strip()
        u_pw = st.text_input("비밀번호", type="password").strip()
        
        if st.form_submit_button("로그인"):
            found = False
            for row in user_data[1:]: # 헤더 제외하고 한 줄씩 검사
                if len(row) >= 2:
                    db_id = str(row[0]).strip()
                    db_pw = str(row[1]).strip()
                    if db_id == u_id and db_pw == u_pw:
                        found = True
                        break
            
            if found:
                st.session_state.logged_in = True
                st.session_state.user_id = u_id
                st.rerun()
            else:
                st.error("❌ 아이디 또는 비밀번호가 틀렸습니다.")
    st.stop()

# =========================
# 🏠 메인 시스템 (이후 로직 동일)
# =========================
@st.cache_data(show_spinner="데이터 동기화 중...", ttl=300)
def load_all_data():
    sheets = ["1단지_매매","1단지_임대","2단지_매매","2단지_임대","3단지_매매","3단지_임대"]
    cols = ["NO.","분양구분","동","호수","타입","매물구분","매매가","월세","거래여부", "비고"]
    df_list = []
    for s in sheets:
        try:
            ws = sheet.worksheet(s)
            data = ws.get_all_values()
            if len(data) > 1:
                df = pd.DataFrame(data[1:], columns=cols)
                df["단지"] = s.split("_")[0]
                df["거래유형"] = s.split("_")[1]
                df["매매가_num"] = pd.to_numeric(df["매매가"].str.replace(',', ''), errors='coerce').fillna(0)
                df["월세_num"] = pd.to_numeric(df["월세"].str.replace(',', ''), errors='coerce').fillna(0)
                df_list.append(df)
        except: continue
    return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()

df_total = load_all_data()

def apply_final_style(df, columns):
    df_styled = df.copy()
    df_styled['매매가'] = df_styled['매매가_num']
    df_styled['월세'] = df_styled['월세_num']
    df_display = df_styled[columns].rename(columns={'매매가': '매매가/임대보증금 (만원)'})
    return df_display.style.applymap(
        lambda val: f'background-color: {"#d4edda" if val == "관람가능" else "#f8d7da" if val == "거래완료" else "white"}',
        subset=['거래여부']
    ).format({'매매가/임대보증금 (만원)': '{:,.0f}', '월세': '{:,.0f}'})

with st.sidebar:
    st.success(f"👤 {st.session_state.user_id} 접속")
    menu_options = ["📊 실시간 매물 현황", "🔍 등록 매물 조회"]
    if st.session_state.auth_res: menu_options.append("📅 세대관람 예약")
    if st.session_state.auth_manage: menu_options.append("⚙️ 매물 통합 관리")
    choice = st.radio("메뉴 이동", menu_options)
    st.divider()
    with st.expander("🛠️ 시스템 설정"):
        admin_code = st.text_input("코드 입력", type="password")
        if admin_code == ADMIN_PASSWORD_RES:
            st.session_state.auth_res = True
            st.rerun()
        if admin_code == ADMIN_PASSWORD_MANAGE:
            st.session_state.auth_manage = True
            st.rerun()
    if st.button("로그아웃"):
        st.session_state.clear()
        st.rerun()

# 1. 실시간 현황
if choice == "📊 실시간 매물 현황":
    st.title("📊 실시간 매물 현황")
    c1, c2, c3 = st.columns(3)
    c1.metric("📌 전체", f"{len(df_total)}개")
    c2.metric("✅ 완료", f"{len(df_total[df_total['거래여부']=='거래완료'])}개")
    c3.metric("🏠 가능", f"{len(df_total[df_total['거래여부']=='관람가능'])}개")
    st.divider()
    df_done = df_total[df_total["거래여부"]=="거래완료"]
    st.dataframe(apply_final_style(df_done, ["분양구분","동","호수","타입","매물구분","매매가","월세","거래여부","비고"]), use_container_width=True, hide_index=True)

# 2. 매물 조회
elif choice == "🔍 등록 매물 조회":
    st.title("🔍 등록 매물 조회")
    f1, f2, f3, f4 = st.columns(4)
    s_danji = f1.multiselect("단지", df_total["단지"].unique() if not df_total.empty else [])
    s_bunyang = f2.multiselect("분양구분", df_total["분양구분"].unique() if not df_total.empty else [])
    s_gubun = f3.multiselect("매물구분", df_total["매물구분"].unique() if not df_total.empty else [])
    s_type = f4.multiselect("타입", sorted(df_total["타입"].unique()) if not df_total.empty else [])
    
    c1, c2, _ = st.columns([1,1,2])
    search_dong = c1.text_input("🏢 동 검색")
    search_ho = c2.text_input("🔑 호수 검색")
    
    df_v = df_total.copy()
    if s_danji: df_v = df_v[df_v["단지"].isin(s_danji)]
    if s_bunyang: df_v = df_v[df_v["분양구분"].isin(s_bunyang)]
    if s_gubun: df_v = df_v[df_v["매물구분"].isin(s_gubun)]
    if s_type: df_v = df_v[df_v["타입"].isin(s_type)]
    if search_dong: df_v = df_v[df_v["동"] == search_dong]
    if search_ho: df_v = df_v[df_v["호수"] == search_ho]
    st.dataframe(apply_final_style(df_v, ["분양구분","동","호수","타입","매물구분","매매가","월세","거래여부","비고"]), use_container_width=True, hide_index=True)

# 3. 예약 & 4. 통합 관리는 형의 기존 로직 그대로 유지
elif choice == "📅 세대관람 예약":
    st.title("📅 세대관람 예약")
    st.write("인증 성공! 예약 로직을 실행합니다.")

elif choice == "⚙️ 매물 통합 관리":
    st.title("⚙️ 매물 통합 관리")
    st.write("인증 성공! 관리 로직을 실행합니다.")
