import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, datetime
import json

# 1. 페이지 설정 및 최적화
st.set_page_config(page_title="EMS 통합 관리 시스템", layout="wide")
st.markdown("""
    <style>
    [data-testid="stElementToolbar"] { display: none !important; }
    .stButton>button { width: 100%; height: 3em; }
    </style>
    """, unsafe_allow_html=True)

# =========================
# 🔑 세션 상태 및 설정
# =========================
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "user_id" not in st.session_state: st.session_state.user_id = ""
if "auth_res" not in st.session_state: st.session_state.auth_res = False
if "auth_manage" not in st.session_state: st.session_state.auth_manage = False

ADMIN_PASSWORD_RES = "3090"      
ADMIN_PASSWORD_MANAGE = "ua0952"  

# =========================
# 📊 구글 시트 연결 및 데이터 로드 (최적화 핵심)
# =========================
@st.cache_resource
def get_gspread_client():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"시트 연결 실패: {e}")
        return None

client = get_gspread_client()

# [중요] 시트 전체 데이터를 한 번에 가져와서 메모리에 저장 (API 호출 최소화)
@st.cache_data(ttl=600)
def load_full_system_data():
    if not client: return None, {}
    try:
        sh = client.open("EMS")
        # 1. 사용자 목록 로드
        user_ws = sh.worksheet("사용자목록")
        u_raw = user_ws.get_all_values()
        user_dict = {str(row[0]).strip(): str(row[1]).strip() for row in u_raw[1:] if len(row) >= 2}
        
        # 2. 매물 데이터 통합 로드
        sheets = ["1단지_매매","1단지_임대","2단지_매매","2단지_임대","3단지_매매","3단지_임대"]
        cols = ["NO.","분양구분","동","호수","타입","매물구분","매매가","월세","거래여부", "비고"]
        df_list = []
        for s in sheets:
            ws = sh.worksheet(s)
            data = ws.get_all_values()
            if len(data) > 1:
                df = pd.DataFrame(data[1:], columns=cols)
                df["단지"] = s.split("_")[0]
                df["거래유형"] = s.split("_")[1]
                df["매매가_num"] = pd.to_numeric(df["매매가"].str.replace(',', ''), errors='coerce').fillna(0)
                df["월세_num"] = pd.to_numeric(df["월세"].str.replace(',', ''), errors='coerce').fillna(0)
                df["동_num"] = pd.to_numeric(df["동"], errors='coerce').fillna(0)
                df["호_num"] = pd.to_numeric(df["호수"], errors='coerce').fillna(0)
                df_list.append(df)
        
        full_df = pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()
        if not full_df.empty:
            full_df = full_df.sort_values(by=["단지", "동_num", "호_num"])
            
        return full_df, user_dict
    except Exception as e:
        st.error(f"데이터 로드 에러: {e}")
        return pd.DataFrame(), {}

# 데이터 실행
df_total, user_dict = load_full_system_data()

# =========================
# 🔒 로그인 로직
# =========================
if not st.session_state.logged_in:
    st.title("🔒 EMS 협력사 시스템")
    with st.form("login"):
        u_id = st.text_input("아이디(상호)").strip()
        u_pw = st.text_input("비밀번호", type="password").strip()
        if st.form_submit_button("로그인"):
            if u_id in user_dict and user_dict[u_id] == u_pw:
                st.session_state.logged_in = True
                st.session_state.user_id = u_id
                st.rerun()
            else: st.error("❌ 정보를 확인해주세요.")
    st.stop()

# =========================
# 🏠 메인 메뉴 설정 (버그 원천 차단)
# =========================
menu_options = ["📊 실시간 매물 현황", "🔍 등록 매물 조회"]
if st.session_state.auth_res: menu_options.append("📅 세대관람 예약")
if st.session_state.auth_manage: menu_options.append("⚙️ 매물 통합 관리")

with st.sidebar:
    st.success(f"👤 {st.session_state.user_id}님")
    choice = st.radio("메뉴 이동", menu_options)
    
    with st.expander("🛠️ 시스템 인증"):
        code = st.text_input("관리자 코드", type="password")
        if code == ADMIN_PASSWORD_RES and not st.session_state.auth_res:
            st.session_state.auth_res = True
            st.rerun()
        elif code == ADMIN_PASSWORD_MANAGE and not st.session_state.auth_manage:
            st.session_state.auth_manage = True
            st.rerun()
            
    if st.button("🔄 새로고침"):
        st.cache_data.clear()
        st.rerun()
    if st.button("🚪 로그아웃"):
        st.session_state.clear()
        st.rerun()

# --- 헬퍼 함수 ---
def show_styled_df(df):
    cols_to_show = ["분양구분","동","호수","타입","매물구분","매매가","월세","거래여부","비고"]
    st.dataframe(df[cols_to_show], use_container_width=True, hide_index=True)

# =========================
# 📋 페이지별 콘텐츠
# =========================
if choice == "📊 실시간 매물 현황":
    st.title("📊 실시간 현황")
    c1, c2, c3 = st.columns(3)
    c1.metric("📌 전체", f"{len(df_total)}개")
    c2.metric("✅ 완료", f"{len(df_total[df_total['거래여부']=='거래완료'])}개")
    c3.metric("🏠 가능", f"{len(df_total[df_total['거래여부']=='관람가능'])}개")
    st.divider()
    show_styled_df(df_total[df_total["거래여부"]=="거래완료"])

elif choice == "🔍 등록 매물 조회":
    st.title("🔍 매물 조회")
    f1, f2, f3 = st.columns(3)
    danji = f1.multiselect("단지", df_total["단지"].unique())
    bunyang = f2.multiselect("분양구분", df_total["분양구분"].unique())
    gubun = f3.multiselect("매물구분", df_total["매물구분"].unique())
    
    d1, d2 = st.columns(2)
    s_dong = d1.text_input("🏢 동")
    s_ho = d2.text_input("🔑 호수")
    
    res = df_total.copy()
    if danji: res = res[res["단지"].isin(danji)]
    if bunyang: res = res[res["분양구분"].isin(bunyang)]
    if gubun: res = res[res["매물구분"].isin(gubun)]
    if s_dong: res = res[res["동"] == s_dong]
    if s_ho: res = res[res["호수"] == s_ho]
    show_styled_df(res)

elif choice == "📅 세대관람 예약":
    if not st.session_state.auth_res:
        pwd = st.text_input("📅 예약 관리자 인증", type="password")
        if pwd == ADMIN_PASSWORD_RES:
            st.session_state.auth_res = True
            st.rerun()
        elif pwd: st.error("비밀번호가 틀렸습니다.")
        st.stop()
    
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
                    target_ws = f"{res_dj}_관람예약" if int(t_val[:2]) < 16 else "야간_관람예약"
                    ws = sheet.worksheet(target_ws)
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

elif choice == "⚙️ 매물 통합 관리":
    if not st.session_state.auth_manage:
        pwd = st.text_input("⚙️ 통합 관리자 인증", type="password")
        if pwd == ADMIN_PASSWORD_MANAGE:
            st.session_state.auth_manage = True
            st.rerun()
        elif pwd: st.error("비밀번호가 틀렸습니다.")
        st.stop()

    st.title("⚙️ 매물 통합 관리 (정보 수정 및 시트 자동 이사)")
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
                        clean_price = int(new_price_str.replace(',', '').strip())
                        clean_monthly = int(new_monthly_str.replace(',', '').strip())
                        formatted_price = f"{clean_price:,}"
                        formatted_monthly = f"{clean_monthly:,}"
                        
                        # 새 시트 결정
                        new_type_suffix = "매매" if new_gubun == "매매" else "임대"
                        new_sheet_name = f"{edit_dj}_{new_type_suffix}"
                        
                        old_ws = sheet.worksheet(old_sheet_name)
                        all_rows = old_ws.get_all_values()
                        row_idx = -1
                        for i, r in enumerate(all_rows):
                            if len(r) > 3 and r[2] == edit_dong and r[3] == edit_ho:
                                row_idx = i + 1; break
                        
                        if row_idx != -1:
                            new_row_data = [all_rows[row_idx-1][0], all_rows[row_idx-1][1], edit_dong, edit_ho, new_type, new_gubun, formatted_price, formatted_monthly, new_status, new_note]
                            
                            if old_sheet_name != new_sheet_name:
                                new_ws = sheet.worksheet(new_sheet_name)
                                new_ws.append_row(new_row_data)
                                old_ws.delete_rows(row_idx)
                                st.success(f"🚀 {new_sheet_name} 시트로 이동 완료!")
                            else:
                                old_ws.update(f'E{row_idx}:J{row_idx}', [[new_type, new_gubun, formatted_price, formatted_monthly, new_status, new_note]])
                                st.success("✅ 정보 수정 완료!")
                            
                            st.cache_data.clear()
                            st.rerun()
                    except: st.error("숫자 입력값을 확인해주세요.")
        else: st.warning("🔍 매물을 찾을 수 없습니다.")
