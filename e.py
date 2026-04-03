import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, date
import json
import uuid
import smtplib
import time
from email.mime.text import MIMEText

# =========================
# 1. 페이지 설정 및 디자인
# =========================
st.set_page_config(page_title="EMS 통합 관리 시스템", layout="wide")
st.markdown("""
    <style>
    [data-testid="stElementToolbar"] { display: none !important; }
    .stButton>button { width: 100%; height: 3em; border-radius: 8px; font-weight: bold; }
    .time-card { border-radius: 8px; padding: 5px; text-align: center; margin-bottom: 5px; }
    .time-card p { margin: 0; font-size: 0.7rem; color: #666; }
    .time-card strong { font-size: 0.85rem; }
    </style>
    """, unsafe_allow_html=True)

# =========================
# 🔑 세션 및 환경 설정
# =========================
if "session_key" not in st.session_state: st.session_state["session_key"] = str(uuid.uuid4())
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
if "user_id" not in st.session_state: st.session_state["user_id"] = ""
if "auth_manage" not in st.session_state: st.session_state["auth_manage"] = False

ADMIN_PASSWORD_MANAGE = "3214"
TIME_SLOTS = ["10:00 ~ 10:45", "11:00 ~ 11:45", "13:00 ~ 13:45", "14:00 ~ 14:45", "15:00 ~ 15:45", "16:00 ~ 16:45", "17:00 ~ 17:45"]
COL_NAMES = ["예약날짜", "예약자", "중개업소", "관람세대수", "동호수", "타입", "예약시간", "비고", "등록ID"]

# =========================
# 📩 이메일 알림 및 구글 API 연결
# =========================
def send_email_notification(content):
    try:
        sender = st.secrets["EMAIL_ADDRESS"]
        password = st.secrets["EMAIL_PASSWORD"]
        receiver = st.secrets["ADMIN_NOTIFY_EMAIL"]
        msg = MIMEText(content)
        msg["Subject"] = "📢 새로운 관람 예약 등록"
        msg["From"] = sender
        msg["To"] = receiver
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, receiver, msg.as_string())
        server.quit()
    except: 
        pass 

@st.cache_resource(ttl=3600)
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

@st.cache_resource(ttl=3600)
def get_ems_sheet():
    client = get_gspread_client()
    return client.open("EMS")

sheet = get_ems_sheet()

# --- [데이터 통합 로드] ---
@st.cache_data(ttl=600)
def load_full_data():
    try:
        sheets_to_load = ["1단지_매매","1단지_임대","2단지_매매","2단지_임대","3단지_매매","3단지_임대"]
        df_list = []
        
        for s in sheets_to_load:
            try:
                ws = sheet.worksheet(s)
                data = ws.get_all_values()
                if len(data) > 1:
                    df = pd.DataFrame(data[1:], columns=["NO.","분양구분","동","호수","타입","매물구분","매매가","월세","거래여부", "비고"])
                    df["단지"] = s.split("_")[0]  # "1단지", "2단지" 등
                    df["거래유형"] = s.split("_")[1] # "매매", "임대"
                    
                    for col in ["매매가", "월세"]:
                        df[f"{col}_num"] = pd.to_numeric(df[col].str.replace(',', ''), errors='coerce').fillna(0)
                    df_list.append(df)
            except Exception as e:
                continue
        
        # 사용자 목록 로드
        user_ws = sheet.worksheet("사용자목록")
        u_data = user_ws.get_all_values()
        user_dict = {str(row[0]).strip(): str(row[1]).strip() for row in u_data[1:] if len(row) >= 2}
        
        if df_list:
            final_df = pd.concat(df_list, ignore_index=True)
            return final_df, user_dict
        else:
            empty_df = pd.DataFrame(columns=["NO.","분양구분","동","호수","타입","매물구분","매매가","월세","거래여부", "비고", "단지", "거래유형"])
            return empty_df, user_dict
            
    except Exception as e:
        st.error(f"전체 데이터 로드 중 치명적 오류: {e}")
        return pd.DataFrame(), {}

df_total, user_dict = load_full_data()

# =========================
# 🎨 스타일 함수
# =========================
def apply_style(df):
    try:
        return df.style.map(lambda x: "background-color: #d4edda" if x == "관람가능" else "background-color: #f8d7da" if x == "거래완료" else "", subset=["거래여부"])
    except:
        return df.style.applymap(lambda x: "background-color: #d4edda" if x == "관람가능" else "background-color: #f8d7da" if x == "거래완료" else "", subset=["거래여부"])

# =========================
# 🔒 로그인 시스템
# =========================
if not st.session_state.logged_in:
    st.title("🔒 EMS 통합 관리 로그인")
    with st.form("login_form"):
        u_id = st.text_input("아이디(ID)").strip()
        u_pw = st.text_input("비밀번호(PW)", type="password").strip()
        if st.form_submit_button("시스템 접속"):
            if u_id in user_dict and user_dict[u_id] == u_pw:
                st.session_state.logged_in = True
                st.session_state.user_id = u_id
                st.rerun()
            else:
                st.error("❌ 아이디 또는 비밀번호가 일치하지 않습니다.")
    st.stop()

# =========================
# 🏠 사이드바 및 메뉴
# =========================
ADMIN_MENU_NAME = "⚙️ 관리자 모드"
menu_options = ["📊 실시간 현황", "🔍 등록 매물 조회", "📅 세대관람 예약"]
if st.session_state.auth_manage:
    menu_options.append(ADMIN_MENU_NAME)

with st.sidebar:
    st.success(f"👤 {st.session_state.user_id} 접속 중")
    choice = st.radio("메뉴 이동", menu_options)
    st.divider()
    if not st.session_state.auth_manage:
        with st.expander("🛠️ 관리자 인증"):
            pw_in = st.text_input("관리자 코드 입력", type="password")
            if pw_in == ADMIN_PASSWORD_MANAGE: 
                st.session_state.auth_manage = True
                st.rerun()
    
    if st.button("🔄 새로고침"): st.cache_data.clear(); st.rerun()
    if st.button("🔒 로그아웃"):
        st.session_state.clear(); st.rerun()

# =========================
