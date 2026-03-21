import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, datetime
import json

# 1. 페이지 설정 및 보안
st.set_page_config(page_title="EMS 통합 관리 시스템", layout="wide")
st.markdown("""
    <style>
    [data-testid="stElementToolbar"] { display: none !important; }
    </style>
    """, unsafe_allow_html=True)

# =========================
# 🔑 세션 상태 초기화
# =========================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_id" not in st.session_state:
    st.session_state.user_id = ""
if "auth_res" not in st.session_state:
    st.session_state.auth_res = False
if "auth_manage" not in st.session_state:
    st.session_state.auth_manage = False

ADMIN_PASSWORD_RES = "3090"
ADMIN_PASSWORD_MANAGE = "5050"

# =========================
# 📊 구글 시트 연결 및 데이터 로드
# =========================
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

try:
    sheet = client.open("EMS")
except Exception as e:
    st.error(f"🚨 구글 시트 연결 실패: {e}")
    st.stop()

# 협력사 명부 로드 및 전처리
@st.cache_data(ttl=300)
def get_user_list():
    try:
        user_ws = sheet.worksheet("사용자목록")
        df = pd.DataFrame(user_ws.get_all_records())
        # 데이터 전처리: 모든 값을 문자열로 바꾸고 앞뒤 공백 제거
        df['ID'] = df['ID'].astype(str).str.strip()
        df['PW'] = df['PW'].astype(str).str.strip()
        return df
    except Exception as e:
        st.error(f"⚠️ '사용자목록' 시트를 읽을 수 없습니다: {e}")
        return pd.DataFrame(columns=["ID", "PW"])

df_users = get_user_list()

# =========================
# 🔒 로그인 화면 (필터링 강화)
# =========================
if not st.session_state.logged_in:
    st.title("🔒 EMS 협력사 전용 시스템")
    st.info("등록된 협력 중개업소 아이디와 비밀번호를 입력하세요.")
    
    with st.form("login_form"):
        u_id = st.text_input("협력사 아이디 (상호명)").strip()
        u_pw = st.text_input("비밀번호", type="password").strip()
        
        if st.form_submit_button("로그인"):
            if not df_users.empty:
                # 입력값과 시트 데이터 비교 (둘 다 문자열로 처리)
                match = df_users[(df_users["ID"] == u_id) & (df_users["PW"] == u_pw)]
                
                if not match.empty:
                    st.session_state.logged_in = True
                    st.session_state.user_id = u_id
                    st.rerun()
                else:
                    st.error("❌ 아이디 또는 비밀번호가 일치하지 않습니다.")
                    # 디버깅용 메시지 (개발 완료 후 삭제 가능)
                    st.write(f"현재 등록된 업체 수: {len(df_users)}개")
            else:
                st.error("사용자 목록 데이터가 비어있습니다. 시트를 확인하세요.")
    st.stop()

# =========================
# 🏠 메인 시스템 시작
# =========================

@st.cache_data(show_spinner="매물 동기화 중...", ttl=300)
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
                df["매매가_num"] = pd.to_numeric(df["매매가"].str.replace(',', ''), errors='coerce').fillna(0)
                df["월세_num"] = pd.to_numeric(df["월세"].str.replace(',', ''), errors='coerce').fillna(0)
                df_list.append(df)
        except: continue
    return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()

df_total = load_all_data()

def apply_final_style(df, columns):
    df_styled = df.copy()
    df_styled['매매가'] = df_styled['매매가_num']
    df_styled['월세'] = df_styled['월세_num']
    df_display = df_styled[columns].rename(columns={'매매가': '매매가/임대보증금 (만원)'})
    return df_display.style.applymap(
        lambda val: f'background-color: {"#d4edda" if val == "관람가능" else "#f8d7da" if val == "거래완료" else "white"}',
        subset=['거래여부']
    ).format({'매매가/임대보증금 (만원)': '{:,.0f}', '월세': '{:,.0f}'})

# 사이드바 설정
with st.sidebar:
    st.success(f"👤 {st.session_state.user_id} 접속")
    
    # 메뉴 노출 로직
    menu_options = ["📊 실시간 매물 현황", "🔍 등록 매물 조회"]
    if st.session_state.auth_res: menu_options.append("📅 세대관람 예약")
    if st.session_state.auth_manage: menu_options.append("⚙️ 매물 통합 관리")
    
    choice = st.radio("메뉴 이동", menu_options)
    
    st.divider()
    # 숨겨진 관리자 입구
    with st.expander("🛠️ 시스템 설정"):
        admin_code = st.text_input("코드 입력", type="password")
        if admin_code == ADMIN_PASSWORD_RES:
            st.session_state.auth_res = True
            st.rerun()
        if admin_code == ADMIN_PASSWORD_MANAGE:
            st.session_state.auth_manage = True
            st.rerun()
            
    if st.button("로그아웃"):
        st.session_state.clear()
        st.rerun()

# --- 1. 실시간 매물 현황 ---
if choice == "📊 실시간 매물 현황":
    st.title("📊 실시간 매물 현황")
    c1, c2, c3 = st.columns(3)
    c1.metric("📌 전체", f"{len(df_total)}개")
    c2.metric("✅ 완료", f"{len(df_total[df_total['거래여부']=='거래완료'])}개")
    c3.metric("🏠 가능", f"{len(df_total[df_total['거래여부']=='관람가능'])}개")
    st.divider()
    df_done = df_total[df_total["거래여부"]=="거래완료"]
    st.dataframe(apply_final_style(df_done, ["분양구분","동","호수","타입","매물구분","매매가","월세","거래여부","비고"]), use_container_width=True, hide_index=True)

# --- 2. 등록 매물 조회 ---
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
    st.dataframe(apply_final_style(df_v, ["분양구분","동","호수","타입","매물구분","매매가","월세","거래여부","비고"]), use_container_width=True, hide_index=True)

# --- 3. 세대관람 예약 (숨김 메뉴) ---
elif choice == "📅 세대관람 예약":
    st.title("📅 세대관람 예약 시스템")
    # 형이 가지고 있는 예약 시스템 코드 로직을 여기에 넣으면 돼!
    st.success("인증 완료: 예약 시스템 접근 가능")

# --- 4. 매물 통합 관리 (숨김 메뉴) ---
elif choice == "⚙️ 매물 통합 관리":
    st.title("⚙️ 매물 통합 관리")
    col1, col2, col3 = st.columns(3)
    edit_dj = col1.selectbox("수정 단지", ["1단지", "2단지", "3단지"])
    edit_dong = col2.text_input("동")
    edit_ho = col3.text_input("호")

    if edit_dong and edit_ho:
        target = df_total[(df_total["단지"]==edit_dj) & (df_total["동"]==edit_dong) & (df_total["호수"]==edit_ho)]
        if not target.empty:
            curr = target.iloc[0]
            with st.form("edit_form"):
                st.markdown(f"### 📝 {edit_dong}동 {edit_ho}호 정보 수정")
                c1, c2, c3 = st.columns(3)
                new_gubun = c1.selectbox("매물구분", ["매매","전세","월세"], index=["매매","전세","월세"].index(curr["매물구분"]) if curr["매물구분"] in ["매매","전세","월세"] else 0)
                new_type = c2.text_input("타입", value=curr["타입"])
                new_status = c3.selectbox("상태", ["관람가능","거래완료"], index=0 if curr["거래여부"]=="관람가능" else 1)
                
                c4, c5, c6 = st.columns(3)
                new_p = c4.text_input("가격(만원)", value=str(int(curr["매매가_num"])))
                new_m = c5.text_input("월세(만원)", value=str(int(curr["월세_num"])))
                new_note = c6.text_input("비고", value=curr["비고"])

                if st.form_submit_button("💾 정보 업데이트 및 시트 이동"):
                    try:
                        f_p, f_m = f"{int(new_p.replace(',','')):,}", f"{int(new_m.replace(',','')):,}"
                        old_sn = f"{edit_dj}_{curr['거래유형']}"
                        new_sn = f"{edit_dj}_매매" if new_gubun=="매매" else f"{edit_dj}_임대"
                        
                        old_ws = sheet.worksheet(old_sn)
                        rows = old_ws.get_all_values()
                        idx = next(i+1 for i,r in enumerate(rows) if len(r)>3 and r[2]==edit_dong and r[3]==edit_ho)
                        
                        # 데이터 업데이트 로직
                        new_row_data = [rows[idx-1][0], rows[idx-1][1], edit_dong, edit_ho, new_type, new_gubun, f_p, f_m, new_status, new_note]
                        
                        if old_sn != new_sn:
                            sheet.worksheet(new_sn).append_row(new_row_data)
                            old_ws.delete_rows(idx)
                            st.success(f"🚚 {new_sn} 시트로 이동 완료!")
                        else:
                            old_ws.update(f'E{idx}:J{idx}', [[new_type, new_gubun, f_p, f_m, new_status, new_note]])
                            st.success("✅ 정보 수정 완료!")
                        
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e: st.error(f"오류 발생: {e}")
