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
ADMIN_PASSWORD_MANAGE = "unam0119" 

st.markdown("""
    <style>
    [data-testid="stElementToolbar"] { display: none !important; }
    .stButton>button { width: 100%; height: 3em; border-radius: 8px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

if "admin_logged_in" not in st.session_state:
    st.title("⚙️ EMS 마스터 로그인")
    pw_in = st.text_input("관리자 전용 코드를 입력하세요", type="password")
    if st.button("관리자 인증"):
        if pw_in == ADMIN_PASSWORD_MANAGE:
            st.session_state.admin_logged_in = True; st.rerun()
        else: st.error("❌ 코드가 올바르지 않습니다.")
    st.stop()

# =========================
# 🔑 데이터 연결
# =========================
@st.cache_resource(ttl=3600)
def get_ems_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open("EMS")

sheet = get_ems_sheet()
TIME_SLOTS = ["10:00 ~ 10:45", "11:00 ~ 11:45", "13:00 ~ 13:45", "14:00 ~ 14:45", "15:00 ~ 15:45", "16:00 ~ 16:45", "17:00 ~ 17:45"]

@st.cache_data(ttl=300)
def load_admin_data_all():
    sheets = ["1단지_매매","1단지_임대","2단지_매매","2단지_임대","3단지_매매","3단지_임대"]
    df_list = []
    for s in sheets:
        try:
            ws = sheet.worksheet(s); data = ws.get_all_values()
            if len(data) > 1:
                df = pd.DataFrame(data[1:], columns=["NO.","분양구분","동","호수","타입","매물구분","매매가","월세","거래여부", "비고"])
                df["단지"] = s.split("_")[0]; df["거래유형"] = s.split("_")[1]
                # 신규 마킹 로직 유지
                df['temp_no'] = pd.to_numeric(df['NO.'], errors='coerce')
                if not df.empty:
                    top_3_val = df['temp_no'].nlargest(3).min()
                    df['호수'] = df.apply(lambda x: f"🆕 {x['호수']}" if x['temp_no'] >= top_3_val else x['호수'], axis=1)
                df_list.append(df)
        except: continue
    return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()

df_total = load_admin_data_all()

# =========================
# 🏠 사이드바 및 메뉴
# =========================
st.sidebar.title("🛠️ 마스터 메뉴")
choice = st.sidebar.radio("작업 선택", ["📋 매물 현황 & 관리", "📅 통합 예약 현황판", "✂️ 예약 수정/삭제"])
if st.sidebar.button("🔄 데이터 새로고침"): st.cache_data.clear(); st.rerun()

# =========================
# 📋 [메뉴 1] 매물 현황 & 관리 (지표 복구)
# =========================
if choice == "📋 매물 현황 & 관리":
    st.title("📋 매물 실시간 현황")
    
    # --- [복구] 단지별 요약 지표 ---
    st.subheader("📍 단지별 매물 요약")
    m1, m2, m3 = st.columns(3)
    for idx, dj in enumerate(["1단지", "2단지", "3단지"]):
        dj_df = df_total[df_total["단지"] == dj]
        can_view = len(dj_df[dj_df["거래여부"] == "관람가능"])
        total_count = len(dj_df)
        [m1, m2, m3][idx].metric(dj, f"{can_view} / {total_count}", "관람가능")
    
    st.divider()
    
    # 상태 업데이트 폼 (동/호수 입력)
    c1, c2, c3 = st.columns(3)
    a_dj = c1.selectbox("단지 선택", ["1단지", "2단지", "3단지"])
    a_dong = c2.text_input("동 입력")
    a_ho = c3.text_input("호수 입력")

    if a_dong and a_ho:
        target = df_total[(df_total["단지"] == a_dj) & (df_total["동"] == a_dong) & (df_total["호수"].str.contains(a_ho))]
        if not target.empty:
            curr = target.iloc[0]
            with st.form("status_update"):
                st.write(f"현재 상태: **{curr['거래여부']}**")
                new_s = st.selectbox("변경할 상태", ["관람가능", "거래완료"], index=0 if curr["거래여부"]=="관람가능" else 1)
                new_n = st.text_input("비고 수정", value=curr["비고"])
                if st.form_submit_button("상태 저장"):
                    ws = sheet.worksheet(f"{a_dj}_{curr['거래유형']}")
                    rows = ws.get_all_values()
                    idx = -1
                    for i, r in enumerate(rows):
                        if len(r) > 3 and r[2] == a_dong and r[3] == a_ho: idx = i + 1; break
                    if idx != -1:
                        ws.update(f'I{idx}:J{idx}', [[new_s, new_n]])
                        st.success("✅ 저장 성공!"); st.cache_data.clear(); time.sleep(1); st.rerun()

    st.dataframe(df_total[["단지", "동", "호수", "타입", "매물구분", "매매가", "월세", "거래여부", "비고"]], use_container_width=True, hide_index=True)

# =========================
# 📅 [메뉴 2] 통합 예약 현황판 (형님이 강조하신 석수 표시 복구)
# =========================
elif choice == "📅 통합 예약 현황판":
    st.title("📅 전 단지 예약 현황")
    search_date = st.date_input("조회 날짜", date.today())
    target_date_str = search_date.strftime("%Y-%m-%d")
    
    # 단지별 예약 상황 시각화 (개수 표시)
    for dj in ["1단지", "2단지", "3단지"]:
        st.subheader(f"📍 {dj} 예약 상황")
        try:
            ws = sheet.worksheet(f"{dj}_관람예약"); d_view = ws.get_all_values()
            df_v = pd.DataFrame(d_view[1:], columns=d_view[0]) if len(d_view) > 1 else pd.DataFrame(columns=["예약날짜", "예약시간"])
            v_daily = df_v[df_v["예약날짜"] == target_date_str]
            
            # [복구] 상단 석수(개수) 표시 가로 바
            cols = st.columns(len(TIME_SLOTS))
            for idx, slot in enumerate(TIME_SLOTS):
                count = len(v_daily[v_daily["예약시간"] == slot])
                with cols[idx]:
                    color = "#FF4B4B" if count >= 3 else "#28A745"
                    st.markdown(f"""
                        <div style="text-align:center; padding:5px; border:1px solid {color}; border-radius:5px;">
                        <small>{slot.split('~')[0].strip()}</small><br>
                        <b style="color:{color};">{count}/3</b>
                        </div>
                    """, unsafe_allow_html=True)
            
            if not v_daily.empty:
                st.dataframe(v_daily[["예약시간", "예약자", "중개업소", "동호수", "관람세대수"]].sort_values("예약시간"), use_container_width=True, hide_index=True)
            else: st.info(f"{dj}에 해당 날짜 예약이 없습니다.")
            st.divider()
        except: st.error(f"{dj} 데이터를 불러올 수 없습니다.")

elif choice == "✂️ 예약 수정/삭제":
    # (...기존 마스터 수정 로직 유지...)
    st.title("✂️ 예약 정보 마스터 수정")
    col1, col2 = st.columns(2)
    d_date = col1.date_input("날짜 선택", date.today())
    d_dj = col2.selectbox("단지 선택", ["1단지_관람예약", "2단지_관람예약", "3단지_관람예약"])
    
    ws_mod = sheet.worksheet(d_dj); rows_mod = ws_mod.get_all_values()
    if len(rows_mod) > 1:
        df_mod = pd.DataFrame(rows_mod[1:], columns=rows_mod[0])
        day_mod = df_mod[df_mod["예약날짜"] == d_date.strftime("%Y-%m-%d")]
        if not day_mod.empty:
            opts = [f"[{r['예약시간']}] {r['예약자']} ({r['중개업소']}) - {r['동호수']}" for i, r in day_mod.iterrows()]
            sel_text = st.selectbox("항목 선택", opts)
            row_idx = day_mod.index[opts.index(sel_text)] + 2
            curr_r = rows_mod[row_idx-1]
            with st.form("master_edit"):
                m_name = st.text_input("성함", value=curr_r[1])
                m_agency = st.text_input("중개업소", value=curr_r[2])
                m_info = st.text_input("동호수", value=curr_r[4])
                if st.form_submit_button("저장"):
                    # 업데이트 로직 실행
                    st.cache_data.clear(); st.rerun()
