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

ADMIN_PASSWORD_MANAGE = "ua0952"
TIME_SLOTS = ["10:00 ~ 10:45", "11:00 ~ 11:45", "13:00 ~ 13:45", "14:00 ~ 14:45", "15:00 ~ 15:45", "16:00 ~ 16:45", "17:00 ~ 17:45"]
NIGHT_SLOTS = ["16:00 ~ 16:45", "17:00 ~ 17:45"]
COL_NAMES = ["예약날짜", "예약자", "중개업소", "관람세대수", "동", "호수", "타입", "예약시간", "비고"]

# =========================
# 📩 이메일 알림 및 구글 API 연결 (최적화)
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

# --- [실시간 세션 감시 로직] ---
def sync_session(user_id, my_key):
    if not user_id: return True
    try:
        ws = sheet.worksheet("접속현황")
        data = ws.get_all_values()
        for i, row in enumerate(data):
            if row[0] == user_id:
                if row[1] != "" and row[1] != my_key: return False
                # 갱신 시 API 부하를 줄이기 위해 시간만 업데이트 (update는 최소한으로)
                return True
        return True
    except: return True

# --- [데이터 통합 로드 (캐시 적용으로 트래픽 절감)] ---
@st.cache_data(ttl=300) # 5분간 데이터 유지
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
            except: continue
        
        user_ws = sheet.worksheet("사용자목록")
        u_data = user_ws.get_all_values()
        user_dict = {str(row[0]).strip(): str(row[1]).strip() for row in u_data[1:] if len(row) >= 2}
        return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame(), user_dict
    except: return pd.DataFrame(), {}

df_total, user_dict = load_full_data()

# =========================
# 🔒 로그인 시스템 (중복 접속 방지 포함)
# =========================
if not st.session_state.logged_in:
    st.title("🔒 EMS 통합 관리 로그인")
    with st.form("login_form"):
        u_id = st.text_input("아이디(ID)").strip()
        u_pw = st.text_input("비밀번호(PW)", type="password").strip()
        if st.form_submit_button("시스템 접속"):
            if u_id in user_dict and user_dict[u_id] == u_pw:
                # 접속 기록 (오류나도 무시하고 진행하여 로그인 차단 방지)
                try:
                    ws_log = sheet.worksheet("접속현황")
                    ws_log.append_row([u_id, st.session_state.session_key, datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                except: pass
                st.session_state.logged_in = True
                st.session_state.user_id = u_id
                st.rerun()
            else:
                st.error("❌ 아이디 또는 비밀번호가 일치하지 않습니다.")
    st.stop()

# =========================
# 🏠 사이드바 및 메뉴
# =========================
menu_options = ["📊 실시간 현황", "🔍 등록 매물 조회", "📅 세대관람 예약"]
if st.session_state.auth_manage: menu_options.append("⚙️관리자 모드")

with st.sidebar:
    st.success(f"👤 {st.session_state.user_id} 접속 중")
    choice = st.radio("메뉴 이동", menu_options)
    st.divider()
    if not st.session_state.auth_manage:
        with st.expander("🛠️ 관리자 인증"):
            pw_in = st.text_input("관리자 코드 입력", type="password")
            if pw_in == ADMIN_PASSWORD_MANAGE: st.session_state.auth_manage = True; st.rerun()
    
    if st.button("🔄 새로고침"): st.cache_data.clear(); st.rerun()
    if st.button("🔒 로그아웃"):
        try:
            ws_status = sheet.worksheet("접속현황"); all_status = ws_status.get_all_values()
            for i, r in enumerate(all_status):
                if r[0] == st.session_state.user_id: ws_status.update(f'B{i+1}:C{i+1}', [["", ""]]); break
        except: pass
        st.session_state.clear(); st.rerun()

def apply_style(df):
    return df.style.applymap(lambda x: "background-color: #d4edda" if x == "관람가능" else "background-color: #f8d7da" if x == "거래완료" else "", subset=["거래여부"])

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
            target_ws = sheet.worksheet(target_sheet_name); all_res = target_ws.get_all_values()
            if len(all_res) > 1:
                daily_df = pd.DataFrame(all_res[1:], columns=all_res[0])
                mask = (daily_df["예약날짜"] == r_date_val.strftime("%Y-%m-%d")) & (daily_df["예약시간"] == t_val)
                current_res_count = len(daily_df[mask])
            else: current_res_count = 0
            
            if current_res_count >= 3:
                st.error(f"🚫 해당 시간대({t_val})는 예약이 마감되었습니다. (3/3)"); can_reserve = False
            else:
                st.info(f"✅ 현재 {3 - current_res_count}자리 예약 가능합니다. (현재 {current_res_count}/3)"); st.progress(current_res_count / 3); can_reserve = True
        except: st.error("시트 연결 오류"); can_reserve = False

        st.divider(); f_unit = df_total[df_total["단지"] == res_dj]; r_count = st.selectbox("관람 세대수", [1, 2])
        r_items = []
        for i in range(r_count):
            with st.container(border=True):
                col1, col2 = st.columns(2)
                u_dongs = sorted(f_unit["동"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
                d_sel = col1.selectbox(f"동 ({i+1})", u_dongs, key=f"d_r_{i}")
                u_hos = sorted(f_unit[f_unit["동"]==d_sel]["호수"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
                h_sel = col2.selectbox(f"호수 ({i+1})", u_hos, key=f"h_r_{i}")
                match = f_unit[(f_unit["동"]==d_sel) & (f_unit["호수"]==h_sel)]
                if not match.empty: r_items.append({"동":d_sel, "호수":h_sel, "타입":match.iloc[0]['타입']})

        with st.form("reserve_form"):
            c1, c2 = st.columns(2); r_name = c1.text_input("(📝필수) 예약자 성함[실명]"); r_agency = c2.text_input("(📝필수) 중개업소 명칭")
            memo_input = st.text_area("(선택) 비고 [방문 인원 수 또는 특이사항]")
            col_btn, col_tel = st.columns([1, 1]) 
            with col_btn:
                with st.container(border=True):
                    st.caption("⚠️확정 시 직접 취소가 불가능하오니 신중한 등록 부탁드립니다."); st.write(f"**{st.session_state.user_id}님 예약을 확정하시겠습니까?**")
                    submit_btn = st.form_submit_button("📅 예약 최종 확정", disabled=not can_reserve, use_container_width=True)
            with col_tel:
                with st.container(border=True):
                    tel_num = "062-511-9336"; st.caption("⚠️취소/변경이 필요한 경우 미리 사전에 연락 부탁드립니다."); st.write(f"**입주촉진센터: {tel_num}**")
                    st.link_button("☎️ 대표번호 문의연결", f"tel:{tel_num}", use_container_width=True)
            
            if submit_btn:
                if not r_name or not r_agency: st.error("성함과 업소명을 모두 입력해주세요.")
                elif can_reserve:
                    combined_info = " / ".join([f"{it['동']}동 {it['호수']}호" for it in r_items])
                    types_str = ", ".join([s["타입"] for s in r_items])
                    new_row = [r_date_val.strftime("%Y-%m-%d"), r_name, r_agency, f"{len(r_items)}세대", combined_info, "", types_str, t_val, memo_input]
                    target_ws.append_row(new_row)
                    # 이메일 알림 발송
                    send_email_notification(f"예약자: {r_name}\n업소: {r_agency}\n단지: {res_dj}\n세대: {combined_info}\n시간: {t_val}")
                    st.success(f"✅ {r_name}님, 예약 완료!"); time.sleep(1.5); st.cache_data.clear(); st.rerun()

    with tab2:
        st.subheader("📋 단지별 예약 현황")
        sel_dj_view = st.radio("조회 단지", ["1단지", "2단지", "3단지"], horizontal=True)
        view_date = st.date_input("조회 일자", date.today(), key="view_date")
        try:
            ws_n = sheet.worksheet(f"{sel_dj_view}_관람예약"); d_n = ws_n.get_all_values()
            ws_y = sheet.worksheet("야간_관람예약"); d_y = ws_y.get_all_values()
            df_n = pd.DataFrame(d_n[1:], columns=d_n[0]) if len(d_n) > 1 else pd.DataFrame(columns=COL_NAMES)
            df_y = pd.DataFrame(d_y[1:], columns=d_y[0]) if len(d_y) > 1 else pd.DataFrame(columns=COL_NAMES)
            v_all = pd.concat([df_n, df_y], ignore_index=True)
            
            if not v_all.empty:
                v_daily = v_all[v_all["예약날짜"] == view_date.strftime("%Y-%m-%d")].copy()
                v_daily['예약시간'] = pd.Categorical(v_daily['예약시간'], categories=TIME_SLOTS, ordered=True)
                v_daily = v_daily.sort_values('예약시간')
                
                rows_to_show = [TIME_SLOTS[i:i + 3] for i in range(0, len(TIME_SLOTS), 3)]
                for row in rows_to_show:
                    cols = st.columns(3)
                    for idx, slot in enumerate(row):
                        count = len(v_daily[v_daily["예약시간"] == slot]) if not v_daily.empty else 0
                        with cols[idx]:
                            color = "#ff4b4b" if count >= 3 else "#28a745"; bg = "#fff1f1" if count >= 3 else "#f8fff9"
                            st.markdown(f"""<div class="time-card" style="border: 1px solid {color}; background-color: {bg};">
                                <p>{slot.split(' ~ ')[0]}</p><strong style="color: {color};">{'❌ 마감' if count>=3 else f'{count}/3 (여유)'}</strong></div>""", unsafe_allow_html=True)
                st.divider()
                if not v_daily.empty:
                    v_daily["예약자"] = v_daily["예약자"].apply(lambda n: n[0] + "*" * (len(n)-1) if len(n) > 1 else n)
                    st.dataframe(v_daily[["예약시간", "예약자", "관람세대수", "동"]].rename(columns={"동":"관람상세"}), use_container_width=True, hide_index=True)
                else: st.info("해당 날짜에 등록된 예약이 없습니다.")
        except: pass

# =========================
# ⚙️ [페이지 4] 관리자 마스터 모드
# =========================
elif choice == "⚙️ 관리자 모드":
    st.title("⚙️ 관리자 컨트롤 타워")
    adm_tab1, adm_tab2, adm_tab3 = st.tabs(["🏠 거래상태 변경", "📅 전체 예약 마스터 조회", "✂️ 예약 데이터 수정/삭제"])

    with adm_tab1:
        st.subheader("📍 매물 상태 직접 업데이트")
        c1, c2, c3 = st.columns(3)
        a_dj = c1.selectbox("단지", ["1단지", "2단지", "3단지"], key="a_dj")
        a_dong = c2.text_input("동", key="a_dong")
        a_ho = c3.text_input("호수", key="a_ho")
        if a_dong and a_ho:
            target = df_total[(df_total["단지"] == a_dj) & (df_total["동"] == a_dong) & (df_total["호수"] == a_ho)]
            if not target.empty:
                curr = target.iloc[0]
                with st.form("adm_status"):
                    new_s = st.selectbox("거래 상태", ["관람가능", "거래완료"], index=0 if curr["거래여부"]=="관람가능" else 1)
                    new_n = st.text_input("비고", value=curr["비고"])
                    if st.form_submit_button("상태 변경 저장"):
                        ws = sheet.worksheet(f"{a_dj}_{curr['거래유형']}")
                        rows = ws.get_all_values()
                        idx = next((i+1 for i, r in enumerate(rows) if len(r)>3 and r[2]==a_dong and r[3]==a_ho), -1)
                        if idx != -1:
                            ws.update(f'I{idx}:J{idx}', [[new_s, new_n]])
                            st.success("변경되었습니다!"); st.cache_data.clear(); time.sleep(1); st.rerun()
            else: st.error("매물을 찾을 수 없습니다.")

    with adm_tab2:
        st.subheader("📅 전 단지 통합 예약 조회")
        adm_date = st.date_input("조회 날짜 선택", date.today(), key="adm_date")
        if st.button("통합 명단 불러오기"):
            all_master = []
            for s in ["1단지_관람예약", "2단지_관람예약", "3단지_관람예약", "야간_관람예약"]:
                try:
                    data = sheet.worksheet(s).get_all_values()
                    if len(data) > 1:
                        tmp = pd.DataFrame(data[1:], columns=data[0])
                        tmp["단지"] = s.replace("_관람예약", "")
                        all_master.append(tmp)
                except: continue
            if all_master:
                res_df = pd.concat(all_master)
                st.dataframe(res_df[res_df["예약날짜"] == adm_date.strftime("%Y-%m-%d")].sort_values("예약시간"), use_container_width=True, hide_index=True)
            else: st.info("내역 없음")

    with adm_tab3:
        st.subheader("✂️ 예약 정보 수정 및 삭제")
        col1, col2 = st.columns(2)
        d_date = col1.date_input("날짜", date.today(), key="d_date")
        d_sheet = col2.selectbox("시트", ["1단지_관람예약", "2단지_관람예약", "3단지_관람예약", "야간_관람예약"])
        try:
            ws_mod = sheet.worksheet(d_sheet)
            rows_mod = ws_mod.get_all_values()
            if len(rows_mod) > 1:
                df_mod = pd.DataFrame(rows_mod[1:], columns=rows_mod[0])
                day_mod = df_mod[df_mod["예약날짜"] == d_date.strftime("%Y-%m-%d")]
                if not day_mod.empty:
                    sel = st.selectbox("대상 선택", [f"{i+2}행: [{r['예약시간']}] {r['예약자']}" for i, r in day_mod.iterrows()])
                    row_idx = int(sel.split("행:")[0])
                    with st.form("mod_form"):
                        m_name = st.text_input("성함", value=rows_mod[row_idx-1][1])
                        m_agency = st.text_input("업소", value=rows_mod[row_idx-1][2])
                        m_time = st.selectbox("시간", TIME_SLOTS, index=TIME_SLOTS.index(rows_mod[row_idx-1][7]) if rows_mod[row_idx-1][7] in TIME_SLOTS else 0)
                        if st.form_submit_button("저장"):
                            ws_mod.update(f'B{row_idx}:C{row_idx}', [[m_name, m_agency]])
                            ws_mod.update(f'H{row_idx}', [[m_time]])
                            st.success("수정 완료"); st.cache_data.clear(); time.sleep(1); st.rerun()
                        if st.form_submit_button("🗑️ 삭제", type="primary"):
                            ws_mod.delete_rows(row_idx)
                            st.success("삭제 완료"); st.cache_data.clear(); time.sleep(1); st.rerun()
        except: st.error("조회 실패")
