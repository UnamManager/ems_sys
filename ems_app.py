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

# CSS: 신규 매물 강조 스타일 추가
st.markdown("""
    <style>
    .new-row { background-color: #fff5f5 !important; color: #FF4B4B !important; font-weight: bold !important; }
    .stDataFrame [data-testid="stTable"] td { white-space: nowrap; }
    </style>
    """, unsafe_allow_html=True)

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
# 🔑 데이터 연결 및 최적화 로직 (API 에러 방지)
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

# [핵심] 모든 매물 데이터를 한 번에 가져와서 캐싱 (API 호출 절약)
@st.cache_data(ttl=300)
def load_admin_data_all():
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
                
                # --- 신규 매물 마킹 (단지별/유형별 최신 3개) ---
                df['temp_no'] = pd.to_numeric(df['NO.'], errors='coerce')
                if not df.empty:
                    top_3_val = df['temp_no'].nlargest(3).min()
                    df['신규여부'] = df['temp_no'] >= top_3_val
                    df['호수'] = df.apply(lambda x: f"★[NEW] {x['호수']}" if x['신규여부'] else x['호수'], axis=1)
                df_list.append(df)
        except Exception as e:
            continue
    
    return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()

df_total = load_admin_data_all()

# 스타일링 함수 (신규 매물은 빨간색 배경)
def apply_admin_style(df):
    def style_row(row):
        if "★[NEW]" in str(row['호수']):
            return ['background-color: #fff5f5; color: #FF4B4B; font-weight: bold'] * len(row)
        elif row['거래여부'] == '거래완료':
            return ['background-color: #f8d7da; color: #721c24'] * len(row)
        return [''] * len(row)
    return df.style.apply(style_row, axis=1)

# =========================
# 🏠 사이드바 메뉴
# =========================
st.sidebar.title("🛠️ 마스터 관리 메뉴")
choice = st.sidebar.radio("작업 선택", ["🏠 통합 대시보드", "📅 통합 예약 조회", "✂️ 예약 수정/삭제"])
if st.sidebar.button("🔄 데이터 강제 새로고침"): st.cache_data.clear(); st.rerun()

# =========================
# 🏠 [메뉴 1] 통합 대시보드
# =========================
if choice == "🏠 통합 대시보드":
    st.title("🏠 매물 통합 대시보드")
    
    # 1. 신규 매물 집중 관리 섹션
    st.subheader("🔥 단지별 신규 등록 매물 (최신 3개씩)")
    new_items = df_total[df_total['신규여부'] == True].sort_values(['단지', '거래유형'])
    if not new_items.empty:
        cols = st.columns(3)
        for idx, (_, row) in enumerate(new_items.iterrows()):
            with cols[idx % 3]:
                st.info(f"**{row['단지']} {row['거래유형']}**\n\n{row['동']}동 {row['호수'].replace('★[NEW] ', '')}호 ({row['타입']})")
    
    st.divider()

    # 2. 거래 상태 변경 로직
    st.subheader("📍 매물 상태 실시간 업데이트")
    c1, c2, c3 = st.columns(3)
    a_dj = c1.selectbox("단지 선택", ["1단지", "2단지", "3단지"])
    a_dong = c2.text_input("동 입력 (예: 101)")
    a_ho = c3.text_input("호수 입력 (예: 501)")

    if a_dong and a_ho:
        # 검색 시 ★[NEW] 마크가 있을 수 있으므로 포함해서 검색
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
                    # ★[NEW] 마크를 떼고 원본 호수와 동이 일치하는 행 찾기
                    idx = -1
                    for i, r in enumerate(rows):
                        if len(r) > 3 and r[2] == a_dong and r[3] == a_ho:
                            idx = i + 1; break
                    if idx != -1:
                        ws.update(f'I{idx}:J{idx}', [[new_s, new_n]])
                        st.success("✅ 업데이트 성공!"); st.cache_data.clear(); time.sleep(1); st.rerun()
        else: st.warning("해당 매물을 찾을 수 없습니다.")

# =========================
# 📅 [메뉴 2] 통합 예약 조회 (에러 방지용 루프 최적화)
# =========================
elif choice == "📅 통합 예약 조회":
    st.title("📅 전 단지 예약 현황")
    search_date = st.date_input("조회 날짜 선택", date.today())
    target_date_str = search_date.strftime("%Y-%m-%d")
    
    all_res = []
    # 루프를 돌 때마다 캐시를 확인하여 API 호출 최소화
    for dj in ["1단지", "2단지", "3단지"]:
        try:
            ws = sheet.worksheet(f"{dj}_관람예약")
            data = ws.get_all_values()
            if len(data) > 1:
                df = pd.DataFrame(data[1:], columns=data[0])
                df = df[df["예약날짜"] == target_date_str]
                df["단지"] = dj
                all_res.append(df)
        except: continue
    
    if all_res:
        full_res_df = pd.concat(all_res, ignore_index=True)
        st.dataframe(full_res_df[["단지", "예약시간", "예약자", "중개업소", "동호수", "관람세대수"]].sort_values("예약시간"), use_container_width=True, hide_index=True)
    else:
        st.info("해당 날짜에 예약이 없습니다.")

# --- [작업 3: 마스터 모든 필드 수정/삭제 (기존 유지)] ---
elif choice == "✂️ 예약 수정/삭제":
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
            sel_text = st.selectbox("수정할 항목을 선택하세요", opts)
            
            row_idx = day_mod.index[opts.index(sel_text)] + 2
            curr_r = rows_mod[row_idx-1]
            
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
                if c_edit.form_submit_button("💾 수정된 내용 저장", use_container_width=True):
                    updated_row = [
                        m_date.strftime("%Y-%m-%d"), m_name, m_agency, 
                        m_count, m_info, m_type, m_time, m_memo, curr_r[8]
                    ]
                    ws_mod.update(f'A{row_idx}:I{row_idx}', [updated_row])
                    st.success("✅ 모든 정보가 수정되었습니다."); st.cache_data.clear(); time.sleep(1); st.rerun()
                
                if c_del.form_submit_button("🗑️ 예약 삭제", use_container_width=True):
                    ws_mod.delete_rows(row_idx)
                    st.success("🗑️ 해당 예약이 삭제되었습니다."); st.cache_data.clear(); time.sleep(1); st.rerun()
        else:
            st.info("해당 날짜에 예약 내역이 없습니다.")
