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
    .section-box { border: 2px solid #4A90E2; padding: 25px; border-radius: 12px; background-color: #ffffff; margin-bottom: 25px; box-shadow: 2px 2px 10px rgba(0,0,0,0.05); }
    .admin-header { color: #4A90E2; font-weight: bold; border-left: 5px solid #4A90E2; padding-left: 10px; margin-bottom: 20px; }
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
                df['temp_no'] = pd.to_numeric(df['NO.'], errors='coerce')
                if not df.empty:
                    top_3_val = df['temp_no'].nlargest(3).min()
                    df['호수'] = df.apply(lambda x: f"🆕 {x['호수']}" if x['temp_no'] >= top_3_val else x['호수'], axis=1)
                df_list.append(df)
        except: continue
    return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()

df_total = load_admin_data_all()

# =========================
# 🏠 사이드바 및 메뉴 (메뉴 분리)
# =========================
st.sidebar.title("🛠️ 마스터 메뉴")
choice = st.sidebar.radio("작업 선택", ["📋 매물 현황 & 관리", "📝 마스터 예약 등록", "📅 통합 예약 현황판", "✂️ 예약 수정/삭제"])
if st.sidebar.button("🔄 데이터 새로고침"): st.cache_data.clear(); st.rerun()

# =========================
# 📋 [메뉴 1] 매물 현황 & 관리
# =========================
if choice == "📋 매물 현황 & 관리":
    st.title("📋 매물 실시간 현황")
    st.subheader("📍 단지별 매물 요약")
    m1, m2, m3 = st.columns(3)
    for idx, dj in enumerate(["1단지", "2단지", "3단지"]):
        dj_df = df_total[df_total["단지"] == dj]
        can_view = len(dj_df[dj_df["거래여부"] == "관람가능"])
        total_count = len(dj_df)
        [m1, m2, m3][idx].metric(dj, f"{can_view} / {total_count}", "관람가능")
    
    st.divider()
    
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.markdown('<div class="admin-header">⚙️ 매물 상태 변경</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    a_dj = c1.selectbox("변경 단지 선택", ["1단지", "2단지", "3단지"])
    a_dong = c2.text_input("변경 동 입력")
    a_ho = c3.text_input("변경 호수 입력")

    if a_dong and a_ho:
        target = df_total[(df_total["단지"] == a_dj) & (df_total["동"] == a_dong) & (df_total["호수"].str.contains(a_ho))]
        if not target.empty:
            curr = target.iloc[0]
            with st.form("status_update"):
                st.write(f"현재 선택: **{a_dj} {a_dong}동 {curr['호수']}** (상태: {curr['거래여부']})")
                new_s = st.selectbox("변경할 상태", ["관람가능", "거래완료"], index=0 if curr["거래여부"]=="관람가능" else 1)
                new_n = st.text_input("비고 수정", value=curr["비고"])
                if st.form_submit_button("상태 저장"):
                    ws = sheet.worksheet(f"{a_dj}_{curr['거래유형']}")
                    rows = ws.get_all_values()
                    idx = -1
                    clean_ho = a_ho.replace("🆕 ", "")
                    for i, r in enumerate(rows):
                        if len(r) > 3 and r[2] == a_dong and r[3] == clean_ho: idx = i + 1; break
                    if idx != -1:
                        ws.update(f'I{idx}:J{idx}', [[new_s, new_n]])
                        st.success("✅ 저장 성공!"); st.cache_data.clear(); time.sleep(1); st.rerun()
        else: st.warning("해당 매물을 찾을 수 없습니다.")
    st.markdown('</div>', unsafe_allow_html=True)

    st.subheader("🔍 매물 현황 조회")
    f1, f2, f3 = st.columns(3)
    f_dj = f1.multiselect("단지 필터", ["1단지", "2단지", "3단지"])
    f_bun = f2.multiselect("분양구분 필터", df_total["분양구분"].unique())
    f_type = f3.multiselect("타입 필터", sorted(df_total["타입"].unique()))
    
    df_v = df_total.copy()
    if f_dj: df_v = df_v[df_v["단지"].isin(f_dj)]
    if f_bun: df_v = df_v[df_v["분양구분"].isin(f_bun)]
    if f_type: df_v = df_v[df_v["타입"].isin(f_type)]
    st.dataframe(df_v[["단지", "분양구분", "동", "호수", "타입", "매물구분", "매매가", "월세", "거래여부", "비고"]], use_container_width=True, hide_index=True)

# =========================
# 📝 [메뉴 2] 마스터 예약 등록 (대폭 수정)
# =========================
elif choice == "📝 마스터 예약 등록":
    st.title("📝 마스터 전용 예약 등록")
    st.info("관리자 권한으로 예약을 강제 등록하는 페이지입니다. '관람가능' 매물만 선택 가능합니다.")

    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.markdown('<div class="admin-header">1. 기본 정보 입력</div>', unsafe_allow_html=True)
    
    r1, r2, r3 = st.columns(3)
    m_dj = r1.selectbox("예약 단지 선택", ["1단지", "2단지", "3단지"])
    m_date = r2.date_input("예약 날짜", date.today())
    m_time = r3.selectbox("예약 시간", TIME_SLOTS)
    
    r4, r5, r6 = st.columns(3)
    m_name = r4.text_input("예약자 성함(실명)")
    m_agency = r5.text_input("중개업소 명칭")
    m_count = r6.selectbox("관람 세대수 선택", [1, 2])
    
    st.divider()
    st.markdown('<div class="admin-header">2. 관람 세대 선택</div>', unsafe_allow_html=True)

    # 해당 단지의 '관람가능' 매물만 필터링
    avail_units = df_total[(df_total["단지"] == m_dj) & (df_total["거래여부"] == "관람가능")]
    u_dongs = sorted(avail_units["동"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
    
    m_items = []
    # 세대수 선택에 따라 입력란이 유동적으로 생성됨
    for i in range(m_count):
        st.write(f"**🏠 세대 {i+1} 선택**")
        c_dong, c_ho = st.columns(2)
        
        # 1. 동 선택
        sel_d = c_dong.selectbox(f"단지 내 동 선택 ({i+1})", u_dongs, key=f"ad_d_{i}")
        
        # 2. 선택된 동에 해당하는 호수만 필터링 (동-호수 연동 핵심)
        hos_in_dong = avail_units[avail_units["동"] == sel_d]["호수"].tolist()
        clean_hos = [h.replace("🆕 ", "") for h in hos_in_dong]
        
        # 3. 호수 선택
        sel_h = c_ho.selectbox(f"해당 동 내 호수 선택 ({i+1})", clean_hos, key=f"ad_h_{i}")
        
        if sel_d and sel_h:
            m_items.append({"동": sel_d, "호수": sel_h})

    m_memo = st.text_area("비고 (선택사항)")
    
    if st.button("📅 예약 최종 강제 등록", use_container_width=True):
        if not m_name or not m_agency:
            st.error("❌ 예약자 성함과 중개업소명은 필수 입력 사항입니다.")
        elif not m_items:
            st.error("❌ 선택된 세대 정보가 없습니다.")
        else:
            try:
                target_ws = sheet.worksheet(f"{m_dj}_관람예약")
                combined_ho_str = " / ".join([f"{it['동']}동 {it['호수']}호" for it in m_items])
                
                # 첫 번째 호실의 타입 정보 추출
                first_h = m_items[0]['호수']
                first_d = m_items[0]['동']
                match_type = avail_units[(avail_units["동"] == first_d) & (avail_units["호수"].str.contains(first_h))]["타입"].iloc[0]
                
                new_row = [
                    m_date.strftime("%Y-%m-%d"), 
                    m_name, 
                    m_agency, 
                    f"{m_count}세대", 
                    combined_ho_str, 
                    match_type, 
                    m_time, 
                    m_memo, 
                    "admin(마스터)"
                ]
                target_ws.append_row(new_row)
                st.success(f"✅ [{m_dj}] {combined_ho_str} 예약이 성공적으로 등록되었습니다."); st.cache_data.clear(); time.sleep(1); st.rerun()
            except Exception as e:
                st.error(f"오류 발생: {e}")
    st.markdown('</div>', unsafe_allow_html=True)

# =========================
# 📅 [메뉴 3] 통합 예약 현황판 (조회 전용으로 깔끔하게)
# =========================
elif choice == "📅 통합 예약 현황판":
    st.title("📅 전 단지 예약 현황")
    search_date = st.date_input("조회 날짜", date.today())
    target_date_str = search_date.strftime("%Y-%m-%d")
    
    for dj in ["1단지", "2단지", "3단지"]:
        st.subheader(f"📍 {dj} 예약 상황")
        try:
            ws = sheet.worksheet(f"{dj}_관람예약"); d_view = ws.get_all_values()
            df_v = pd.DataFrame(d_view[1:], columns=d_view[0]) if len(d_view) > 1 else pd.DataFrame(columns=["예약날짜", "예약시간", "예약자", "중개업소", "동호수", "관람세대수"])
            v_daily = df_v[df_v["예약날짜"] == target_date_str]
            
            cols = st.columns(len(TIME_SLOTS))
            for idx, slot in enumerate(TIME_SLOTS):
                count = len(v_daily[v_daily["예약시간"] == slot])
                with cols[idx]:
                    color = "#FF4B4B" if count >= 3 else "#28A745"
                    st.markdown(f'<div style="text-align:center; padding:5px; border:1px solid {color}; border-radius:5px;"><small>{slot.split("~")[0].strip()}</small><br><b style="color:{color};">{count}/3</b></div>', unsafe_allow_html=True)
            
            if not v_daily.empty:
                st.dataframe(v_daily[["예약시간", "예약자", "중개업소", "동호수", "관람세대수"]].sort_values("예약시간"), use_container_width=True, hide_index=True)
            else: st.info(f"{dj}에 해당 날짜 예약이 없습니다.")
            st.divider()
        except: st.error(f"{dj} 데이터를 불러올 수 없습니다.")

# =========================
# ✂️ [메뉴 4] 예약 수정/삭제
# =========================
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
            day_mod = day_mod.sort_values("예약시간")
            opts = [f"[{r['예약시간']}] {r['예약자']} ({r['중개업소']}) - {r['동호수']}" for i, r in day_mod.iterrows()]
            sel_text = st.selectbox("수정할 항목 선택", opts)
            selected_row = day_mod.iloc[opts.index(sel_text)]
            row_idx = int(selected_row.name) + 2 
            
            curr_r = rows_mod[row_idx-1]
            with st.form("master_edit"):
                st.write(f"현재 선택 행: {row_idx}번 라인")
                m_name = st.text_input("성함", value=curr_r[1])
                m_agency = st.text_input("중개업소", value=curr_r[2])
                m_info = st.text_input("동호수", value=curr_r[4])
                
                col_btn1, col_btn2 = st.columns(2)
                if col_btn1.form_submit_button("저장"):
                    ws_mod.update(f'B{row_idx}:C{row_idx}', [[m_name, m_agency]])
                    ws_mod.update(f'E{row_idx}', [[m_info]])
                    st.success("✅ 수정 성공!"); st.cache_data.clear(); time.sleep(1); st.rerun()
                
                if col_btn2.form_submit_button("🚨 예약 삭제"):
                    ws_mod.delete_rows(row_idx)
                    st.warning("🗑️ 예약이 삭제되었습니다."); st.cache_data.clear(); time.sleep(1); st.rerun()
        else: st.info("해당 날짜에 예약이 없습니다.")
