import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, date, timedelta, timezone
import json
import uuid
import time

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
# 🔑 데이터 연결
# =========================
@st.cache_resource(ttl=60)
def get_ems_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open("EMS")

sheet = get_ems_sheet()
TIME_SLOTS = ["10:00 ~ 10:45", "11:00 ~ 11:45", "13:00 ~ 13:45", "14:00 ~ 14:45", "15:00 ~ 15:45", "16:00 ~ 16:45", "17:00 ~ 17:45"]
COL_NAMES = ["예약날짜", "예약자", "중개업소", "관람세대수", "동호수", "타입", "예약시간", "비고", "ID"]

@st.cache_data(ttl=60)
def load_admin_data():
    sheets = ["1단지_매매","1단지_임대","2단지_매매","2단지_임대","3단지_매매","3단지_임대"]
    df_list = []
    for s in sheets:
        try:
            ws = sheet.worksheet(s); data = ws.get_all_values()
            if len(data) > 1:
                df = pd.DataFrame(data[1:], columns=["NO.","분양구분","동","호수","타입","매물구분","매매가","월세","거래여부", "비고"])
                df["단지"] = s.split("_")[0]; df["거래유형"] = s.split("_")[1]
                df_list.append(df)
        except: continue
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

# --- [작업 3: 마스터 모든 필드 수정/삭제] ---
elif choice == "✂️ 예약 강제 수정/삭제":
    st.title("✂️ 예약 정보 마스터 수정 (전체 필드)")
    col1, col2 = st.columns(2)
    d_date = col1.date_input("날짜 선택", date.today())
    d_dj = col2.selectbox("단지 선택", ["1단지_관람예약", "2단지_관람예약", "3단지_관람예약"])
    
    ws_mod = sheet.worksheet(d_dj); rows_mod = ws_mod.get_all_values()
    if len(rows_mod) > 1:
        df_mod = pd.DataFrame(rows_mod[1:], columns=rows_mod[0])
        day_mod = df_mod[df_mod["예약날짜"] == d_date.strftime("%Y-%m-%d")]
        
        if not day_mod.empty:
            opts = [f"[{r['예약시간']}] {r['예약자']} ({r['중개업소']}) - {r['동호수']}" for i, r in day_mod.iterrows()]
            sel_text = st.selectbox("수정할 항목을 선택하세요", opts)
            
            # 실제 행 번호 찾기
            row_idx = day_mod.index[opts.index(sel_text)] + 2
            curr_r = rows_mod[row_idx-1] # 기존 데이터 (A:1, B:2...)
            
            st.markdown("---")
            st.warning(f"⚠️ 현재 선택된 행 번호: {row_idx} (구글 시트 기준)")
            
            with st.form("master_edit_form"):
                mc1, mc2 = st.columns(2)
                m_date = mc1.date_input("📅 예약날짜", value=datetime.strptime(curr_r[0], "%Y-%m-%d"))
                m_time = mc2.selectbox("🕒 예약시간", TIME_SLOTS, index=TIME_SLOTS.index(curr_r[6]) if curr_r[6] in TIME_SLOTS else 0)
                
                mc3, mc4 = st.columns(2)
                m_name = mc3.text_input("👤 예약자 성함", value=curr_r[1])
                m_agency = mc4.text_input("🏢 중개업소", value=curr_r[2])
                
                mc5, mc6, mc7 = st.columns([1, 2, 1])
                m_count = mc5.text_input("🔢 세대수", value=curr_r[3])
                m_info = mc6.text_input("🏠 동호수 정보", value=curr_r[4])
                m_type = mc7.text_input("📋 타입", value=curr_r[5])
                
                m_memo = st.text_area("📝 비고", value=curr_r[7])
                
                c_edit, c_del = st.columns(2)
                if c_edit.form_submit_button("💾 마스터 권한으로 수정 저장", use_container_width=True):
                    updated_row = [
                        m_date.strftime("%Y-%m-%d"), m_name, m_agency, 
                        m_count, m_info, m_type, m_time, m_memo, curr_r[8]
                    ]
                    ws_mod.update(f'A{row_idx}:I{row_idx}', [updated_row])
                    st.success("✅ 모든 정보가 강제 수정되었습니다."); st.cache_data.clear(); time.sleep(1); st.rerun()
                
                if c_del.form_submit_button("🗑️ 이 예약 강제 삭제", use_container_width=True):
                    ws_mod.delete_rows(row_idx)
                    st.success("🗑️ 해당 예약이 시스템에서 완전히 삭제되었습니다."); st.cache_data.clear(); time.sleep(1); st.rerun()
        else:
            st.info("해당 날짜에 예약 내역이 없습니다.")
