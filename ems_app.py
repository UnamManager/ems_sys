import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, date, timedelta, timezone  # ← uuid를 여기서 제거
import json
import uuid  # ← uuid를 이렇게 따로 한 줄로 빼야 합니다
import smtplib
import time
from email.mime.text import MIMEText

# =========================
# 1. 관리자 전용 설정
# =========================
st.set_page_config(page_title="EMS 마스터 관리 시스템", layout="wide")
ADMIN_PASSWORD_MANAGE = "3214" 

if "admin_logged_in" not in st.session_state:
    st.title("⚙️ EMS 마스터 로그인")
    pw_in = st.text_input("관리자 전용 코드를 입력하세요", type="password")
    if st.button("관리자 인증"):
        if pw_in == ADMIN_PASSWORD_MANAGE:
            st.session_state.admin_logged_in = True
            st.rerun()
        else: st.error("❌ 코드가 올바르지 않습니다.")
    st.stop()

# =========================
# 🔑 데이터 연결 (사용자 버전과 동일한 시트 사용)
# =========================
@st.cache_resource(ttl=60) # 관리자는 실시간성이 중요하므로 짧게 설정
def get_ems_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open("EMS")

sheet = get_ems_sheet()
TIME_SLOTS = ["10:00 ~ 10:45", "11:00 ~ 11:45", "13:00 ~ 13:45", "14:00 ~ 14:45", "15:00 ~ 15:45", "16:00 ~ 16:45", "17:00 ~ 17:45"]
COL_NAMES = ["예약날짜", "예약자", "중개업소", "관람세대수", "동호수", "타입", "예약시간", "비고"]

@st.cache_data(ttl=60)
def load_admin_data():
    sheets = ["1단지_매매","1단지_임대","2단지_매매","2단지_임대","3단지_매매","3단지_임대"]
    df_list = []
    for s in sheets:
        ws = sheet.worksheet(s); data = ws.get_all_values()
        if len(data) > 1:
            df = pd.DataFrame(data[1:], columns=["NO.","분양구분","동","호수","타입","매물구분","매매가","월세","거래여부", "비고"])
            df["단지"] = s.split("_")[0]; df["거래유형"] = s.split("_")[1]
            df_list.append(df)
    return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()

df_total = load_admin_data()

# =========================
# 🏠 사이드바 및 메뉴
# =========================
st.sidebar.title("🛠️ 관리자 메뉴")
choice = st.sidebar.radio("작업 선택", ["🏠 거래상태 변경", "📅 통합 예약 조회", "✂️ 예약 강제 수정/삭제"])
if st.sidebar.button("🔄 데이터 강제 갱신"): st.cache_data.clear(); st.rerun()
if st.sidebar.button("🔒 로그아웃"): st.session_state.clear(); st.rerun()

# --- [작업 1: 상태 변경] ---
if choice == "🏠 거래상태 변경":
    st.title("📍 매물 상태 업데이트")
    c1, c2, c3 = st.columns(3)
    a_dj = c1.selectbox("단지", ["1단지", "2단지", "3단지"])
    a_dong = c2.text_input("동")
    a_ho = c3.text_input("호수")
    if a_dong and a_ho:
        target = df_total[(df_total["단지"] == a_dj) & (df_total["동"] == a_dong) & (df_total["호수"] == a_ho)]
        if not target.empty:
            curr = target.iloc[0]
            with st.form("adm_status"):
                new_s = st.selectbox("거래 상태", ["관람가능", "거래완료"], index=0 if curr["거래여부"]=="관람가능" else 1)
                new_n = st.text_input("비고", value=curr["비고"])
                if st.form_submit_button("저장"):
                    ws = sheet.worksheet(f"{a_dj}_{curr['거래유형']}")
                    rows = ws.get_all_values()
                    idx = next((i+1 for i, r in enumerate(rows) if len(r)>3 and r[2]==a_dong and r[3]==a_ho), -1)
                    if idx != -1:
                        ws.update(f'I{idx}:J{idx}', [[new_s, new_n]])
                        st.success("✅ 변경 완료!"); st.cache_data.clear(); time.sleep(1); st.rerun()
        else: st.error("매물을 찾을 수 없습니다.")

# --- [작업 2: 통합 조회] ---
elif choice == "📅 통합 예약 조회":
    st.title("📅 전체 예약 현황 (마스터)")
    adm_date = st.date_input("조회 날짜", date.today())
    formatted_date = adm_date.strftime("%Y-%m-%d")
    
    tabs = st.tabs(["1단지", "2단지", "3단지", "📊 전체보기"])
    for i, dj in enumerate(["1단지", "2단지", "3단지"]):
        with tabs[i]:
            ws = sheet.worksheet(f"{dj}_관람예약"); data = ws.get_all_values()
            df = pd.DataFrame(data[1:], columns=data[0]) if len(data)>1 else pd.DataFrame(columns=COL_NAMES)
            df = df[df["예약날짜"] == formatted_date]
            st.write(f"🏠 {dj} 예약: {len(df)}건")
            st.dataframe(df, use_container_width=True, hide_index=True)
    
    with tabs[3]:
        all_res = []
        for dj in ["1단지", "2단지", "3단지"]:
            ws = sheet.worksheet(f"{dj}_관람예약"); data = ws.get_all_values()
            if len(data)>1:
                df = pd.DataFrame(data[1:], columns=data[0])
                df = df[df["예약날짜"] == formatted_date]; df["단지"] = dj
                all_res.append(df)
        if all_res: st.dataframe(pd.concat(all_res), use_container_width=True, hide_index=True)

# --- [작업 3: 마스터 수정/삭제] ---
elif choice == "✂️ 예약 강제 수정/삭제":
    st.title("✂️ 예약 정보 마스터 수정")
    col1, col2 = st.columns(2)
    d_date = col1.date_input("날짜 선택", date.today())
    d_dj = col2.selectbox("단지 선택", ["1단지_관람예약", "2단지_관람예약", "3단지_관람예약"])
    
    ws_mod = sheet.worksheet(d_dj); rows_mod = ws_mod.get_all_values()
    if len(rows_mod) > 1:
        df_mod = pd.DataFrame(rows_mod[1:], columns=rows_mod[0])
        day_mod = df_mod[df_mod["예약날짜"] == d_date.strftime("%Y-%m-%d")]
        if not day_mod.empty:
            opts = [f"[{r['예약시간']}] {r['예약자']} ({r['중개업소']})" for i, r in day_mod.iterrows()]
            sel_text = st.selectbox("수정할 항목", opts)
            row_idx = day_mod.index[opts.index(sel_text)] + 2
            curr_r = rows_mod[row_idx-1]
            
            st.divider()
            m_time = st.selectbox("🕒 시간 변경", TIME_SLOTS, index=TIME_SLOTS.index(curr_r[6]) if curr_r[6] in TIME_SLOTS else 0)
            m_memo = st.text_input("비고 수정", value=curr_r[7])
            
            if st.button("💾 마스터 권한으로 수정 저장", type="primary"):
                ws_mod.update(f'G{row_idx}', [[m_time]])
                ws_mod.update(f'H{row_idx}', [[m_memo]])
                st.success("✅ 강제 수정 완료!"); st.cache_data.clear(); time.sleep(1); st.rerun()
            
            if st.button("🗑️ 예약 강제 삭제"):
                ws_mod.delete_rows(row_idx)
                st.success("🗑️ 삭제 완료!"); st.cache_data.clear(); time.sleep(1); st.rerun()
        else: st.info("예약이 없습니다.")
