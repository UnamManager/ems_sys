import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, datetime
import json

# 1. 페이지 설정 및 보안 강화 (CSV 다운로드 버튼 숨기기)
st.set_page_config(page_title="EMS 통합 관리 시스템", layout="wide")
st.markdown("""
    <style>
    [data-testid="stElementToolbar"] { display: none !important; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #f0f2f6; }
    .stDataFrame { border: 1px solid #exexex; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# =========================
# 🔑 세션 및 관리자 비번 설정
# =========================
ADMIN_PASSWORD_RES = "3090"      # 세대관람 예약용
ADMIN_PASSWORD_MANAGE = "ua0952"  # 매물 통합 관리용

if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "user_id" not in st.session_state: st.session_state.user_id = ""
if "auth_res" not in st.session_state: st.session_state.auth_res = False
if "auth_manage" not in st.session_state: st.session_state.auth_manage = False

# =========================
# 📊 구글 시트 연결 (캐시 적용)
# =========================
@st.cache_resource
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

client = get_gspread_client()
sheet = client.open("EMS")

# --- [최적화] 협력사 명부 로드 (0.1초 컷 로그인용) ---
@st.cache_data(ttl=600)
def get_user_dict():
    try:
        user_ws = sheet.worksheet("사용자목록")
        data = user_ws.get_all_values()
        # {ID: PW} 형태의 딕셔너리로 저장해서 검색 속도 극대화
        return {str(row[0]).strip(): str(row[1]).strip() for row in data[1:] if len(row) >= 2}
    except: return {}

# --- [최적화] 전체 매물 데이터 로드 ---
@st.cache_data(show_spinner="최신 매물 동기화 중...", ttl=300)
def load_all_data():
    sheets = ["1단지_매매","1단지_임대","2단지_매매","2단지_임대","3단지_매매","3단지_임대"]
    cols = ["NO.","분양구분","동","호수","타입","매물구분","매매가","월세","거래여부", "비고"]
    df_list = []
    for s in sheets:
        try:
            ws = sheet.worksheet(s)
            data = ws.get_all_values()
            if len(data) > 1:
                df = pd.DataFrame(data[1:], columns=cols)
                df["단지"] = s.split("_")[0]
                df["거래유형"] = s.split("_")[1]
                # 형의 기존 숫자 변환 로직 적용
                df["매매가_num"] = pd.to_numeric(df["매매가"].str.replace(',', ''), errors='coerce').fillna(0)
                df["월세_num"] = pd.to_numeric(df["월세"].str.replace(',', ''), errors='coerce').fillna(0)
                df["동_num"] = pd.to_numeric(df["동"], errors='coerce').fillna(0)
                df["호_num"] = pd.to_numeric(df["호수"], errors='coerce').fillna(0)
                df_list.append(df)
        except: continue
    
    if df_list:
        full_df = pd.concat(df_list, ignore_index=True)
        return full_df.sort_values(by=["단지", "동_num", "호_num"])
    return pd.DataFrame(columns=cols + ["단지", "거래유형"])

# 스타일 함수
def apply_final_style(df, columns):
    df_styled = df.copy()
    df_styled['매매가'] = df_styled['매매가_num']
    df_styled['월세'] = df_styled['월세_num']
    df_display = df_styled[columns].rename(columns={'매매가': '매매가/임대보증금 (만원)'})
    return df_display.style.applymap(
        lambda val: f'background-color: {"#d4edda" if val == "관람가능" else "#f8d7da" if val == "거래완료" else "white"}',
        subset=['거래여부']
    ).format({'매매가/임대보증금 (만원)': '{:,.0f}', '월세': '{:,.0f}'})

# =========================
# 🔒 로그인 화면
# =========================
if not st.session_state.logged_in:
    st.title("🔒 EMS 협력사 전용 시스템")
    user_dict = get_user_dict()
    with st.form("login_form"):
        u_id = st.text_input("협력사 아이디 (상호명)").strip()
        u_pw = st.text_input("비밀번호", type="password").strip()
        if st.form_submit_button("로그인"):
            if u_id in user_dict and user_dict[u_id] == u_pw:
                st.session_state.logged_in = True
                st.session_state.user_id = u_id
                st.rerun()
            else: st.error("❌ 아이디 또는 비밀번호가 일치하지 않습니다.")
    st.stop()

# =========================
# 🏠 메인 시스템 로드
# =========================
df_total = load_all_data()

with st.sidebar:
    st.markdown("### 🏢 EMS 관리 센터")
    st.success(f"👤 {st.session_state.user_id} 접속")
    
    # 메뉴 숨김 로직 (인증된 것만 리스트에 추가)
    menu_options = ["📊 실시간 매물 현황", "🔍 등록 매물 조회"]
    if st.session_state.auth_res: menu_options.append("📅 세대관람 예약")
    if st.session_state.auth_manage: menu_options.append("⚙️ 매물 통합 관리")
    
    choice = st.radio("메뉴 이동", menu_options)
    st.divider()
    
    # 비밀 통로 (Expander 내부에서 인증)
    with st.expander("🛠️ 시스템 설정"):
        admin_code = st.text_input("관리자 코드 입력", type="password")
        if admin_code == ADMIN_PASSWORD_RES:
            st.session_state.auth_res = True
            st.rerun()
        if admin_code == ADMIN_PASSWORD_MANAGE:
            st.session_state.auth_manage = True
            st.rerun()

    if st.button("🔄 데이터 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    if st.button("🚪 로그아웃", use_container_width=True):
        st.session_state.clear()
        st.rerun()

# --- 1. 실시간 매물 현황 ---
if choice == "📊 실시간 매물 현황":
    st.title("📊 실시간 매물 현황")
    c1, c2, c3 = st.columns(3)
    c1.metric("📌 전체 매물", f"{len(df_total)}개")
    c2.metric("✅ 거래완료", f"{len(df_total[df_total['거래여부'] == '거래완료'])}개")
    c3.metric("🏠 관람가능", f"{len(df_total[df_total['거래여부'] == '관람가능'])}개")
    st.divider()
    df_done = df_total[df_total["거래여부"] == "거래완료"].copy()
    if not df_done.empty:
        st.dataframe(apply_final_style(df_done, ["분양구분", "동", "호수", "타입", "매물구분", "매매가", "월세", "거래여부", "비고"]), use_container_width=True, hide_index=True)

# --- 2. 등록 매물 조회 ---
elif choice == "🔍 등록 매물 조회":
    st.title("🔍 등록 매물 조회")
    f1, f2, f3, f4 = st.columns(4)
    s_danji = f1.multiselect("단지", df_total["단지"].unique() if not df_total.empty else [])
    s_bunyang = f2.multiselect("분양구분", df_total["분양구분"].unique() if not df_total.empty else [])
    s_gubun = f3.multiselect("매물구분", df_total["매물구분"].unique() if not df_total.empty else [])
    s_type = f4.multiselect("타입", sorted(df_total["타입"].unique()) if not df_total.empty else [])
    
    st.markdown("---")
    c1, c2, _ = st.columns([1, 1, 2])
    search_dong = c1.text_input("🏢 동 검색 (숫자만)")
    search_ho = c2.text_input("🔑 호수 검색 (숫자만)")
    
    df_v = df_total.copy()
    if s_danji: df_v = df_v[df_v["단지"].isin(s_danji)]
    if s_bunyang: df_v = df_v[df_v["분양구분"].isin(s_bunyang)]
    if s_gubun: df_v = df_v[df_v["매물구분"].isin(s_gubun)]
    if s_type: df_v = df_v[df_v["타입"].isin(s_type)]
    if search_dong: df_v = df_v[df_v["동"] == search_dong]
    if search_ho: df_v = df_v[df_v["호수"] == search_ho]
    st.dataframe(apply_final_style(df_v, ["분양구분", "동", "호수", "타입", "매물구분", "매매가", "월세", "거래여부", "비고"]), use_container_width=True, hide_index=True)

# --- 3. 세대관람 예약 (형의 원본 로직) ---
elif choice == "📅 세대관람 예약":
    st.title("📅 세대관람 예약 관리")
    tab1, tab2 = st.tabs(["📅 예약 등록", "📊 예약 현황"])
    with tab1:
        st.subheader("📅 예약 등록")
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
                    r_items.append({"동":d_sel, "호수":h_sel, "타입":m_row['타입'], "상태":m_row['거래여부']})

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
                    target_ws_n = f"{res_dj}_관람예약" if int(t_val[:2]) < 16 else "야간_관람예약"
                    ws = sheet.worksheet(target_ws_n)
                    f_date = r_date.strftime("%Y-%m-%d")
                    rows = [[f_date, r_name, r_agency, f"{r_count}세대", s["동"], s["호수"], s["타입"], t_val, r_manager, memo_input] for s in r_items]
                    ws.append_rows(rows)
                    st.success("예약 완료!")
                    st.cache_data.clear()

    with tab2:
        v_dj = st.selectbox("조회 단지 선택", ["1단지", "2단지", "3단지", "야간"])
        try:
            ws_n = f"{v_dj}_관람예약" if v_dj != "야간" else "야간_관람예약"
            v_data = sheet.worksheet(ws_n).get_all_values()
            if len(v_data) > 1:
                df_c = pd.DataFrame(v_data[1:], columns=["날짜","예약자","중개업소","세대수","동","호수","타입","시간","동행매니저","비고"])
                st.dataframe(df_c, use_container_width=True, hide_index=True)
            else: st.info("예약 데이터가 없습니다.")
        except: st.error("데이터 로드 실패")

# --- 4. 매물 통합 관리 (형의 원본 로직) ---
elif choice == "⚙️ 매물 통합 관리":
    st.title("⚙️ 매물 통합 관리")
    col1, col2, col3 = st.columns(3)
    edit_dj = col1.selectbox("수정 단지", ["1단지", "2단지", "3단지"])
    edit_dong = col2.text_input("동 입력 (숫자)")
    edit_ho = col3.text_input("호수 입력 (숫자)")

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
                new_price_str = c4.text_input("가액 (만원)", value=str(int(curr["매매가_num"])))
                new_monthly_str = c5.text_input("월세 (만원)", value=str(int(curr["월세_num"])))
                new_note = c6.text_input("비고", value=curr["비고"])

                if st.form_submit_button("💾 정보 업데이트"):
                    try:
                        clean_price = int(new_price_str.replace(',', '').strip())
                        clean_monthly = int(new_monthly_str.replace(',', '').strip())
                        formatted_price = f"{clean_price:,}"
                        formatted_monthly = f"{clean_monthly:,}"
                        new_sheet_name = f"{edit_dj}_매매" if new_gubun == "매매" else f"{edit_dj}_임대"
                        
                        old_ws = sheet.worksheet(old_sheet_name)
                        all_rows = old_ws.get_all_values()
                        row_idx = -1
                        for i, r in enumerate(all_rows):
                            if len(r) > 3 and r[2] == edit_dong and r[3] == edit_ho:
                                row_idx = i + 1; break
                        
                        if row_idx != -1:
                            new_row_data = [all_rows[row_idx-1][0], all_rows[row_idx-1][1], edit_dong, edit_ho, new_type, new_gubun, formatted_price, formatted_monthly, new_status, new_note]
                            if old_sheet_name != new_sheet_name:
                                sheet.worksheet(new_sheet_name).append_row(new_row_data)
                                old_ws.delete_rows(row_idx)
                            else:
                                old_ws.update(f'E{row_idx}:J{row_idx}', [[new_type, new_gubun, formatted_price, formatted_monthly, new_status, new_note]])
                            st.success("✅ 처리 완료!")
                            st.cache_data.clear()
                            st.rerun()
                    except: st.error("입력값을 확인하세요.")
        else: st.warning("🔍 매물을 찾을 수 없습니다.")
