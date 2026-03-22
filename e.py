import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, date
import json
import uuid
import time
import smtplib
from email.mime.text import MIMEText
import streamlit_javascript as st_js


# 1. 페이지 설정
st.set_page_config(page_title="EMS 통합 관리 시스템", layout="wide")
st.markdown("""
    <style>
    [data-testid="stElementToolbar"] { display: none !important; }
    .stButton>button { width: 100%; height: 3em; border-radius: 8px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# =========================
# 🔑 세션 초기화
# =========================
if "session_key" not in st.session_state:
    st.session_state.session_key = str(uuid.uuid4())
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "user_id" not in st.session_state: st.session_state.user_id = ""
if "auth_manage" not in st.session_state: st.session_state.auth_manage = False

ADMIN_PASSWORD_MANAGE = "ua0952"

# =========================
# 📩 이메일 알림 시스템
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

# =========================
# 📊 구글 시트 연결 (최적화 버전)
# =========================
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

# --- [실시간 세션 감시 함수] ---
def sync_session(user_id, my_key):
    try:
        ws = sheet.worksheet("접속현황")
        data = ws.get_all_values()
        for i, row in enumerate(data):
            if row[0] == user_id:
                if row[1] != "" and row[1] != my_key:
                    return False
                ws.update(f'C{i+1}', [[datetime.now().strftime("%Y-%m-%d %H:%M:%S")]])
                return True
        return True
    except: return True

# --- 데이터 로드 (API 호출 최소화) ---
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
            except: continue
            
        user_ws = sheet.worksheet("사용자목록")
        u_data = user_ws.get_all_values()
        user_dict = {str(row[0]).strip(): str(row[1]).strip() for row in u_data[1:] if len(row) >= 2}
        
        return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame(), user_dict
    except: return pd.DataFrame(), {}

df_total, user_dict = load_full_data()

# =========================
# 🔒 로그인 및 중복 체크
# =========================
if not st.session_state.logged_in:
    st.title("🔒 EMS 로그인")
    with st.form("login"):
        u_id = st.text_input("ID(아이디)").strip()
        u_pw = st.text_input("PW(비밀번호)", type="password").strip()
        login_btn = st.form_submit_button("로그인")
        
        if login_btn:
            if u_id in user_dict and user_dict[u_id] == u_pw:
                ws_status = sheet.worksheet("접속현황")
                all_status = ws_status.get_all_values()
                target_row = -1; current_db_key = ""
                for i, r in enumerate(all_status):
                    if r[0] == u_id:
                        target_row = i + 1; current_db_key = r[1].strip(); break
                
                if current_db_key != "" and current_db_key != st.session_state.session_key:
                    st.error("🔒 현재 다른 기기에서 접속 중인 계정입니다.  EMS 보안 정책상 중복 접속은 제한됩니다.")
                    st.session_state.pending_user = u_id
                else:
                    if target_row != -1:
                        ws_status.update(f'B{target_row}:C{target_row}', [[st.session_state.session_key, datetime.now().strftime("%H:%M:%S")]])
                    else:
                        ws_status.append_row([u_id, st.session_state.session_key, datetime.now().strftime("%H:%M:%S")])
                    st.session_state.logged_in = True; st.session_state.user_id = u_id; st.rerun()
            else: st.error("❌ 로그인 정보를 확인해주세요.")
            
    if "pending_user" in st.session_state:
        if st.button(f"🔑 '{st.session_state.pending_user}' 님의 기존 접속을 종료하고 \n현재 기기에서 EMS 서비스를 시작합니다."):
            ws_status = sheet.worksheet("접속현황")
            all_status = ws_status.get_all_values()
            for i, r in enumerate(all_status):
                if r[0] == st.session_state.pending_user:
                    ws_status.update(f'B{i+1}:C{i+1}', [[st.session_state.session_key, datetime.now().strftime("%H:%M:%S")]])
                    break
            st.session_state.logged_in = True; st.session_state.user_id = st.session_state.pending_user
            del st.session_state.pending_user; st.rerun()
    st.stop()

if not sync_session(st.session_state.user_id, st.session_state.session_key):
    st.error("🚨 다른 사용자의 접속이 감지되어 종료되었습니다."); st.session_state.clear(); st.stop()

# =========================
# 🏠 메인 사이드바
# =========================
menu_options = ["📊 실시간 현황", "🔍 등록 매물 조회", "📅 세대관람 예약"]
if st.session_state.auth_manage: menu_options.append("⚙️관리자 모드")

with st.sidebar:
    st.success(f"👤 {st.session_state.user_id} 접속 중")
    choice = st.radio("메뉴 이동", menu_options)
    st.divider()
    with st.expander("🛠️ 관리자 인증"):
        pw_in = st.text_input("관리자 코드 입력", type="password")
        if pw_in == ADMIN_PASSWORD_MANAGE and not st.session_state.auth_manage:
            st.session_state.auth_manage = True
            st.rerun()
    if st.button("🔄 새로고침"): st.cache_data.clear(); st.rerun()

def apply_style(df):
    return df.style.applymap(
        lambda x: "background-color: #d4edda" if x == "관람가능" else "background-color: #f8d7da" if x == "거래완료" else "",
        subset=["거래여부"]
    )

if choice == "📊 실시간 현황":
    st.title("📊 실시간 현황")
    c1, c2, c3 = st.columns(3)
    c1.metric("📌 전체", f"{len(df_total)}개")
    c2.metric("✅ 거래완료", f"{len(df_total[df_total['거래여부']=='거래완료'])}개")
    c3.metric("🏠 관람가능", f"{len(df_total[df_total['거래여부']=='관람가능'])}개")
    st.divider()
    
    # [수정] 거래완료 매물 데이터 추출 및 블라인드 처리
    df_done = df_total[df_total["거래여부"] == "거래완료"].copy()
    
    # '매매가', '월세', '비고' 컬럼 블라인드 처리
    for col in ["매매가", "월세", "비고"]:
        if col in df_done.columns:
            df_done[col] = "🔒 거래완료"
            
    st.dataframe(apply_style(df_done[["분양구분", "동", "호수", "타입", "매물구분", "매매가", "월세", "거래여부", "비고"]]), use_container_width=True, hide_index=True)

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
    
    # [수정] 조회 결과 중 '거래완료'인 행의 특정 컬럼 블라인드 처리
    mask = df_v["거래여부"] == "거래완료"
    for col in ["매매가", "월세", "비고"]:
        if col in df_v.columns:
            df_v.loc[mask, col] = "🔒 거래완료"
            
    st.dataframe(apply_style(df_v[["분양구분", "동", "호수", "타입", "매물구분", "매매가", "월세", "거래여부", "비고"]]), use_container_width=True, hide_index=True)

elif choice == "📅 세대관람 예약":
    st.title("📅 세대관람 예약")
    
    time_slots = ["10:00 ~ 11:00", "11:00 ~ 12:00", "13:00 ~ 14:00", "14:00 ~ 15:00", "15:00 ~ 16:00", "16:00 ~ 17:00", "17:00 ~ 18:00"]
    tab1, tab2 = st.tabs(["📝 예약 등록", "📊 단지별 예약 현황"])
    
    with tab1:
        res_dj = st.selectbox("관람 단지 선택", ["1단지", "2단지", "3단지"])
        
        # --- [중요] target_ws를 여기서 미리 정의해야 에러가 안 나! ---
        try:
            target_ws = sheet.worksheet(f"{res_dj}_관람예약")
        except Exception as e:
            st.error(f"시트 연결 오류: {e}")
            st.stop() # 시트 못 찾으면 여기서 멈춤
        # ------------------------------------------------------

        r_date_val = st.date_input("방문 날짜 선택", date.today())
        current_res_count = len(daily_res[daily_res["시간"] == t_val]) if not daily_res.empty else 0
        
        if current_res_count >= 3:
            st.error(f"🚫 해당 시간대({t_val})는 예약이 마감되었습니다. (3/3)")
            can_reserve = False
        else:
            st.info(f"✅ 현재 {3 - current_res_count}자리 예약 가능합니다. (현재 {current_res_count}/3)")
            st.progress(current_res_count / 3)
            can_reserve = True

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
            r_name = c1.text_input("(*필수*) 예약자 성함[실명])")
            r_agency = c2.text_input("(*필수*) 중개업소 명칭")
            memo_input = st.text_area("(*선택*) 비고 [방문 인원 수 또는 특이사항]")
            
# --- [수정] 좌우 대칭형 레이아웃 ---
            col_btn, col_tel = st.columns([1, 1]) 

            with col_btn:
                with st.container(border=True):
                    st.caption("⚠️ 확정 후 직접 취소가 불가하오니 신중히 등록 바랍니다.")
                    st.write(f"**{st.session_state.user_id}님의 세대관람 예약을 확정하시겠습니까?**")
                    # 아래에 버튼 배치
                    submit_btn = st.form_submit_button("📅 예약 최종 확정", 
                                                    disabled=not can_reserve, 
                                                    use_container_width=True)
            with col_tel:
                with st.container(border=True):
                    tel_num = "062-511-9336" # 실제 번호로 수정!
                    st.caption("📞 취소/변경 문의")
                    st.write(f"**입주촉진센터: {tel_num}**")
                    # 아래에 버튼 배치
                    st.link_button("☎️ 전화 연결", f"tel:{tel_num}", use_container_width=True)
            
            if submit_btn:
                if not r_name or not r_agency: 
                    st.error("성함과 업소명을 모두 입력해주세요.")
                elif can_reserve:
                    # --- [수정 포인트 2] 세대수 상관없이 시트에 1줄(Row)만 저장 ---
                    # 동, 호수, 타입을 쉼표(,)로 합쳐서 한 칸에 몰아넣기
                    dongs_str = ", ".join([s["동"] for s in r_items])
                    hos_str = ", ".join([s["호수"] for s in r_items])
                    types_str = ", ".join([s["타입"] for s in r_items])
                    
                    # 이제 rows가 아니라 row 하나만 만듦
                    new_row = [
                        r_date_val.strftime("%Y-%m-%d"), 
                        r_name, 
                        r_agency, 
                        f"{r_count}세대", 
                        dongs_str, 
                        hos_str, 
                        types_str, 
                        t_val, 
                        memo_input
                    ]
                    # 딱 1줄만 추가 (이래야 예약 자리가 1개만 참)
                    target_ws.append_row(new_row)
                    
                    # 2. 메일 발송 로직 (상세 리스트 포함)
                    unit_info_str = "".join([f"- {idx+1}번째 세대: {item['동']}동 {item['호수']}호 ({item['타입']}타입)\n" for idx, item in enumerate(r_items)])
                    m_content = f"📢 [EMS] 새로운 예약 확정\n■ 단지: {res_dj}\n■ 일시: {r_date_val} ({t_val})\n■ 예약자: {r_name}({r_agency})\n[상세]\n{unit_info_str}"
                    send_email_notification(m_content)
                    
                    # 3. 확정 메시지 노출 (2초 대기)
                    st.success(f"✅ {r_name}님, 예약이 성공적으로 확정되었습니다.")
                    import time
                    time.sleep(2) 
                    
                    st.cache_data.clear()
                    st.rerun()

    with tab2:
        st.subheader("📅 단지별 실시간 예약 현황판")
        sel_dj_view = st.radio("조회 단지", ["1단지", "2단지", "3단지"], horizontal=True)
        view_date = st.date_input("조회 일자", date.today(), key="view_date")
        
        try:
            v_ws = sheet.worksheet(f"{sel_dj_view}_관람예약")
            v_data = pd.DataFrame(v_ws.get_all_values()[1:], columns=["날짜","예약자","중개업소","세대수","동","호수","타입","시간","비고"])
            v_daily = v_data[v_data["날짜"] == view_date.strftime("%Y-%m-%d")].copy()
            
            if not v_daily.empty: 
                v_daily = v_daily.sort_values(by="시간")
            
            # 성함 마스킹
            def mask_name(n): return n[0] + "*" * (len(n)-1) if len(n) > 1 else n
            if not v_daily.empty: 
                v_daily["예약자"] = v_daily["예약자"].apply(mask_name)
            
            # --- [UI 개선 섹션] 시간대별 카드형 현황 ---
            st.write("---")
            # 모바일 가로폭을 고려해 2열 혹은 3열로 배치 (화면 크기에 따라 자동 조절됨)
            rows_to_show = [time_slots[i:i + 3] for i in range(0, len(time_slots), 3)]
            
            for row in rows_to_show:
                cols = st.columns(3)
                for idx, slot in enumerate(row):
                    count = len(v_daily[v_daily["시간"] == slot])
                    with cols[idx]:
                        # 시간 표시 예쁘게 다듬기 (10:00 ~ 11:00 -> AM 10:00)
                        start_time = slot.split(" ~ ")[0]
                        hr = int(start_time.split(":")[0])
                        ampm = "AM" if hr < 12 else "PM"
                        display_time = f"{ampm} {start_time}"
                        
                        # 카드 스타일 테두리 및 컬러 적용
                        if count >= 3:
                            st.markdown(f"""
                                <div style="border: 1px solid #ff4b4b; border-radius: 10px; padding: 10px; text-align: center; background-color: #fff1f1;">
                                    <p style="margin: 0; font-size: 0.8rem; color: #666;">{display_time}</p>
                                    <strong style="color: #ff4b4b;">❌ 마감</strong>
                                </div>
                            """, unsafe_allow_with_html=True)
                        else:
                            remains = 3 - count
                            st.markdown(f"""
                                <div style="border: 1px solid #28a745; border-radius: 10px; padding: 10px; text-align: center; background-color: #f8fff9;">
                                    <p style="margin: 0; font-size: 0.8rem; color: #666;">{display_time}</p>
                                    <strong style="color: #28a745;">{count}/3 (여유)</strong>
                                </div>
                            """, unsafe_allow_with_html=True)
                st.write("") # 줄간격
            
            st.divider()
            # 하단 상세 리스트는 깔끔한 표로 유지
            if len(v_daily) > 0:
                st.markdown("##### 📍 상세 예약 리스트")
                st.dataframe(v_daily[["예약자", "중개업소", "세대수", "시간"]], use_container_width=True, hide_index=True)
            else: 
                st.info("해당 날짜에 등록된 예약이 없습니다.")
        except: 
            st.error("현황 데이터를 불러오는 중 오류가 발생했습니다.")
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
