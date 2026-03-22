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

# 1. 페이지 설정
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
# 🔑 세션 및 설정
# =========================
if "session_key" not in st.session_state: st.session_state["session_key"] = str(uuid.uuid4())
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
if "user_id" not in st.session_state: st.session_state["user_id"] = ""
if "auth_manage" not in st.session_state: st.session_state["auth_manage"] = False

ADMIN_PASSWORD_MANAGE = "ua0952"
TIME_SLOTS = ["10:00 ~ 11:00", "11:00 ~ 12:00", "13:00 ~ 14:00", "14:00 ~ 15:00", "15:00 ~ 16:00", "16:00 ~ 17:00", "17:00 ~ 18:00"]
NIGHT_SLOTS = ["16:00 ~ 17:00", "17:00 ~ 18:00"]

# 📩 이메일 알림
def send_email_notification(content):
    try:
        sender = st.secrets["EMAIL_ADDRESS"]; password = st.secrets["EMAIL_PASSWORD"]; receiver = st.secrets["ADMIN_NOTIFY_EMAIL"]
        msg = MIMEText(content); msg["Subject"] = "📢 새로운 관람 예약 등록"; msg["From"] = sender; msg["To"] = receiver
        server = smtplib.SMTP("smtp.gmail.com", 587); server.starttls(); server.login(sender, password)
        server.sendmail(sender, receiver, msg.as_string()); server.quit()
    except: pass 

# 📊 구글 시트 연결
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

# --- 데이터 로드 ---
@st.cache_data(ttl=600) 
def load_full_data():
    try:
        sheets = ["1단지_매매","1단지_임대","2단지_매매","2단지_임대","3단지_매매","3단지_임대"]
        df_list = []
        for s in sheets:
            try:
                ws = sheet.worksheet(s); data = ws.get_all_values()
                if len(data) > 1:
                    df = pd.DataFrame(data[1:], columns=["NO.","분양구분","동","호수","타입","매물구분","매매가","월세","거래여부", "비고"])
                    df["단지"] = s.split("_")[0]; df["거래유형"] = s.split("_")[1]
                    for col in ["매매가", "월세"]: df[f"{col}_num"] = pd.to_numeric(df[col].str.replace(',', ''), errors='coerce').fillna(0)
                    df_list.append(df)
            except: continue
        user_ws = sheet.worksheet("사용자목록"); u_data = user_ws.get_all_values()
        user_dict = {str(row[0]).strip(): str(row[1]).strip() for row in u_data[1:] if len(row) >= 2}
        return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame(), user_dict
    except: return pd.DataFrame(), {}

df_total, user_dict = load_full_data()

# =========================
# 🔒 로그인 (기존 로직 유지)
# =========================
if not st.session_state.logged_in:
    st.title("🔒 EMS 로그인")
    with st.form("login"):
        u_id = st.text_input("ID(아이디)").strip(); u_pw = st.text_input("PW(비밀번호)", type="password").strip()
        if st.form_submit_button("로그인"):
            if u_id in user_dict and user_dict[u_id] == u_pw:
                st.session_state.logged_in = True; st.session_state.user_id = u_id; st.rerun()
            else: st.error("❌ 로그인 정보를 확인해주세요.")
    st.stop()

# =========================
# 🏠 메인 사이드바
# =========================
menu_options = ["📊 실시간 현황", "🔍 등록 매물 조회", "📅 세대관람 예약"]
if st.session_state.auth_manage: menu_options.append("⚙️관리자 모드")
with st.sidebar:
    st.success(f"👤 {st.session_state.user_id} 접속 중"); choice = st.radio("메뉴 이동", menu_options)
    if st.button("🔄 새로고침"): st.cache_data.clear(); st.rerun()
    if st.button("🔒 로그아웃"): st.session_state.clear(); st.rerun()

# =========================
# 📅 세대관람 예약 (핵심 수정 구역)
# =========================
if choice == "📅 세대관람 예약":
    st.title("📋 세대관람 예약 시스템")
    tab1, tab2 = st.tabs(["📝 예약 등록", "📊 단지별 예약 현황"])
    
    with tab1:
        res_dj = st.selectbox("관람 단지 선택", ["1단지", "2단지", "3단지"])
        r_date_val = st.date_input("방문 날짜 선택", date.today())
        t_val = st.selectbox("방문 시간 선택", TIME_SLOTS)
        
        # [수정] 야간 자동 분류 로직
        target_sheet_name = "야간_관람예약" if t_val in NIGHT_SLOTS else f"{res_dj}_관람예약"
        
        try:
            target_ws = sheet.worksheet(target_sheet_name); all_res = target_ws.get_all_values()
            # 정확한 컬럼명 '예약날짜'와 '예약시간' 사용
            col_names = ["예약날짜", "예약자", "중개업소", "관람세대수", "동", "호수", "타입", "예약시간", "비고"]
            if len(all_res) > 1:
                daily_df = pd.DataFrame(all_res[1:], columns=all_res[0])
                # 예약 인원 체크
                mask = (daily_df["예약날짜"] == r_date_val.strftime("%Y-%m-%d")) & (daily_df["예약시간"] == t_val)
                current_res_count = len(daily_df[mask])
            else: current_res_count = 0
        except: st.error(f"⚠️ '{target_sheet_name}' 시트 로드 실패. 시트 이름을 확인하세요."); st.stop()

        if current_res_count >= 3:
            st.error(f"🚫 해당 시간대({t_val})는 예약이 마감되었습니다. (3/3)"); can_reserve = False
        else:
            st.info(f"✅ 현재 {3 - current_res_count}자리 예약 가능합니다. (현재 {current_res_count}/3)"); st.progress(current_res_count / 3); can_reserve = True

        st.divider(); f_unit = df_total[df_total["단지"] == res_dj]; r_count = st.selectbox("관람 세대수", [1, 2]); r_items = []
        for i in range(r_count):
            with st.container(border=True):
                col1, col2 = st.columns(2); u_dongs = sorted(f_unit["동"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
                d_sel = col1.selectbox(f"동 ({i+1})", u_dongs, key=f"d_r_{i}"); u_hos = sorted(f_unit[f_unit["동"]==d_sel]["호수"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
                h_sel = col2.selectbox(f"호수 ({i+1})", u_hos, key=f"h_r_{i}"); match = f_unit[(f_unit["동"]==d_sel) & (f_unit["호수"]==h_sel)]
                if not match.empty: r_items.append({"동":d_sel, "호수":h_sel, "타입":match.iloc[0]['타입']})

        with st.form("reserve_form"):
            c1, c2 = st.columns(2); r_name = c1.text_input("(📝필수) 예약자 성함[실명]"); r_agency = c2.text_input("(📝필수) 중개업소 명칭")
            memo_input = st.text_area("(선택) 비고 [방문 인원 수 또는 특이사항]"); col_btn, col_tel = st.columns([1, 1]) 
            with col_btn:
                with st.container(border=True):
                    st.caption("⚠️확정 시 직접 취소가 불가능하오니 신중한 등록 부탁드립니다."); st.write(f"**{st.session_state.user_id}님 예약을 확정하시겠습니까?**")
                    submit_btn = st.form_submit_button("📅 예약 최종 확정", disabled=not can_reserve, use_container_width=True)
            with col_tel:
                with st.container(border=True):
                    tel_num = "062-511-9336"; st.write(f"**입주촉진센터: {tel_num}**")
                    st.link_button("☎️ 대표번호 문의연결", f"tel:{tel_num}", use_container_width=True)
            
            if submit_btn:
                if not r_name or not r_agency: st.error("성함과 업소명을 모두 입력해주세요.")
                elif can_reserve:
                    # [요청사항1] 동/호수 매칭 가독성 수정
                    combined_info = " / ".join([f"{it['동']}동 {it['호수']}호" for it in r_items])
                    types_str = ", ".join([s["타입"] for s in r_items])
                    # 시트 컬럼 순서: 예약날짜/예약자/중개업소/관람세대수/동/호수/타입/예약시간/비고
                    new_row = [r_date_val.strftime("%Y-%m-%d"), r_name, r_agency, f"{len(r_items)}세대", combined_info, "", types_str, t_val, memo_input]
                    target_ws.append_row(new_row)
                    st.success(f"✅ {r_name}님, 예약 완료!"); time.sleep(1.5); st.cache_data.clear(); st.rerun()

    with tab2:
        st.subheader("📋 단지별 실시간 예약 현황판")
        sel_dj_view = st.radio("조회 단지", ["1단지", "2단지", "3단지"], horizontal=True)
        view_date = st.date_input("조회 일자", date.today(), key="view_date")
        try:
            # 통합 조회 (일반+야간)
            ws_n = sheet.worksheet(f"{sel_dj_view}_관람예약"); d_n = ws_n.get_all_values()
            ws_y = sheet.worksheet("야간_관람예약"); d_y = ws_y.get_all_values()
            df_n = pd.DataFrame(d_n[1:], columns=d_n[0]) if len(d_n) > 1 else pd.DataFrame(columns=col_names)
            df_y = pd.DataFrame(d_y[1:], columns=d_y[0]) if len(d_y) > 1 else pd.DataFrame(columns=col_names)
            v_all = pd.concat([df_n, df_y], ignore_index=True)
            
            if not v_all.empty:
                v_daily = v_all[v_all["예약날짜"] == view_date.strftime("%Y-%m-%d")].copy()
                # [요청사항2] 예약시간 순으로 정렬
                v_daily['시간순서'] = v_daily['예약시간'].apply(lambda x: TIME_SLOTS.index(x) if x in TIME_SLOTS else 99)
                v_daily = v_daily.sort_values('시간순서').drop(columns=['시간순서'])
            else: v_daily = pd.DataFrame()

            # 시간 카드 표시
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
                st.dataframe(v_daily[["예약자", "관람세대수", "동", "예약시간"]].rename(columns={"동":"관람상세"}), use_container_width=True, hide_index=True)
            else: st.info("해당 날짜에 등록된 예약이 없습니다.")
        except Exception as e: st.error(f"현황판 로드 오류: {e}")


elif choice == "⚙️관리자 모드":
    st.title("⚙️ 매물 통합 관리")
    col1, col2, col3 = st.columns(3)
    edit_dj = col1.selectbox("수정 단지", ["1단지", "2단지", "3단지"])
    edit_dong = col2.text_input("동 입력")
    edit_ho = col3.text_input("호수 입력")
    if edit_dong and edit_ho:
        target_df = df_total[(df_total["단지"] == edit_dj) & (df_total["동"] == edit_dong) & (df_total["호수"] == edit_ho)]
        if not target_df.empty:
            curr = target_df.iloc[0]; old_sheet_name = f"{edit_dj}_{curr['거래유형']}"
            with st.form("edit_form"):
                st.markdown(f"### 📝 {edit_dong}동 {edit_ho}호 정보 수정")
                c1, c2, c3 = st.columns(3)
                options = ["매매", "전세", "월세"]
                new_gubun = c1.selectbox("매물구분", options, index=options.index(curr["매물구분"]) if curr["매물구분"] in options else 0)
                new_type = c2.text_input("타입", value=curr["타입"])
                new_status = c3.selectbox("거래상태", ["관람가능", "거래완료"], index=0 if curr["거래여부"] == "관람가능" else 1)
                c4, c5, c6 = st.columns(3)
                new_price_str = c4.text_input("매매가/보증금 (만원)", value=str(int(curr["매매가_num"])))
                new_monthly_str = c5.text_input("월세 (만원)", value=str(int(curr["월세_num"])))
                new_note = c6.text_input("비고", value=curr["비고"])
                if st.form_submit_button("💾 정보 업데이트 및 저장"):
                    try:
                        f_price = f"{int(new_price_str.replace(',','')):,}"; f_monthly = f"{int(new_monthly_str.replace(',','')):,}"
                        new_sheet_name = f"{edit_dj}_{'매매' if new_gubun == '매매' else '임대'}"
                        ws = sheet.worksheet(old_sheet_name); rows = ws.get_all_values()
                        idx = next((i+1 for i, r in enumerate(rows) if len(r)>3 and r[2]==edit_dong and r[3]==edit_ho), -1)
                        if idx != -1:
                            new_data = [rows[idx-1][0], rows[idx-1][1], edit_dong, edit_ho, new_type, new_gubun, f_price, f_monthly, new_status, new_note]
                            if old_sheet_name != new_sheet_name:
                                sheet.worksheet(new_sheet_name).append_row(new_data); ws.delete_rows(idx)
                            else: ws.update(f'E{idx}:J{idx}', [[new_type, new_gubun, f_price, f_monthly, new_status, new_note]])
                            st.success("✅ 완료!"); st.cache_data.clear(); st.rerun()
                    except: st.error("입력값을 확인하세요.")
        else: st.warning("🔍 매물을 찾을 수 없습니다.")
