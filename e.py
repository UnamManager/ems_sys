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
# 1. 페이지 설정 및 디자인 스타일
# =========================
st.set_page_config(page_title="EMS 통합 관리 시스템", layout="wide")
st.markdown("""
    <style>
    [data-testid="stElementToolbar"] { display: none !important; }
    .stButton>button { width: 100%; height: 3em; border-radius: 8px; font-weight: bold; }
    .time-card { border-radius: 8px; padding: 5px; text-align: center; margin-bottom: 5px; }
    .time-card p { margin: 0; font-size: 0.7rem; color: #666; }
    .time-card strong { font-size: 0.85rem; }
    /* 테이블 가독성 향상 */
    .stDataFrame { border: 1px solid #f0f2f6; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# =========================
# 🔑 세션 및 환경 설정
# =========================
if "session_key" not in st.session_state: 
    st.session_state["session_key"] = str(uuid.uuid4())
if "logged_in" not in st.session_state: 
    st.session_state["logged_in"] = False
if "user_id" not in st.session_state: 
    st.session_state["user_id"] = ""
if "auth_manage" not in st.session_state: 
    st.session_state["auth_manage"] = False

ADMIN_PASSWORD_MANAGE = "3214"
TIME_SLOTS = ["10:00 ~ 10:45", "11:00 ~ 11:45", "13:00 ~ 13:45", "14:00 ~ 14:45", "15:00 ~ 15:45", "16:00 ~ 16:45", "17:00 ~ 17:45"]
NIGHT_SLOTS = ["16:00 ~ 16:45", "17:00 ~ 17:45"]
COL_NAMES = ["예약날짜", "예약자", "중개업소", "관람세대수", "동", "호수", "타입", "예약시간", "비고"]

# =========================
# 📩 구글 API 연결 및 데이터 캐싱 (오류 방지의 핵심)
# =========================
@st.cache_resource(ttl=3600)
def get_gspread_client():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"인증 오류: {e}")
        return None

def get_ems_sheet():
    client = get_gspread_client()
    if client:
        return client.open("EMS")
    return None

# 5분간 데이터를 메모리에 저장 (이 기능이 API 호출을 획기적으로 줄임)
@st.cache_data(ttl=300) 
def load_all_cached_data():
    sheet_obj = get_ems_sheet()
    if not sheet_obj: return pd.DataFrame(), {}
    
    try:
        # 1. 매물 데이터 통합 로드
        sheets = ["1단지_매매","1단지_임대","2단지_매매","2단지_임대","3단지_매매","3단지_임대"]
        df_list = []
        for s in sheets:
            try:
                ws = sheet_obj.worksheet(s)
                data = ws.get_all_values()
                if len(data) > 1:
                    df = pd.DataFrame(data[1:], columns=["NO.","분양구분","동","호수","타입","매물구분","매매가","월세","거래여부", "비고"])
                    df["단지"] = s.split("_")[0]
                    df["거래유형"] = s.split("_")[1]
                    df_list.append(df)
            except: continue
        
        # 2. 사용자 계정 정보 로드
        user_ws = sheet_obj.worksheet("사용자목록")
        u_data = user_ws.get_all_values()
        user_dict = {str(row[0]).strip(): str(row[1]).strip() for row in u_data[1:] if len(row) >= 2}
        
        final_df = pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()
        return final_df, user_dict
    except:
        return pd.DataFrame(), {}

# 데이터 실행 및 시트 객체 확보
df_total, user_dict = load_all_cached_data()
sheet = get_ems_sheet()

# 🎨 스타일 함수
def apply_style(df):
    def row_style(row):
        # '신규' 강조
        if '신규' in str(row.get('비고', '')):
            return ['background-color: #fff3cd; font-weight: 500;'] * len(row)
        # 거래여부 색상
        styles = [''] * len(row)
        if row.get('거래여부') == "관람가능":
            styles[df.columns.get_loc('거래여부')] = "background-color: #d4edda; font-weight: bold;"
        elif row.get('거래여부') == "거래완료":
            styles[df.columns.get_loc('거래여부')] = "background-color: #f8d7da;"
        return styles
    return df.style.apply(row_style, axis=1)

# =========================
# 🔒 로그인 시스템 (API 부하 최소화형)
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
# 🏠 사이드바 및 메뉴 구성
# =========================
menu_options = ["📊 실시간 현황", "🔍 등록 매물 조회", "📅 세대관람 예약"]
if st.session_state.auth_manage:
    menu_options.append("⚙️ 관리자 모드")

with st.sidebar:
    st.success(f"👤 {st.session_state.user_id}님 접속 중")
    choice = st.radio("메뉴 바로가기", menu_options)
    st.divider()
    
    # 관리자 인증
    if not st.session_state.auth_manage:
        with st.expander("🛠️ 관리자 권한 획득"):
            pw_in = st.text_input("관리자 암호", type="password")
            if st.button("권한 승인"):
                if pw_in == ADMIN_PASSWORD_MANAGE:
                    st.session_state.auth_manage = True
                    st.rerun()
                else: st.error("암호 불일치")
    
    # API 리셋 버튼 (형이 원하신 수동 제어)
    if st.button("🔄 최신 데이터 새로고침"):
        st.cache_data.clear()
        st.rerun()
    
    if st.button("🔒 안전 로그아웃"):
        st.session_state.clear()
        st.rerun()

# =========================
# 📊 [페이지 1] 실시간 현황
# =========================
if choice == "📊 실시간 현황":
    st.title("📊 단지별 실시간 매물 현황")
    c1, c2, c3 = st.columns(3)
    c1.metric("📌 전체 매물", f"{len(df_total)}개")
    c2.metric("✅ 거래 완료", f"{len(df_total[df_total['거래여부']=='거래완료'])}개")
    c3.metric("🏠 관람 가능", f"{len(df_total[df_total['거래여부']=='관람가능'])}개")
    
    st.divider()
    st.subheader("📍 최근 거래완료 목록")
    df_done = df_total[df_total["거래여부"] == "거래완료"].copy()
    # 정보 보호 처리
    for col in ["매매가", "월세", "비고"]:
        if col in df_done.columns: df_done[col] = "🔒 거래완료"
    
    st.dataframe(apply_style(df_done[["단지", "분양구분", "동", "호수", "타입", "매물구분", "매매가", "월세", "거래여부", "비고"]]), 
                 use_container_width=True, hide_index=True)

# =========================
# 🔍 [페이지 2] 등록 매물 조회
# =========================
elif choice == "🔍 등록 매물 조회":
    st.title("🔍 통합 매물 검색 센터")
    with st.container(border=True):
        f1, f2, f3, f4 = st.columns(4)
        s_danji = f1.multiselect("단지", df_total["단지"].unique())
        s_bunyang = f2.multiselect("분양구분", df_total["분양구분"].unique())
        s_gubun = f3.multiselect("매물구분", df_total["매물구분"].unique())
        s_type = f4.multiselect("타입", sorted(df_total["타입"].unique()))
        
        c1, c2, _ = st.columns([1,1,2])
        search_dong = c1.text_input("🏢 동 검색 (예: 101)")
        search_ho = c2.text_input("🔑 호수 검색 (예: 501)")

    df_v = df_total.copy()
    if s_danji: df_v = df_v[df_v["단지"].isin(s_danji)]
    if s_bunyang: df_v = df_v[df_v["분양구분"].isin(s_bunyang)]
    if s_gubun: df_v = df_v[df_v["매물구분"].isin(s_gubun)]
    if s_type: df_v = df_v[df_v["타입"].isin(s_type)]
    if search_dong: df_v = df_v[df_v["동"] == search_dong]
    if search_ho: df_v = df_v[df_v["호수"] == search_ho]

    # 거래완료 정보 마스킹
    mask = df_v["거래여부"] == "거래완료"
    for col in ["매매가", "월세", "비고"]:
        if col in df_v.columns: df_v.loc[mask, col] = "🔒 거래완료"
        
    st.dataframe(apply_style(df_v[["단지", "분양구분", "동", "호수", "타입", "매물구분", "매매가", "월세", "거래여부", "비고"]]), 
                 use_container_width=True, hide_index=True)

# =========================
# 📅 [페이지 3] 세대관람 예약
# =========================
elif choice == "📅 세대관람 예약":
    st.title("📋 세대관람 예약 시스템")
    tab1, tab2 = st.tabs(["📝 신규 예약 등록", "📊 실시간 현황판"])
    
    with tab1:
        res_dj = st.selectbox("관람하실 단지 선택", ["1단지", "2단지", "3단지"])
        r_date_val = st.date_input("방문 날짜", date.today())
        t_val = st.selectbox("희망 시간", TIME_SLOTS)
        
        target_sheet_name = "야간_관람예약" if t_val in NIGHT_SLOTS else f"{res_dj}_관람예약"
        
        try:
            target_ws = sheet.worksheet(target_sheet_name)
            all_res = target_ws.get_all_values()
            if len(all_res) > 1:
                daily_df = pd.DataFrame(all_res[1:], columns=all_res[0])
                count = len(daily_df[(daily_df["예약날짜"] == r_date_val.strftime("%Y-%m-%d")) & (daily_df["예약시간"] == t_val)])
            else: count = 0
            
            can_reserve = count < 3
            if not can_reserve: st.error(f"🚫 해당 시간은 예약 마감입니다. ({count}/3)")
            else: st.success(f"✅ 예약 가능합니다. ({count}/3)")
            
            st.divider()
            f_unit = df_total[df_total["단지"] == res_dj]
            r_count = st.selectbox("관람할 세대수", [1, 2])
            r_items = []
            for i in range(r_count):
                with st.container(border=True):
                    col1, col2 = st.columns(2)
                    d_sel = col1.selectbox(f"동 ({i+1})", sorted(f_unit["동"].unique()), key=f"d_{i}")
                    h_sel = col2.selectbox(f"호수 ({i+1})", sorted(f_unit[f_unit["동"]==d_sel]["호수"].unique()), key=f"h_{i}")
                    match = f_unit[(f_unit["동"]==d_sel) & (f_unit["호수"]==h_sel)]
                    if not match.empty: r_items.append({"동":d_sel, "호수":h_sel, "타입":match.iloc[0]['타입']})

            with st.form("reserve_form"):
                r_name = st.text_input("예약자 성함(실명)")
                r_agency = st.text_input("중개업소 명칭")
                memo = st.text_area("기타 전달사항")
                if st.form_submit_button("📅 예약 확정하기", disabled=not can_reserve):
                    if r_name and r_agency:
                        combined_info = " / ".join([f"{it['동']}동 {it['호수']}호" for it in r_items])
                        new_row = [r_date_val.strftime("%Y-%m-%d"), r_name, r_agency, f"{len(r_items)}세대", combined_info, "", ", ".join([s["타입"] for s in r_items]), t_val, f"[{st.session_state.user_id}] {memo}"]
                        target_ws.append_row(new_row)
                        st.success("🎉 예약이 정상적으로 접수되었습니다."); st.cache_data.clear(); time.sleep(1); st.rerun()
                    else: st.warning("필수 정보를 입력해주세요.")
        except: st.error("시스템 연결이 원활하지 않습니다. 잠시 후 시도해주세요.")

    with tab2:
        st.subheader(f"📅 {r_date_val} 예약 현황")
        sel_dj_view = st.radio("단지 선택", ["1단지", "2단지", "3단지"], horizontal=True, key="view_radio")
        try:
            # 실시간 현황 카드 출력
            ws_n = sheet.worksheet(f"{sel_dj_view}_관람예약").get_all_values()
            ws_y = sheet.worksheet("야간_관람예약").get_all_values()
            df_n = pd.DataFrame(ws_n[1:], columns=ws_n[0]) if len(ws_n) > 1 else pd.DataFrame(columns=COL_NAMES)
            df_y = pd.DataFrame(ws_y[1:], columns=ws_y[0]) if len(ws_y) > 1 else pd.DataFrame(columns=COL_NAMES)
            v_all = pd.concat([df_n, df_y])
            v_daily = v_all[v_all["예약날짜"] == r_date_val.strftime("%Y-%m-%d")]
            
            cols = st.columns(len(TIME_SLOTS))
            for i, slot in enumerate(TIME_SLOTS):
                cnt = len(v_daily[v_daily["예약시간"] == slot])
                with cols[i]:
                    color = "#ff4b4b" if cnt >= 3 else "#28a745"
                    st.markdown(f"""<div class="time-card" style="border: 1px solid {color};"><p>{slot.split(' ~ ')[0]}</p><strong>{cnt}/3</strong></div>""", unsafe_allow_html=True)
            
            if not v_daily.empty:
                v_daily["예약자"] = v_daily["예약자"].apply(lambda n: n[0] + "*" * (len(n)-1))
                st.dataframe(v_daily[["예약시간", "예약자", "중개업소", "동"]].sort_values("예약시간"), use_container_width=True, hide_index=True)
            else: st.info("예약 내역이 없습니다.")
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
