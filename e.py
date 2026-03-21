import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import json
import uuid

# 1. 페이지 설정
st.set_page_config(page_title="EMS 통합 관리 시스템", layout="wide")
st.markdown("""
    <style>
    [data-testid="stElementToolbar"] { display: none !important; }
    .stButton>button { width: 100%; height: 3em; border-radius: 8px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# =========================
# 🔑 세션 초기화 (session_key가 핵심)
# =========================
if "session_key" not in st.session_state:
    st.session_state.session_key = str(uuid.uuid4())
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "user_id" not in st.session_state: st.session_state.user_id = ""
if "auth_res" not in st.session_state: st.session_state.auth_res = False
if "auth_manage" not in st.session_state: st.session_state.auth_manage = False

ADMIN_PASSWORD_RES = "3090"
ADMIN_PASSWORD_MANAGE = "ua0952"

# =========================
# 📊 구글 시트 연결
# =========================
@st.cache_resource
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

client = get_gspread_client()
sheet = client.open("EMS")

# --- [강력 로직] 동시 접속 감시 및 세션 업데이트 ---
def sync_session(user_id, my_key):
    ws = sheet.worksheet("접속현황")
    data = ws.get_all_values()
    
    # 1. 현재 시트에 기록된 이 아이디의 최신 세션 키 확인
    db_key = ""
    row_idx = -1
    for i, row in enumerate(data):
        if row[0] == user_id:
            db_key = row[1]
            row_idx = i + 1
            break
    
    # 2. 내 키와 DB 키가 다르면 (누가 새로 로그인함) -> 차단
    if db_key and db_key != my_key:
        return False
    
    # 3. 로그인 중이라면 시간 업데이트 (생존 신고)
    if row_idx != -1:
        ws.update(f'C{row_idx}', [[datetime.now().strftime("%Y-%m-%d %H:%M:%S")]])
    else:
        ws.append_row([user_id, my_key, datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    return True

# --- 데이터 로드 ---
@st.cache_data(ttl=300)
def load_full_data():
    sheets = ["1단지_매매","1단지_임대","2단지_매매","2단지_임대","3단지_매매","3단지_임대"]
    df_list = []
    for s in sheets:
        try:
            ws = sheet.worksheet(s)
            data = ws.get_all_values()
            if len(data) > 1:
                df = pd.DataFrame(data[1:], columns=["NO.","분양구분","동","호수","타입","매물구분","매매가","월세","거래여부", "비고"])
                df["단지"] = s.split("_")[0]; df["거래유형"] = s.split("_")[1]
                for col in ["매매가", "월세", "동", "호수"]:
                    df[f"{col}_num"] = pd.to_numeric(df[col].str.replace(',', ''), errors='coerce').fillna(0)
                df_list.append(df)
        except: continue
    u_raw = sheet.worksheet("사용자목록").get_all_values()
    user_dict = {row[0].strip(): row[1].strip() for row in u_raw[1:] if len(row) >= 2}
    return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame(), user_dict

df_total, user_dict = load_full_data()

# =========================
# 🔒 로그인 및 실시간 세션 체크
# =========================
if not st.session_state.logged_in:
    st.title("🔒 EMS 협력사 로그인")
    with st.form("login"):
        u_id = st.text_input("아이디(상호명)").strip()
        u_pw = st.text_input("비밀번호", type="password").strip()
        if st.form_submit_button("로그인"):
            if u_id in user_dict and user_dict[u_id] == u_pw:
                # 로그인 성공 시 DB에 내 세션 키를 강제로 덮어씌움 (기존 접속자 밀어내기)
                ws_status = sheet.worksheet("접속현황")
                all_status = ws_status.get_all_values()
                exists = False
                for i, r in enumerate(all_status):
                    if r[0] == u_id:
                        ws_status.update(f'B{i+1}:C{i+1}', [[st.session_state.session_key, datetime.now().strftime("%H:%M:%S")]])
                        exists = True; break
                if not exists: ws_status.append_row([u_id, st.session_state.session_key, datetime.now().strftime("%H:%M:%S")])
                
                st.session_state.logged_in = True
                st.session_state.user_id = u_id
                st.rerun()
            else: st.error("❌ 정보를 확인해주세요.")
    st.stop()

# [무적의 중복 체크] 모든 페이지 동작 전에 실행
if not sync_session(st.session_state.user_id, st.session_state.session_key):
    st.error("🚨 다른 기기에서 로그인이 감지되어 이 세션은 종료되었습니다.")
    st.info("중복 로그인을 방지하기 위해 한 아이디당 하나의 브라우저만 허용됩니다.")
    if st.button("내 세션으로 다시 접속하기 (다른 기기 튕겨냄)"):
        # 내 키로 DB를 갱신해버림
        ws_status = sheet.worksheet("접속현황")
        all_status = ws_status.get_all_values()
        for i, r in enumerate(all_status):
            if r[0] == st.session_state.user_id:
                ws_status.update(f'B{i+1}', [[st.session_state.session_key]])
                break
        st.rerun()
    st.stop()

# =========================
# 🏠 메인 사이드바 (메뉴 은닉 적용)
# =========================
menu_options = ["📊 실시간 매물 현황", "🔍 등록 매물 조회"]
if st.session_state.auth_res: menu_options.append("📅 세대관람 예약")
if st.session_state.auth_manage: menu_options.append("⚙️ 매물 통합 관리")

with st.sidebar:
    st.success(f"👤 {st.session_state.user_id} 접속 중")
    choice = st.radio("메뉴 이동", menu_options)
    st.divider()
    with st.expander("🛠️ 관리자 인증"):
        pw_in = st.text_input("코드 입력", type="password")
        if pw_in == ADMIN_PASSWORD_RES and not st.session_state.auth_res:
            st.session_state.auth_res = True; st.rerun()
        if pw_in == ADMIN_PASSWORD_MANAGE and not st.session_state.auth_manage:
            st.session_state.auth_manage = True; st.rerun()
    if st.button("🔄 새로고침"): st.cache_data.clear(); st.rerun()
    if st.button("🚪 로그아웃"): st.session_state.clear(); st.rerun()

# --- 공통 스타일 함수 ---
def apply_style(df):
    return df.style.applymap(
        lambda x: "background-color: #d4edda" if x == "관람가능" else "background-color: #f8d7da" if x == "거래완료" else "",
        subset=["거래여부"]
    )

# =========================
# 📋 페이지별 로직
# =========================
if choice == "📊 실시간 매물 현황":
    st.title("📊 실시간 매물 현황")
    c1, c2, c3 = st.columns(3)
    c1.metric("📌 전체", f"{len(df_total)}개")
    c2.metric("✅ 거래완료", f"{len(df_total[df_total['거래여부']=='거래완료'])}개")
    c3.metric("🏠 관람가능", f"{len(df_total[df_total['거래여부']=='관람가능'])}개")
    st.divider()
    df_done = df_total[df_total["거래여부"] == "거래완료"].copy()
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
    st.dataframe(apply_style(df_v[["분양구분", "동", "호수", "타입", "매물구분", "매매가", "월세", "거래여부", "비고"]]), use_container_width=True, hide_index=True)

elif choice == "📅 세대관람 예약":
    st.title("📅 세대관람 예약 관리")
    tab1, tab2 = st.tabs(["📅 예약 등록", "📊 예약 현황"])
    with tab1:
        st.subheader("📅 세대관람 예약 등록")
        res_dj = st.selectbox("예약 단지 선택", ["1단지", "2단지", "3단지"])
        f_unit = df_total[df_total["단지"] == res_dj]
        r_count = st.selectbox("관람 세대수 선택", [1, 2, 3])
        r_items = []
        for i in range(r_count):
            with st.container(border=True):
                col1, col2 = st.columns(2)
                u_dongs = sorted(f_unit["동"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
                d_sel = col1.selectbox("동", u_dongs, key=f"d_r_{i}")
                u_hos = sorted(f_unit[f_unit["동"]==d_sel]["호수"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
                h_sel = col2.selectbox("호수", u_hos, key=f"h_r_{i}")
                match = f_unit[(f_unit["동"]==d_sel) & (f_unit["호수"]==h_sel)]
                if not match.empty:
                    m_row = match.iloc[0]
                    st.markdown(f"✅ 타입: **{m_row['타입']}** | 상태: **{m_row['거래여부']}**")
                    r_items.append({"동":d_sel, "호수":h_sel, "타입":m_row['타입']})

        time_options = [f"{h:02d}:00 ~ {h:02d}:45" for h in range(9, 21) if h not in [12, 17, 20]]
        with st.form("reserve_form"):
            c1, c2 = st.columns(2)
            r_date = c1.date_input("방문 날짜", date.today())
            r_name = c2.text_input("예약자 성함")
            r_agency = st.text_input("중개업소 명칭")
            r_manager = st.text_input("동행 매니저")
            t_val = st.selectbox("방문 시간", time_options)
            memo_input = st.text_input("상세 메모")
            if st.form_submit_button("📅 예약 최종 확정"):
                if not r_name: st.error("성함을 입력해주세요.")
                else:
                    target_ws_name = f"{res_dj}_관람예약" if int(t_val[:2]) < 16 else "야간_관람예약"
                    ws = sheet.worksheet(target_ws_name)
                    rows = [[r_date.strftime("%Y-%m-%d"), r_name, r_agency, f"{r_count}세대", s["동"], s["호수"], s["타입"], t_val, r_manager, memo_input] for s in r_items]
                    ws.append_rows(rows)
                    st.success("✅ 예약 완료!"); st.cache_data.clear()

    with tab2:
        v_dj = st.selectbox("조회 단지 선택", ["1단지", "2단지", "3단지", "야간"])
        try:
            ws_n = f"{v_dj}_관람예약" if v_dj != "야간" else "야간_관람예약"
            v_data = sheet.worksheet(ws_n).get_all_values()
            if len(v_data) > 1:
                st.dataframe(pd.DataFrame(v_data[1:], columns=["날짜","예약자","중개업소","세대수","동","호수","타입","시간","동행매니저","비고"]), use_container_width=True, hide_index=True)
            else: st.info("예약 데이터가 없습니다.")
        except: st.error("데이터 로드 실패")

elif choice == "⚙️ 매물 통합 관리":
    st.title("⚙️ 매물 통합 관리")
    col1, col2, col3 = st.columns(3)
    edit_dj = col1.selectbox("수정 단지", ["1단지", "2단지", "3단지"])
    edit_dong = col2.text_input("동 입력 (숫자만)")
    edit_ho = col3.text_input("호수 입력 (숫자만)")

    if edit_dong and edit_ho:
        target_df = df_total[(df_total["단지"] == edit_dj) & (df_total["동"] == edit_dong) & (df_total["호수"] == edit_ho)]
        if not target_df.empty:
            curr = target_df.iloc[0]
            old_sheet_name = f"{edit_dj}_{curr['거래유형']}"
            with st.form("edit_form"):
                st.markdown(f"### 📝 {edit_dong}동 {edit_ho}호 정보 수정")
                c1, c2, c3 = st.columns(3)
                options = ["매매", "전세", "월세"]
                default_idx = options.index(curr["매물구분"]) if curr["매물구분"] in options else 0
                new_gubun = c1.selectbox("매물구분", options, index=default_idx)
                new_type = c2.text_input("타입", value=curr["타입"])
                new_status = c3.selectbox("거래상태", ["관람가능", "거래완료"], index=0 if curr["거래여부"] == "관람가능" else 1)
                
                c4, c5, c6 = st.columns(3)
                new_price_str = c4.text_input("매매가/보증금 (만원)", value=str(int(curr["매매가_num"])))
                new_monthly_str = c5.text_input("월세 (만원)", value=str(int(curr["월세_num"])))
                new_note = c6.text_input("비고", value=curr["비고"])

                if st.form_submit_button("💾 정보 업데이트 및 저장"):
                    try:
                        f_price = f"{int(new_price_str.replace(',','')):,}"
                        f_monthly = f"{int(new_monthly_str.replace(',','')):,}"
                        new_sheet_name = f"{edit_dj}_{'매매' if new_gubun == '매매' else '임대'}"
                        
                        ws = sheet.worksheet(old_sheet_name)
                        rows = ws.get_all_values()
                        idx = next((i+1 for i, r in enumerate(rows) if len(r)>3 and r[2]==edit_dong and r[3]==edit_ho), -1)
                        
                        if idx != -1:
                            new_data = [rows[idx-1][0], rows[idx-1][1], edit_dong, edit_ho, new_type, new_gubun, f_price, f_monthly, new_status, new_note]
                            if old_sheet_name != new_sheet_name:
                                sheet.worksheet(new_sheet_name).append_row(new_data)
                                ws.delete_rows(idx)
                                st.success(f"🚀 {new_sheet_name} 이동 완료!")
                            else:
                                ws.update(f'E{idx}:J{idx}', [[new_type, new_gubun, f_price, f_monthly, new_status, new_note]])
                                st.success("✅ 수정 완료!")
                            st.cache_data.clear(); st.rerun()
                    except: st.error("입력값을 확인하세요.")
        else: st.warning("🔍 매물을 찾을 수 없습니다.")
