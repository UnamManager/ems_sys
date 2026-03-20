import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, datetime
import json

# 1. 페이지 설정 및 CSV 다운로드 버튼 숨기기 (CSS 강제 주입)
st.set_page_config(page_title="EMS 통합 관리 시스템", layout="wide")

# 🚫 [보안] 데이터프레임 우측 상단 다운로드 아이콘 숨기기
st.markdown("""
    <style>
    [data-testid="stElementToolbar"] {
        display: none !important;
    }
    </style>
    """, unsafe_allow_html=True)

# =========================
# 🔐 보안 설정
# =========================
if "admin_auth" not in st.session_state:
    st.session_state.admin_auth = False

ADMIN_PASSWORD = "3090"

# =========================
# 📊 데이터 로드 및 시트 연결
# =========================
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

try:
    sheet = client.open("EMS")
except gspread.exceptions.SpreadsheetNotFound:
    st.error("🚨 구글 시트 'EMS' 파일을 찾을 수 없습니다.")
    st.stop()

@st.cache_data(show_spinner="데이터 동기화 중...", ttl=300)
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
                # 숫자 변환
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

df_total = load_all_data()

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
# 🏠 사이드바 메뉴
# =========================
with st.sidebar:
    st.markdown("### 🏢 EMS 관리 센터")
    choice = st.radio("메뉴 이동", ["📊 실시간 매물 현황", "🔍 등록 매물 조회", "📅 세대관람 예약", "⚙️ 매물 통합 관리"])
    st.divider()
    if st.button("🔄 데이터 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- 1번 메뉴: 실시간 매물 현황 ---
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
    else: st.info("완료 매물 없음")

# --- 2번 메뉴: 등록 매물 조회 ---
elif choice == "🔍 등록 매물 조회":
    st.title("🔍 등록 매물 조회")
    f1, f2, f3, f4 = st.columns(4)
    s_danji = f1.multiselect("단지", df_total["단지"].unique())
    s_bunyang = f2.multiselect("분양구분", df_total["분양구분"].unique())
    s_gubun = f3.multiselect("매물구분", df_total["매물구분"].unique())
    s_type = f4.multiselect("타입", sorted(df_total["타입"].unique()))
    
    st.markdown("---")
    c1, c2, _ = st.columns([1, 1, 2])
    search_dong = c1.text_input("🏢 동 검색")
    search_ho = c2.text_input("🔑 호수 검색")
    
    df_v = df_total.copy()
    if s_danji: df_v = df_v[df_v["단지"].isin(s_danji)]
    if s_bunyang: df_v = df_v[df_v["분양구분"].isin(s_bunyang)]
    if s_gubun: df_v = df_v[df_v["매물구분"].isin(s_gubun)]
    if s_type: df_v = df_v[df_v["타입"].isin(s_type)]
    if search_dong: df_v = df_v[df_v["동"] == search_dong]
    if search_ho: df_v = df_v[df_v["호수"] == search_ho]
    
    st.dataframe(apply_final_style(df_v, ["분양구분", "동", "호수", "타입", "매물구분", "매매가", "월세", "거래여부", "비고"]), use_container_width=True, hide_index=True)

# --- 3번 메뉴: 세대관람 예약 (기존 관리자 모드 로직) ---
elif choice == "📅 세대관람 예약":
    if not st.session_state.admin_auth:
        pwd = st.text_input("관리자 인증", type="password")
        if pwd == ADMIN_PASSWORD:
            st.session_state.admin_auth = True
            st.rerun()
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

# --- 4번 메뉴: 매물 통합 관리 (시트 이동 로직 추가) ---
elif choice == "⚙️ 매물 통합 관리":
    if not st.session_state.admin_auth:
        pwd = st.text_input("관리자 인증", type="password")
        if pwd == ADMIN_PASSWORD:
            st.session_state.admin_auth = True
            st.rerun()
        st.stop()

    st.title("⚙️ 매물 통합 관리 (정보 수정 및 시트 이동)")
    col1, col2, col3 = st.columns(3)
    edit_dj = col1.selectbox("수정 단지", ["1단지", "2단지", "3단지"])
    edit_dong = col2.text_input("동 입력 (숫자만)")
    edit_ho = col3.text_input("호수 입력 (숫자만)")

    if edit_dong and edit_ho:
        target_df = df_total[(df_total["단지"] == edit_dj) & (df_total["동"] == edit_dong) & (df_total["호수"] == edit_ho)]
        
        if not target_df.empty:
            curr = target_df.iloc[0]
            # 현재 이 매물이 살고 있는 원래 시트 이름 (예: 1단지_매매)
            old_sheet_name = f"{edit_dj}_{curr['거래유형']}"
            
            with st.form("edit_form"):
                st.markdown(f"### 📝 {edit_dong}동 {edit_ho}호 정보 수정")
                c1, c2, c3 = st.columns(3)
                
                options = ["매매", "전세", "월세"]
                default_idx = options.index(curr["매물구분"]) if curr["매물구분"] in options else 0
                new_gubun = c1.selectbox("매물구분", options, index=default_idx)
                
                new_type = c2.text_input("타입", value=curr["타입"])
                new_status = c3.selectbox("거래상태", ["관람가능", "거래완료"], index=0 if curr["거래여부"] == "관람가능" else 1)
                
                st.divider()
                c4, c5, c6 = st.columns(3)
                new_price_str = c4.text_input("매매가/보증금 (만원)", value=str(int(curr["매매가_num"])))
                new_monthly_str = c5.text_input("월세 (만원)", value=str(int(curr["월세_num"])))
                new_note = c6.text_input("비고", value=curr["비고"])

                if st.form_submit_button("💾 수정 및 시트 이동 저장"):
                    try:
                        clean_price = int(new_price_str.replace(',', '').strip())
                        clean_monthly = int(new_monthly_str.replace(',', '').strip())
                        formatted_price = f"{clean_price:,}"
                        formatted_monthly = f"{clean_monthly:,}"
                        
                        # 1. 새 시트 결정 로직 (매매면 '매매', 전세/월세면 '임대')
                        new_type_suffix = "매매" if new_gubun == "매매" else "임대"
                        new_sheet_name = f"{edit_dj}_{new_type_suffix}"
                        
                        # 원래 있던 시트에서 해당 행 찾기
                        old_ws = sheet.worksheet(old_sheet_name)
                        all_rows = old_ws.get_all_values()
                        row_idx = -1
                        for i, r in enumerate(all_rows):
                            if len(r) > 3 and r[2] == edit_dong and r[3] == edit_ho:
                                row_idx = i + 1; break
                        
                        if row_idx != -1:
                            # 새 데이터 행 구성 (NO는 기존 거 유지)
                            new_row_data = [
                                all_rows[row_idx-1][0], # NO.
                                all_rows[row_idx-1][1], # 분양구분
                                edit_dong, 
                                edit_ho, 
                                new_type, 
                                new_gubun, 
                                formatted_price, 
                                formatted_monthly, 
                                new_status, 
                                new_note
                            ]
                            
                            # 시트가 바뀌는 경우 (예: 매매 -> 전세)
                            if old_sheet_name != new_sheet_name:
                                new_ws = sheet.worksheet(new_sheet_name)
                                new_ws.append_row(new_row_data) # 새 시트에 추가
                                old_ws.delete_rows(row_idx)    # 기존 시트에서 삭제
                                st.success(f"🚀 매물이 {new_sheet_name} 시트로 이동 및 수정되었습니다!")
                            else:
                                # 시트가 안 바뀌면 그냥 해당 행만 업데이트
                                old_ws.update(f'E{row_idx}:J{row_idx}', [[new_type, new_gubun, formatted_price, formatted_monthly, new_status, new_note]])
                                st.success("✅ 정보가 수정되었습니다!")
                            
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error("데이터를 찾을 수 없습니다.")
                    except Exception as e:
                        st.error(f"오류 발생: {e}")
        else:
            st.warning("🔍 매물을 찾을 수 없습니다.")
