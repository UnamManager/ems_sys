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
# 1. 페이지 설정 및 스타일
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
# 🔑 세션 및 설정값
# =========================
if "session_key" not in st.session_state: 
    st.session_state["session_key"] = str(uuid.uuid4())
if "logged_in" not in st.session_state: 
    st.session_state["logged_in"] = False
if "user_id" not in st.session_state: 
    st.session_state["user_id"] = ""
if "auth_manage" not in st.session_state: 
    st.session_state["auth_manage"] = False

ADMIN_PASSWORD_MANAGE = "ua0952"
TIME_SLOTS = ["10:00 ~ 10:45", "11:00 ~ 11:45", "13:00 ~ 13:45", "14:00 ~ 14:45", "15:00 ~ 15:45", "16:00 ~ 16:45", "17:00 ~ 17:45"]
NIGHT_SLOTS = ["16:00 ~ 16:45", "17:00 ~ 17:45"]
COL_NAMES = ["예약날짜", "예약자", "중개업소", "관람세대수", "동", "호수", "타입", "예약시간", "비고"]

# =========================
# 📩 이메일 및 구글 시트 연결
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

@st.cache_resource
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

@st.cache_resource
def get_ems_sheet():
    client = get_gspread_client()
    return client.open("EMS")

sheet = get_ems_sheet()

# =========================
# 🔄 데이터 동기화 및 로드 함수
# =========================
def sync_session(user_id, my_key):
    if not user_id: return True
    try:
        ws = sheet.worksheet("접속현황")
        data = ws.get_all_values()
        for i, row in enumerate(data):
            if row[0] == user_id:
                if row[1] != "" and row[1] != my_key: 
                    return False
                ws.update(range_name=f'C{i+1}', values=[[datetime.now().strftime("%Y-%m-%d %H:%M:%S")]])
                return True
        return True
    except:
        return True

@st.cache_data(ttl=600) 
def load_full_data():
    try:
        sheets = ["1단지_매매","1단지_임대","2단지_매매","2단지_임대","3단지_매매","3단지_임대"]
        df_list = []
        for s in sheets:
            try:
                ws = sheet.worksheet(s)
                data = ws.get_all_values()
                if len(data) > 1:
                    df = pd.DataFrame(data[1:], columns=["NO.","분양구분","동","호수","타입","매물구분","매매가","월세","거래여부", "비고"])
                    df["단지"] = s.split("_")[0]
                    df["거래유형"] = s.split("_")[1]
                    for col in ["매매가", "월세"]:
                        df[f"{col}_num"] = pd.to_numeric(df[col].str.replace(',', ''), errors='coerce').fillna(0)
                    df_list.append(df)
            except:
                continue
        user_ws = sheet.worksheet("사용자목록")
        u_data = user_ws.get_all_values()
        user_dict = {str(row[0]).strip(): str(row[1]).strip() for row in u_data[1:] if len(row) >= 2}
        final_df = pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()
        return final_df, user_dict
    except:
        return pd.DataFrame(), {}

df_total, user_dict = load_full_data()

# =========================
# 🔒 로그인 처리 로직
# =========================
if not st.session_state.logged_in:
    st.title("🔒 EMS 로그인")
    with st.form("login"):
        u_id = st.text_input("ID(아이디)").strip()
        u_pw = st.text_input("PW(비밀번호)", type="password").strip()
        if st.form_submit_button("로그인"):
            if u_id in user_dict and user_dict[u_id] == u_pw:
                ws_status = sheet.worksheet("접속현황")
                all_status = ws_status.get_all_values()
                target_row = -1
                current_db_key = ""
                for i, r in enumerate(all_status):
                    if r[0] == u_id: 
                        target_row = i + 1
                        current_db_key = r[1].strip()
                        break
                
                if current_db_key != "" and current_db_key != st.session_state.session_key:
                    st.error("🔒현재 다른 기기에서 접속 중인 계정입니다. 보안 정책상 중복 접속은 제한됩니다.")
                    st.session_state.pending_user = u_id
                else:
                    if target_row != -1:
                        ws_status.update(range_name=f'B{target_row}:C{target_row}', values=[[st.session_state.session_key, datetime.now().strftime("%H:%M:%S")]])
                    else:
                        ws_status.append_row([u_id, st.session_state.session_key, datetime.now().strftime("%H:%M:%S")])
                    st.session_state.logged_in = True
                    st.session_state.user_id = u_id
                    st.rerun()
            else:
                st.error("❌ 로그인 정보를 확인해주세요.[문의 : 062-511-9336]")
    
    if "pending_user" in st.session_state:
        if st.button(f"🔑 '{st.session_state.pending_user}' 님의 기존 접속을 종료하고 시작합니다."):
            ws_status = sheet.worksheet("접속현황")
            all_status = ws_status.get_all_values()
            for i, r in enumerate(all_status):
                if r[0] == st.session_state.pending_user:
                    ws_status.update(range_name=f'B{i+1}:C{i+1}', values=[[st.session_state.session_key, datetime.now().strftime("%H:%M:%S")]])
                    break
            st.session_state.logged_in = True
            st.session_state.user_id = st.session_state.pending_user
            del st.session_state.pending_user
            st.rerun()
    st.stop()

# 세션 감시 실행
if not sync_session(st.session_state.user_id, st.session_state.session_key):
    st.error("🚨 다른 사용자의 접속이 감지되어 종료되었습니다.")
    st.session_state.clear()
    st.stop()

# =========================
# 🏠 사이드바 메뉴
# =========================
menu_options = ["📊 실시간 현황", "🔍 등록 매물 조회", "📅 세대관람 예약"]
if st.session_state.auth_manage: 
    menu_options.append("⚙️관리자 모드")

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
    if st.button("🔄 새로고침"):
        st.cache_data.clear()
        st.rerun()
    if st.button("🔒 로그아웃"):
        try:
            ws_status = sheet.worksheet("접속현황")
            all_status = ws_status.get_all_values()
            for i, r in enumerate(all_status):
                if r[0] == st.session_state.user_id:
                    ws_status.update(range_name=f'B{i+1}:C{i+1}', values=[["", ""]])
                    break
        except: pass
        st.session_state.clear()
        st.rerun()

def apply_style(df):
    return df.style.map(lambda x: "background-color: #d4edda" if x == "관람가능" else "background-color: #f8d7da" if x == "거래완료" else "", subset=["거래여부"])

# =========================
# 📊 [페이지 1] 실시간 현황
# =========================
if choice == "📊 실시간 현황":
    st.title("📊 실시간 현황")
    c1, c2, c3 = st.columns(3)
    c1.metric("📌 전체", f"{len(df_total)}개")
    c2.metric("✅ 거래완료", f"{len(df_total[df_total['거래여부']=='거래완료'])}개")
    c3.metric("🏠 관람가능", f"{len(df_total[df_total['거래여부']=='관람가능'])}개")
    st.divider()
    df_done = df_total[df_total["거래여부"] == "거래완료"].copy()
    for col in ["매매가", "월세", "비고"]:
        if col in df_done.columns: df_done[col] = "🔒 거래완료"
    st.dataframe(apply_style(df_done[["분양구분", "동", "호수", "타입", "매물구분", "매매가", "월세", "거래여부", "비고"]]), use_container_width=True, hide_index=True)

# =========================
# 🔍 [페이지 2] 등록 매물 조회
# =========================
elif choice == "🔍 등록 매물 조회":
    st.title("🔍 등록 매물 조회")
    f1, f2, f3, f4 = st.columns(4)
    s_danji = f1.multiselect("단지", df_total["단지"].unique())
    s_bunyang = f2.multiselect("분양구분", df_total["분양구분"].unique())
    s_gubun = f3.multiselect("매물구분", df_total["매물구분"].unique())
    s_type = f4.multiselect("타입", sorted(df_total["타입"].unique()))
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
    
    mask = df_v["거래여부"] == "거래완료"
    for col in ["매매가", "월세", "비고"]:
        if col in df_v.columns: df_v.loc[mask, col] = "🔒 거래완료"
    st.dataframe(apply_style(df_v[["분양구분", "동", "호수", "타입", "매물구분", "매매가", "월세", "거래여부", "비고"]]), use_container_width=True, hide_index=True)

# =========================
# 📅 [페이지 3] 세대관람 예약
# =========================
elif choice == "📅 세대관람 예약":
    st.title("📋 세대관람 예약 시스템")
    tab1, tab2 = st.tabs(["📝 예약 등록", "📊 단지별 예약 현황"])
    
    with tab1:
        res_dj = st.selectbox("관람 단지 선택", ["1단지", "2단지", "3단지"])
        r_date_val = st.date_input("방문 날짜 선택", date.today())
        t_val = st.selectbox("관람 시간 선택", TIME_SLOTS)
        target_sheet_name = "야간_관람예약" if t_val in NIGHT_SLOTS else f"{res_dj}_관람예약"
        
        try:
            target_ws = sheet.worksheet(target_sheet_name)
            all_res = target_ws.get_all_values()
            if len(all_res) > 1:
                daily_df = pd.DataFrame(all_res[1:], columns=all_res[0])
                mask = (daily_df["예약날짜"] == r_date_val.strftime("%Y-%m-%d")) & (daily_df["예약시간"] == t_val)
                current_res_count = len(daily_df[mask])
            else: 
                daily_df = pd.DataFrame(columns=COL_NAMES)
                current_res_count = 0
            can_reserve = current_res_count < 3
        except:
            st.error(f"⚠️ '{target_sheet_name}' 시트 로드 실패."); st.stop()

        if not can_reserve:
            st.error(f"🚫 해당 시간대({t_val})는 예약이 마감되었습니다. (3/3)")
        else:
            st.info(f"✅ 현재 {3 - current_res_count}자리 예약 가능합니다. (현재 {current_res_count}/3)")
            st.progress(current_res_count / 3)

        st.divider()
        f_unit = df_total[df_total["단지"] == res_dj]
        r_count = st.selectbox("관람 세대수", [1, 2])
        r_items = []
        for i in range(r_count):
            with st.container(border=True):
                col1, col2 = st.columns(2)
                u_dongs = sorted(f_unit["동"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
                d_sel = col1.selectbox(f"동 ({i+1})", u_dongs, key=f"d_r_{i}")
                u_hos = sorted(f_unit[f_unit["동"]==d_sel]["호수"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
                h_sel = col2.selectbox(f"호수 ({i+1})", u_hos, key=f"h_r_{i}")
                match = f_unit[(f_unit["동"]==d_sel) & (f_unit["호수"]==h_sel)]
                if not match.empty: 
                    r_items.append({"동":d_sel, "호수":h_sel, "타입":match.iloc[0]['타입']})

        with st.form("reserve_form"):
            c1, c2 = st.columns(2)
            r_name = c1.text_input("(📝필수) 예약자 성함[실명]")
            r_agency = c2.text_input("(📝필수) 중개업소 명칭")
            memo_input = st.text_area("(선택) 비고 [방문 인원 수 또는 특이사항]")
            col_btn, col_tel = st.columns([1, 1]) 
            with col_btn:
                with st.container(border=True):
                    st.caption("⚠️확정 시 직접 취소가 불가능합니다.")
                    submit_btn = st.form_submit_button("📅 예약 최종 확정", disabled=not can_reserve, use_container_width=True)
            with col_tel:
                with st.container(border=True):
                    tel_num = "062-511-9336"
                    st.link_button("☎️ 대표번호 문의연결", f"tel:{tel_num}", use_container_width=True)
            
            if submit_btn:
                if not r_name or not r_agency:
                    st.error("성함과 업소명을 모두 입력해주세요.")
                elif can_reserve:
                    user_check_mask = (daily_df["예약날짜"] == r_date_val.strftime("%Y-%m-%d")) & (daily_df["예약시간"] == t_val)
                    already_reserved = daily_df[user_check_mask & (daily_df["중개업소"] == r_agency)]
                    if not already_reserved.empty:
                        st.error(f"🚫 '{r_agency}' 명의로 해당 시간대 중복 예약은 불가능합니다.")
                    else:
                        combined_info = " / ".join([f"{it['동']}동 {it['호수']}호" for it in r_items])
                        types_str = ", ".join([s["타입"] for s in r_items])
                        final_memo = f"[{st.session_state.user_id}] {memo_input}"
                        new_row = [r_date_val.strftime("%Y-%m-%d"), r_name, r_agency, f"{len(r_items)}세대", combined_info, "", types_str, t_val, final_
