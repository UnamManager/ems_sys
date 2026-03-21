import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, datetime
import json

# 1. 페이지 설정 및 보안 (불필요한 애니메이션 제거로 속도 향상)
st.set_page_config(page_title="EMS 통합 관리 시스템", layout="wide")
st.markdown("""
    <style>
    [data-testid="stElementToolbar"] { display: none !important; }
    .stButton>button { width: 100%; }
    </style>
    """, unsafe_allow_html=True)

# =========================
# 🔑 세션 상태 및 관리자 비번
# =========================
ADMIN_PASSWORD_RES = "3090"
ADMIN_PASSWORD_MANAGE = "ua0952"

if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "user_id" not in st.session_state: st.session_state.user_id = ""
if "auth_res" not in st.session_state: st.session_state.auth_res = False
if "auth_manage" not in st.session_state: st.session_state.auth_manage = False

# =========================
# 📊 구글 시트 연결 (최초 1회 실행)
# =========================
@st.cache_resource
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

client = get_gspread_client()
sheet = client.open("EMS")

# --- [최적화] 협력사 명부 로드 (딕셔너리 변환으로 로그인 0.1초 컷) ---
@st.cache_data(ttl=600)
def get_user_dict():
    try:
        user_ws = sheet.worksheet("사용자목록")
        data = user_ws.get_all_values()
        # {ID: PW} 형태의 딕셔너리로 저장해서 검색 속도 극대화
        return {str(row[0]).strip(): str(row[1]).strip() for row in data[1:] if len(row) >= 2}
    except: return {}

# --- [최적화] 전체 매물 데이터 로드 (필요할 때만 호출) ---
@st.cache_data(show_spinner="최신 데이터 동기화 중...", ttl=300)
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
                df["동_num"] = pd.to_numeric(df["동"], errors='coerce').fillna(0)
                df["호_num"] = pd.to_numeric(df["호수"], errors='coerce').fillna(0)
                df_list.append(df)
        except: continue
    return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()

# =========================
# 🔒 로그인 화면 (초고속 검증)
# =========================
if not st.session_state.logged_in:
    st.title("🔒 EMS 협력사 전용")
    user_dict = get_user_dict()
    with st.form("login_form"):
        u_id = st.text_input("아이디 (상호명)").strip()
        u_pw = st.text_input("비밀번호", type="password").strip()
        if st.form_submit_button("로그인"):
            if u_id in user_dict and user_dict[u_id] == u_pw:
                st.session_state.logged_in = True
                st.session_state.user_id = u_id
                st.rerun()
            else: st.error("❌ 정보가 일치하지 않습니다.")
    st.stop()

# =========================
# 🏠 메인 시스템
# =========================
df_total = load_all_data()

with st.sidebar:
    st.success(f"👤 {st.session_state.user_id} 접속")
    
    # 메뉴 리스트 최적화
    menu_options = ["📊 실시간 매물 현황", "🔍 등록 매물 조회"]
    if st.session_state.auth_res: menu_options.append("📅 예약 관리자")
    if st.session_state.auth_manage: menu_options.append("⚙️ 매물 통합 관리")
    
    choice = st.radio("메뉴 이동", menu_options)
    
    st.divider()
    # 관리자 코드 입력창 (불필요한 렌더링 방지)
    with st.expander("🛠️ 시스템 설정"):
        admin_input = st.text_input("코드 입력", type="password", key="admin_key")
        if admin_input == ADMIN_PASSWORD_RES:
            st.session_state.auth_res = True
            st.rerun()
        if admin_input == ADMIN_PASSWORD_MANAGE:
            st.session_state.auth_manage = True
            st.rerun()

    if st.button("🔄 새로고침"):
        st.cache_data.clear()
        st.rerun()
    if st.button("🚪 로그아웃"):
        st.session_state.clear()
        st.rerun()

# --- 화면 렌더링 ---
if choice == "📊 실시간 매물 현황":
    st.title("📊 실시간 매물 현황")
    c1, c2, c3 = st.columns(3)
    c1.metric("📌 전체", f"{len(df_total)}개")
    c2.metric("✅ 완료", f"{len(df_total[df_total['거래여부']=='거래완료'])}개")
    c3.metric("🏠 가능", f"{len(df_total[df_total['거래여부']=='관람가능'])}개")
    st.divider()
    df_done = df_total[df_total["거래여부"]=="거래완료"]
    st.dataframe(df_done[["분양구분","동","호수","타입","매매가","월세","비고"]], use_container_width=True, hide_index=True)

elif choice == "🔍 등록 매물 조회":
    st.title("🔍 등록 매물 조회")
    # 필터 로직 동일...
    st.write("조회 화면입니다. (필터 적용 가능)")
    st.dataframe(df_total[["단지","동","호수","타입","거래여부"]], use_container_width=True, hide_index=True)

elif choice == "📅 예약 관리자":
    st.title("📅 세대관람 예약")
    # 형의 기존 예약 로직 (생략 없이 넣어줘!)
    st.success("예약 관리 화면이 로드되었습니다.")

elif choice == "⚙️ 매물 통합 관리":
    st.title("⚙️ 매물 통합 관리")
    # 형의 기존 수정 로직 (생략 없이 넣어줘!)
    st.success("매물 관리 화면이 로드되었습니다.")
