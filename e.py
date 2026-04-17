import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, date, timedelta, timezone
import json
import uuid
import smtplib
import time
from email.mime.text import MIMEText

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

TIME_SLOTS = ["10:00 ~ 10:45", "11:00 ~ 11:45", "13:00 ~ 13:45", "14:00 ~ 14:45", "15:00 ~ 15:45", "16:00 ~ 16:45", "17:00 ~ 17:45"]
COL_NAMES = ["예약날짜", "예약자", "중개업소", "관람세대수", "동호수", "타입", "예약시간", "비고", "ID"]

# --- [추가기능: 신규 매물 마킹 로직] ---
def apply_new_mark(df, top_n=3):
    try:
        df['temp_no'] = pd.to_numeric(df['NO.'], errors='coerce')
        if len(df) > 0:
            threshold_no = df['temp_no'].nlargest(top_n).min()
            df['호수'] = df.apply(
                lambda x: f"🆕 {x['호수']}" if x['temp_no'] >= threshold_no else x['호수'], 
                axis=1
            )
        df = df.drop(columns=['temp_no'])
    except: pass
    return df

# =========================
# 📩 이메일 및 구글 API 연결
# =========================
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

@st.cache_data(ttl=600)
def load_full_data():
    try:
        sheets_to_load = ["1단지_매매","1단지_임대","2단지_매매","2단지_임대","3단지_매매","3단지_임대"]
        df_list = []
        for s in sheets_to_load:
            try:
                ws = sheet.worksheet(s); data = ws.get_all_values()
                if len(data) > 1:
                    df = pd.DataFrame(data[1:], columns=["NO.","분양구분","동","호수","타입","매물구분","매매가","월세","거래여부", "비고"])
                    df["단지"] = s.split("_")[0]; df["거래유형"] = s.split("_")[1]
                    
                    # --- [이 부분이 핵심 수정 사항입니다] ---
                    # 각 시트(단지/유형)별로 가져올 때마다 바로 신규 마킹을 적용합니다.
                    # 그래야 각 단지별 매매 3개, 임대 3개씩 총 18개가 🆕 마크를 답니다.
                    df = apply_new_mark(df, top_n=3)
                    # --------------------------------------
                    
                    df_list.append(df)
            except: continue
        
        user_ws = sheet.worksheet("사용자목록"); u_data = user_ws.get_all_values()
        user_dict = {str(row[0]).strip(): str(row[1]).strip() for row in u_data[1:] if len(row) >= 2}
        
        # 데이터 합치기
        full_df = pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()
        
        # 합친 후에는 이미 개별적으로 마킹이 끝났으므로 
        # 기존에 있던 full_df = apply_new_mark(full_df, top_n=3) 이 줄은 불필요해서 뺀 것입니다.
        # (합친 후에 또 하면 마크가 꼬일 수 있거든요)
            
        return full_df, user_dict
    except: return pd.DataFrame(), {}
df_total, user_dict = load_full_data()

def apply_style(df):
    try: return df.style.map(lambda x: "background-color: #d4edda" if "관람가능" in str(x) else "background-color: #f8d7da" if "거래완료" in str(x) else "", subset=["거래여부"])
    except: return df.style.applymap(lambda x: "background-color: #d4edda" if "관람가능" in str(x) else "background-color: #f8d7da" if "거래완료" in str(x) else "", subset=["거래여부"])

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
            else: st.error("❌ 아이디 또는 비밀번호가 일치하지 않습니다.")
    st.stop()

# =========================
# 🏠 사이드바 메뉴
# =========================
menu_options = ["📊 실시간 현황", "🔍 등록 매물 조회", "📅 세대관람 예약"]
with st.sidebar:
    st.success(f"👤 {st.session_state.user_id} 접속 중")
    choice = st.radio("메뉴 이동", menu_options)
    st.divider()
    if st.button("🔄 새로고침"): st.cache_data.clear(); st.rerun()
    if st.button("🔒 로그아웃"): st.session_state.clear(); st.rerun()

# =========================
# 📊 [페이지 1] 실시간 현황
# =========================
if choice == "📊 실시간 현황":
    st.title("📊 실시간 현황")
    
    # 1. 상단 지표 (Metric)
    c1, c2, c3 = st.columns(3)
    c1.metric("📌 전체 매물", f"{len(df_total)}개")
    c2.metric("✅ 거래완료", f"{len(df_total[df_total['거래여부']=='거래완료'])}개")
    c3.metric("🏠 관람가능", f"{len(df_total[df_total['거래여부']=='관람가능'])}개")
    
    st.divider()

    # --- [수정된 섹션: 신규 등록 매물 리스트] ---
    st.subheader("✨ 신규 등록 매물")
    
    # [핵심 수정]: '🆕' 마크가 있고 + '거래여부'가 '관람가능'인 데이터만 추출
    df_new = df_total[
        (df_total["호수"].str.contains("🆕")) & 
        (df_total["거래여부"] == "관람가능")
    ].copy()
    
    if not df_new.empty:
        # 보기 좋게 단지/동/호수 순으로 정렬
        df_new_view = df_new.sort_values(["단지", "동", "호수"])[["단지", "동", "호수", "타입", "매물구분", "매매가", "월세", "거래여부", "비고"]]
        st.dataframe(apply_style(df_new_view), use_container_width=True, hide_index=True)
    else:
        st.info("현재 관람 가능한 신규 매물이 없습니다.")
    # -------------------------------------------

    st.divider()

    # 2. 하단 거래완료 매물 리스트
    st.subheader("🔒 거래완료 매물 내역")
    df_done = df_total[df_total["거래여부"] == "거래완료"].copy()
    for col in ["매매가", "월세", "비고"]:
        if col in df_done.columns: df_done[col] = "🔒 거래완료"
    
    st.dataframe(apply_style(df_done[["단지", "동", "호수", "타입", "매물구분", "매매가", "월세", "거래여부", "비고"]]), use_container_width=True, hide_index=True)

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
    if search_dong: df_v = df_v[df_v["동"].str.contains(search_dong, na=False)]
    if search_ho: df_v = df_v[df_v["호수"].str.contains(search_ho, na=False)]
    
    mask = df_v["거래여부"] == "거래완료"
    for col in ["매매가", "월세", "비고"]:
        if col in df_v.columns: df_v.loc[mask, col] = "🔒 거래완료"
    st.dataframe(apply_style(df_v[["단지", "동", "호수", "타입", "매물구분", "매매가", "월세", "거래여부", "비고"]]), use_container_width=True, hide_index=True)

# =========================
# 📅 [페이지 3] 세대관람 예약
# =========================
elif choice == "📅 세대관람 예약":
    st.title("📋 세대관람 예약 시스템")
    is_admin_user = st.session_state.user_id in ["admin", "master", "unam0119"]
    
    tab1, tab2, tab3 = st.tabs(["📝 예약 등록", "📅 단지별 예약 현황", "🛠️ 내 예약 관리"])
    
    with tab1:
        st.subheader("📝 세대관람 예약 등록")
        KST = timezone(timedelta(hours=9))
        now = datetime.now(KST); today_date = now.date() 
        
        c1, c2 = st.columns(2)
        res_dj = c1.selectbox("단지 선택", ["1단지", "2단지", "3단지"], key="res_dj_select")
        r_date_val = c2.date_input("예약 날짜 선택", value=today_date, key="res_date_input")
        
        is_today = (r_date_val == today_date)
        curr_time_num = int(now.strftime("%H%M"))
        available_slots = []
        for slot in TIME_SLOTS:
            start_time_part = slot.split(" ~ ")[0] 
            sh, sm = map(int, start_time_part.split(":"))
            limit_num = int(f"{sh:02d}{sm+30:02d}") if sm+30 < 60 else int(f"{sh+1:02d}{sm-30:02d}")
            if is_admin_user or not (is_today and curr_time_num >= limit_num):
                available_slots.append(slot)

        if not available_slots:
            st.error("⏰ 오늘 예약 가능한 시간대가 마감되었습니다.")
            can_reserve = False; t_val = "마감"
        else:
            t_val = st.selectbox("🕒 관람 시간 선택", available_slots, key="res_time_select")
            can_reserve = True

        target_ws = sheet.worksheet(f"{res_dj}_관람예약"); all_res = target_ws.get_all_values()
        daily_df = pd.DataFrame(all_res[1:], columns=all_res[0]) if len(all_res) > 1 else pd.DataFrame(columns=COL_NAMES)
        v_filtered = daily_df[(daily_df["예약날짜"] == r_date_val.strftime("%Y-%m-%d")) & (daily_df["예약시간"] == t_val)]

        error_msg = ""; user_id = st.session_state.user_id
        if not is_admin_user:
            if is_today and curr_time_num >= 1540:
                error_msg = "⏰ 당일 예약은 오후 3시 40분(15:40)에 마감되었습니다."; can_reserve = False
            elif can_reserve and not v_filtered.empty:
                if user_id in v_filtered.iloc[:, 8].values:
                    error_msg = "🚫 이미 동일한 시간대에 예약한 내역이 있습니다."; can_reserve = False
            if can_reserve and len(v_filtered) >= 3:
                error_msg = f"🚫 {t_val} 타임은 마감되었습니다."; can_reserve = False

        if error_msg: st.warning(error_msg)

        # [핵심 수정: 관람가능 매물만 필터링]
        f_unit = df_total[(df_total["단지"] == res_dj) & (df_total["거래여부"] == "관람가능")]
        u_dongs = sorted(f_unit["동"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
        
        if f_unit.empty:
            st.error("현재 해당 단지에 관람 가능한 매물이 없습니다.")
            can_reserve = False
        
        r_count = st.selectbox("🏠 관람 세대수", [1, 2], key="res_count_select")
        
        r_items = []
        for i in range(r_count):
            row_c1, row_c2 = st.columns(2)
            sel_d = row_c1.selectbox(f"동 ({i+1})", u_dongs, key=f"r_d_{i}")
            # 호수 리스트에서도 거래완료는 자동 제외됨
            raw_hos = f_unit[f_unit["동"] == sel_d]["호수"].tolist()
            clean_hos = [h.replace("🆕 ", "") for h in raw_hos]
            sel_h = row_c2.selectbox(f"호수 ({i+1})", clean_hos, key=f"r_h_{i}")
            match = f_unit[(f_unit["동"] == sel_d) & (f_unit["호수"].str.contains(sel_h))]
            if not match.empty: r_items.append({"동": sel_d, "호수": sel_h, "타입": match.iloc[0]['타입']})

        with st.form("reserve_form"):
            r_name = st.text_input("(📝필수) 예약자 성함[실명]")
            r_agency = st.text_input("(📝필수) 중개업소 명칭")
            memo_input = st.text_area("(선택) 비고")
            btn_label = "📅 예약 강제 등록 (관리자)" if is_admin_user else "📅 예약 최종 확정"
            submit_btn = st.form_submit_button(btn_label, disabled=not can_reserve)
            
            if submit_btn:
                if not r_name or not r_agency: st.error("성함과 업소명을 입력하세요.")
                else:
                    combined_info = " / ".join([f"{it['동']}동 {it['호수']}호" for it in r_items])
                    types_str = ", ".join([str(s["타입"]) for s in r_items])
                    final_id = f"{user_id}(관리자)" if is_admin_user else user_id
                    new_row = [r_date_val.strftime("%Y-%m-%d"), r_name, r_agency, f"{len(r_items)}세대", combined_info, types_str, t_val, memo_input, final_id]
                    target_ws.append_row(new_row)
                    st.success("✅ 예약이 완료되었습니다!"); st.cache_data.clear(); time.sleep(1); st.rerun()

    with tab2:
        st.subheader("📋 단지별 예약 현황")
        sel_dj_view = st.radio("조회 단지 선택", ["1단지", "2단지", "3단지"], horizontal=True)
        view_date = st.date_input("조회 일자", today_date)
        
        ws_view = sheet.worksheet(f"{sel_dj_view}_관람예약"); d_view = ws_view.get_all_values()
        df_view_tab = pd.DataFrame(d_view[1:], columns=d_view[0]) if len(d_view) > 1 else pd.DataFrame(columns=COL_NAMES)
        
        if not df_view_tab.empty:
            v_daily = df_view_tab[df_view_tab["예약날짜"] == view_date.strftime("%Y-%m-%d")].copy()
            cols = st.columns(len(TIME_SLOTS))
            for idx, slot in enumerate(TIME_SLOTS):
                count = len(v_daily[v_daily["예약시간"] == slot])
                is_closed = count >= 3
                with cols[idx]:
                    color = "#ff4b4b" if is_closed else "#28a745"
                    st.markdown(f'<div style="text-align:center; border:1px solid {color}; border-radius:5px;"><small>{slot[:5]}</small><br><b style="color:{color}">{3-count}석</b></div>', unsafe_allow_html=True)
            
            def mask_name(name): return name[0] + "*" * (len(name)-1) if not is_admin_user and len(name) > 1 else name
            v_daily["예약자"] = v_daily["예약자"].apply(mask_name)
            st.divider()
            st.dataframe(v_daily[["예약시간", "예약자", "관람세대수", "동호수"]].sort_values("예약시간"), use_container_width=True, hide_index=True)
        else: st.info("등록된 예약이 없습니다.")

    with tab3:
        st.subheader("👤 내 예약 수정/취소")
        my_dj = st.selectbox("단지 선택", ["1단지", "2단지", "3단지"], key="my_dj_sel")
        ws_my = sheet.worksheet(f"{my_dj}_관람예약"); my_data = ws_my.get_all_values()
        if len(my_data) > 1:
            df_my = pd.DataFrame(my_data[1:], columns=my_data[0])
            my_res_only = df_my if is_admin_user else df_my[df_my.iloc[:, 8].str.contains(st.session_state.user_id)]
            
            if not my_res_only.empty:
                my_map = {f"[{r['예약날짜']} {r['예약시간']}] {r['예약자']} - {r['동호수']}": i+2 for i, r in my_res_only.iterrows()}
                sel_my_res = st.selectbox("항목 선택", list(my_map.keys()))
                row_idx = my_map[sel_my_res]
                
                if st.button("🗑️ 예약 취소(삭제)", use_container_width=True):
                    ws_my.delete_rows(row_idx)
                    st.success("취소되었습니다."); st.cache_data.clear(); time.sleep(1); st.rerun()
            else: st.info("예약 내역이 없습니다.")
