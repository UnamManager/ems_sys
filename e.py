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

# =========================
# 1. 페이지 설정 및 디자인 (문구/기능 유지)
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
# 🔑 세션 및 환경 설정 (관리자 비밀번호 제거)
# =========================
if "session_key" not in st.session_state: st.session_state["session_key"] = str(uuid.uuid4())
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
if "user_id" not in st.session_state: st.session_state["user_id"] = ""

TIME_SLOTS = ["10:00 ~ 10:45", "11:00 ~ 11:45", "13:00 ~ 13:45", "14:00 ~ 14:45", "15:00 ~ 15:45", "16:00 ~ 16:45", "17:00 ~ 17:45"]
COL_NAMES = ["예약날짜", "예약자", "중개업소", "관람세대수", "동호수", "타입", "예약시간", "비고"]

# =========================
# 📩 이메일 알림 및 구글 API 연결
# =========================
def send_email_notification(content):
    try:
        sender = st.secrets["EMAIL_ADDRESS"]; password = st.secrets["EMAIL_PASSWORD"]; receiver = st.secrets["ADMIN_NOTIFY_EMAIL"]
        msg = MIMEText(content); msg["Subject"] = "📢 새로운 관람 예약 등록"; msg["From"] = sender; msg["To"] = receiver
        server = smtplib.SMTP("smtp.gmail.com", 587); server.starttls(); server.login(sender, password)
        server.sendmail(sender, receiver, msg.as_string()); server.quit()
    except: pass 

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
                    for col in ["매매가", "월세"]:
                        df[f"{col}_num"] = pd.to_numeric(df[col].str.replace(',', ''), errors='coerce').fillna(0)
                    df_list.append(df)
            except: continue
        user_ws = sheet.worksheet("사용자목록"); u_data = user_ws.get_all_values()
        user_dict = {str(row[0]).strip(): str(row[1]).strip() for row in u_data[1:] if len(row) >= 2}
        if df_list: return pd.concat(df_list, ignore_index=True), user_dict
        else: return pd.DataFrame(columns=["NO.","분양구분","동","호수","타입","매물구분","매매가","월세","거래여부", "비고", "단지", "거래유형"]), user_dict
    except: return pd.DataFrame(), {}

df_total, user_dict = load_full_data()

def apply_style(df):
    try: return df.style.map(lambda x: "background-color: #d4edda" if x == "관람가능" else "background-color: #f8d7da" if x == "거래완료" else "", subset=["거래여부"])
    except: return df.style.applymap(lambda x: "background-color: #d4edda" if x == "관람가능" else "background-color: #f8d7da" if x == "거래완료" else "", subset=["거래여부"])

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
# 🏠 사이드바 및 메뉴 (관리자 메뉴 완전 제거)
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
# 📅 [페이지 3] 세대관람 예약 (문구/기능 100% 유지)
# =========================
elif choice == "📅 세대관람 예약":
    st.title("📋 세대관람 예약 시스템")
    tab1, tab2, tab3 = st.tabs(["📝 예약 등록", "📅 단지별 예약 현황", "🛠️ 내 예약 관리"])
    
    with tab1:
        st.subheader("📝 세대관람 예약 등록")
        KST = timezone(timedelta(hours=9))
        now = datetime.now(KST); today_date = now.date() 
        
        c1, c2 = st.columns(2)
        res_dj = c1.selectbox("단지 선택", ["1단지", "2단지", "3단지"], key="res_dj_select")
        r_date_val = c2.date_input("예약 날짜 선택", value=today_date, min_value=today_date, key="res_date_input")
        
        is_today = (r_date_val == today_date)
        available_slots = []
        curr_time_num = int(now.strftime("%H%M"))
        
        for slot in TIME_SLOTS:
            start_time_part = slot.split(" ~ ")[0] 
            sh, sm = map(int, start_time_part.split(":"))
            limit_minute = sm + 30; limit_hour = sh
            if limit_minute >= 60: limit_hour += 1; limit_minute -= 60
            limit_num = int(f"{limit_hour:02d}{limit_minute:02d}")
            if is_today and curr_time_num >= limit_num: continue
            available_slots.append(slot)

        if not available_slots:
            st.error("⏰ 오늘 예약 가능한 모든 시간대가 마감되었습니다.")
            can_reserve = False; t_val = "마감"
        else:
            t_val = st.selectbox("🕒 관람 시간 선택", available_slots, key="res_time_select")
            can_reserve = True

        target_ws = sheet.worksheet(f"{res_dj}_관람예약"); all_res = target_ws.get_all_values()
        daily_df = pd.DataFrame(all_res[1:], columns=all_res[0]) if len(all_res) > 1 else pd.DataFrame(columns=COL_NAMES)
        v_filtered = daily_df[(daily_df["예약날짜"] == r_date_val.strftime("%Y-%m-%d")) & (daily_df["예약시간"] == t_val)]

        error_msg = ""; user_id = st.session_state.user_id
        if is_today and curr_time_num >= 1540:
            error_msg = "⏰ 당일 예약은 오후 3시 40분(15:40)에 최종 마감되었습니다."; can_reserve = False
        elif can_reserve and not v_filtered.empty:
            is_korean_id = ('가' <= user_id[0] <= '힣') if user_id else False
            if not is_korean_id and user_id in v_filtered.iloc[:, 8].values:
                error_msg = "🚫 이미 동일한 시간대에 예약한 내역이 있습니다. (영문 계정은 1인 1개 타임 제한)"; can_reserve = False
        if can_reserve and len(v_filtered) >= 3:
            error_msg = f"🚫 {t_val} 타임은 이미 3명이 예약하여 마감되었습니다."; can_reserve = False

        if not can_reserve: st.warning(error_msg)

        f_unit = df_total[df_total["단지"] == res_dj]
        u_dongs = sorted(f_unit["동"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
        r_count = st.selectbox("🏠 관람 세대수 (최대 2세대)", [1, 2], key="res_count_select")
        
        r_items = []
        for i in range(r_count):
            row_c1, row_c2 = st.columns(2)
            sel_d = row_c1.selectbox(f"동 ({i+1})", u_dongs, key=f"r_d_{i}")
            u_hos = sorted(f_unit[f_unit["동"] == sel_d]["호수"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
            sel_h = row_c2.selectbox(f"호수 ({i+1})", u_hos, key=f"r_h_{i}")
            match = f_unit[(f_unit["동"] == sel_d) & (f_unit["호수"] == sel_h)]
            if not match.empty: r_items.append({"동": sel_d, "호수": sel_h, "타입": match.iloc[0]['타입']})

        with st.form("reserve_form"):
            r_name = st.text_input("(📝필수) 예약자 성함[실명]")
            r_agency = st.text_input("(📝필수) 중개업소 명칭")
            memo_input = st.text_area("(선택) 비고")
            submit_btn = st.form_submit_button("📅 예약 최종 확정", disabled=not can_reserve)
            
            if submit_btn:
                if not r_name or not r_agency: st.error("성함과 업소명을 입력하세요.")
                else:
                    combined_info = " / ".join([f"{it['동']}동 {it['호수']}호" for it in r_items])
                    types_str = ", ".join([s["타입"] for s in r_items])
                    new_row = [r_date_val.strftime("%Y-%m-%d"), r_name, r_agency, f"{len(r_items)}세대", combined_info, types_str, t_val, memo_input, st.session_state.user_id]
                    target_ws.append_row(new_row)
                    st.success("✅ 예약이 정상적으로 완료되었습니다!"); st.cache_data.clear(); time.sleep(1); st.rerun()

    with tab2:
        st.subheader("📋 단지별 예약 현황")
        sel_dj_view = st.radio("조회 단지 선택", ["1단지", "2단지", "3단지"], horizontal=True, key="view_danji_radio")
        view_date = st.date_input("조회 일자", today_date, key="view_date_picker")
        is_view_today = (view_date == today_date)

        try:
            ws_view = sheet.worksheet(f"{sel_dj_view}_관람예약"); d_view = ws_view.get_all_values()
            df_view = pd.DataFrame(d_view[1:], columns=d_view[0]) if len(d_view) > 1 else pd.DataFrame(columns=COL_NAMES)
            if not df_view.empty:
                v_daily = df_view[df_view["예약날짜"] == view_date.strftime("%Y-%m-%d")].copy()
                cols = st.columns(len(TIME_SLOTS))
                for idx, slot in enumerate(TIME_SLOTS):
                    count = len(v_daily[v_daily["예약시간"] == slot])
                    sh, sm = map(int, slot.split(" ~ ")[0].split(":"))
                    limit_min = sm + 30; limit_hr = sh
                    if limit_min >= 60: limit_hr += 1; limit_min -= 60
                    limit_n = int(f"{limit_hr:02d}{limit_min:02d}")
                    is_closed = (is_view_today and curr_time_num >= limit_n) or count >= 3
                    with cols[idx]:
                        color = "#ff4b4b" if is_closed else "#28a745"; label = "마감" if is_closed else f"{3-count}석 가능"
                        st.markdown(f'<div style="text-align:center; padding:5px; border:1px solid {color}; border-radius:5px; margin-bottom:10px;"><small style="font-size:0.7rem;">{slot.split("~")[0]}</small><br><b style="color:{color}; font-size:0.85rem;">{label}</b></div>', unsafe_allow_html=True)
                def mask_name(name): return name[0] + "*" * (len(name)-1) if name and len(name) > 1 else "*"
                if "예약자" in v_daily.columns: v_daily["예약자"] = v_daily["예약자"].apply(mask_name)
                v_daily['예약시간'] = pd.Categorical(v_daily['예약시간'], categories=TIME_SLOTS, ordered=True)
                st.divider(); st.dataframe(v_daily.sort_values('예약시간')[["예약시간", "예약자", "관람세대수", "동호수"]].rename(columns={"동호수":"관람상세"}), use_container_width=True, hide_index=True)
            else: st.info(f"📅 {sel_dj_view}에 등록된 예약 데이터가 없습니다.")
        except: st.error("데이터 로드 실패")

    with tab3:
        st.subheader("👤 내 예약 수정/취소")
        my_dj = st.selectbox("수정할 예약의 단지 선택", ["1단지", "2단지", "3단지"], key="my_mod_dj_sel")
        try:
            ws_my = sheet.worksheet(f"{my_dj}_관람예약"); my_data = ws_my.get_all_values()
            if len(my_data) > 1:
                df_my = pd.DataFrame(my_data[1:], columns=my_data[0])
                my_res_only = df_my[df_my.iloc[:, 8] == st.session_state.user_id]
                if not my_res_only.empty:
                    my_map = {f"[{r['예약날짜']} {r['예약시간']}] {r['동호수']}": i+2 for i, r in my_res_only.iterrows()}
                    sel_my_res = st.selectbox("수정/취소할 항목 선택", list(my_map.keys()), key="sel_my_res_box")
                    row_idx = my_map[sel_my_res]; curr_my = my_data[row_idx-1]
                    st.divider()
                    m_date = st.date_input("📅 날짜 변경", value=datetime.strptime(curr_my[0], "%Y-%m-%d"), key=f"my_date_{row_idx}")
                    m_time = st.selectbox("🕒 시간 변경", TIME_SLOTS, index=TIME_SLOTS.index(curr_my[6]) if curr_my[6] in TIME_SLOTS else 0, key=f"my_time_{row_idx}")
                    f_unit_my = df_total[df_total["단지"] == my_dj]; u_dongs_my = sorted(f_unit_my["동"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
                    m_count = st.selectbox("🏠 세대수 변경", [1, 2], index=0 if curr_my[3] == "1세대" else 1, key=f"my_cnt_{row_idx}")
                    exist_units = curr_my[4].split(" / "); new_items = []
                    for i in range(m_count):
                        c1, c2 = st.columns(2)
                        d_val = exist_units[i].split("동")[0].strip() if i < len(exist_units) else u_dongs_my[0]
                        m_d = c1.selectbox(f"동 ({i+1})", u_dongs_my, index=u_dongs_my.index(d_val) if d_val in u_dongs_my else 0, key=f"my_d_box_{row_idx}_{i}")
                        u_hos_my = sorted(f_unit_my[f_unit_my["동"]==m_d]["호수"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
                        try: h_val = exist_units[i].split("동")[1].replace("호","").strip() if i < len(exist_units) else u_hos_my[0]
                        except: h_val = u_hos_my[0]
                        m_h = c2.selectbox(f"호수 ({i+1})", u_hos_my, index=u_hos_my.index(h_val) if h_val in u_hos_my else 0, key=f"my_h_box_{row_idx}_{i}")
                        match_u = f_unit_my[(f_unit_my["동"]==m_d) & (f_unit_my["호수"]==m_h)]
                        if not match_u.empty: new_items.append({"동": m_d, "호수": m_h, "타입": match_u.iloc[0]['타입']})
                    b1, b2 = st.columns(2)
                    if b1.button("💾 수정 저장", use_container_width=True, type="primary", key=f"save_{row_idx}"):
                        new_info = " / ".join([f"{it['동']}동 {it['호수']}호" for it in new_items]); new_type = ", ".join([s["타입"] for s in new_items])
                        ws_my.update(f'A{row_idx}', [[m_date.strftime("%Y-%m-%d")]])
                        ws_my.update(f'D{row_idx}:G{row_idx}', [[f"{m_count}세대", new_info, new_type, m_time]])
                        st.success("수정되었습니다."); st.cache_data.clear(); time.sleep(1); st.rerun()
                    if b2.button("🗑️ 예약 취소", use_container_width=True, key=f"del_{row_idx}"):
                        ws_my.delete_rows(row_idx); st.success("취소되었습니다."); st.cache_data.clear(); time.sleep(1); st.rerun()
                else: st.info("본인의 예약 내역이 없습니다.")
            else: st.info("데이터가 없습니다.")
        except: st.info("내역을 불러올 수 없습니다.")
