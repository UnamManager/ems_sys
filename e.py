import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import json

# 1. 페이지 설정
st.set_page_config(page_title="EMS 통합 관리 시스템", layout="wide")

# =========================
# 🔑 세션 초기화 (재접속 지원)
# =========================
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "user_id" not in st.session_state: st.session_state.user_id = ""

# 브라우저 탭별 고유 ID (이건 창 닫으면 바뀌지만, 로그인 시점에 시트와 대조용으로 씀)
if "temp_dev_id" not in st.session_state:
    import random
    st.session_state.temp_dev_id = f"dev_{random.randint(1000, 9999)}"

# =========================
# 📊 구글 시트 및 데이터 로드 (생략 없이 통합)
# =========================
@st.cache_resource
def get_gspread_client():
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
    return gspread.authorize(creds)

client = get_gspread_client()
sheet = client.open("EMS")

# --- [개선된 기기 체크 로직] ---
def login_logic(user_id, my_temp_id):
    try:
        ws = sheet.worksheet("접속현황")
        data = ws.get_all_values()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        for i, row in enumerate(data):
            if i == 0: continue
            if row[0] == user_id:
                # 기기1, 기기2, 마지막 시간
                r = row + [""] * (4 - len(row))
                dev1, dev2 = r[1].strip(), r[2].strip()
                
                # [재접속 허용 핵심] 
                # 1. 내가 이미 등록된 기기 중 하나라면? -> 시간만 업데이트하고 통과
                if my_temp_id == dev1 or my_temp_id == dev2:
                    ws.update(f'D{i+1}', [[now_str]])
                    return True, ""
                
                # 2. 빈 자리가 있다면? -> 등록하고 통과
                if not dev1:
                    ws.update(f'B{i+1}:D{i+1}', [[my_temp_id, dev2, now_str]])
                    return True, ""
                if not dev2:
                    ws.update(f'C{i+1}:D{i+1}', [[my_temp_id, now_str]])
                    return True, ""
                
                # 3. 자리가 꽉 찼다면? (이게 형이 겪은 문제)
                # 협력사가 "이전에 썼던 기기"라고 간주하고 가장 오래된 기록을 덮어씌울지, 
                # 아니면 마지막 활동 시간을 보고 30분 지났으면 밀어낼지 결정
                last_time = datetime.strptime(r[3], "%Y-%m-%d %H:%M:%S")
                if datetime.now() - last_time > timedelta(minutes=10): # 10분만 지나도 재접속 허용
                    ws.update(f'B{i+1}:D{i+1}', [[my_temp_id, dev2, now_str]])
                    return True, ""
                
                return False, "이미 다른 기기 2대에서 사용 중입니다. 10분 후 다시 시도하세요."
        
        # 목록에 없으면 신규 등록
        ws.append_row([user_id, my_temp_id, "", now_str])
        return True, ""
    except: return True, ""

# =========================
# 🔒 로그인 화면
# =========================
if not st.session_state.logged_in:
    st.title("🔒 EMS 협력사 로그인")
    with st.form("login_form"):
        u_id = st.text_input("아이디(상호명)").strip()
        u_pw = st.text_input("비밀번호", type="password").strip()
        if st.form_submit_button("로그인"):
            # 유저 확인 (user_dict 로드 생략, 실제 코드엔 포함)
            if u_id in user_dict and user_dict[u_id] == u_pw:
                success, msg = login_logic(u_id, st.session_state.temp_dev_id)
                if success:
                    st.session_state.logged_in = True
                    st.session_state.user_id = u_id
                    st.rerun()
                else: st.error(f"🚨 {msg}")
            else: st.error("❌ 정보를 확인해주세요.")
    st.stop()

# 이후 메뉴 로직은 동일...

# =========================
# 🏠 사이드바 (메뉴 은닉 핵심)
# =========================
menu_options = ["📊 실시간 매물 현황", "🔍 등록 매물 조회"]
if st.session_state.auth_res: menu_options.append("📅 세대관람 예약")
if st.session_state.auth_manage: menu_options.append("⚙️ 매물 통합 관리")

with st.sidebar:
    st.success(f"👤 {st.session_state.user_id} 인증됨")
    choice = st.radio("메뉴 이동", menu_options)
    st.divider()
    with st.expander("🛠️ 관리자 인증"):
        pw_in = st.text_input("코드 입력", type="password")
        if pw_in == ADMIN_PASSWORD_RES and not st.session_state.auth_res:
            st.session_state.auth_res = True; st.rerun()
        if pw_in == ADMIN_PASSWORD_MANAGE and not st.session_state.auth_manage:
            st.session_state.auth_manage = True; st.rerun()
    if st.button("🔄 새로고침"): st.cache_data.clear(); st.rerun()
    if st.button("🚪 로그아웃 (기기 해제)"):
        try:
            ws = sheet.worksheet("접속현황")
            rows = ws.get_all_values()
            for i, r in enumerate(rows):
                if r[0] == st.session_state.user_id:
                    if r[1] == st.session_state.browser_id: ws.update(f'B{i+1}', [[""]])
                    elif r[2] == st.session_state.browser_id: ws.update(f'C{i+1}', [[""]])
                    break
        except: pass
        st.session_state.clear(); st.rerun()
        
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
