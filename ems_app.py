import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, date, timedelta, timezone
import json
import uuid
import time

# =========================
# 1. 관리자 전용 설정
# =========================
st.set_page_config(page_title="EMS 마스터 관리 시스템", layout="wide")
ADMIN_PASSWORD_MANAGE = "unam0119" 

if "admin_logged_in" not in st.session_state:
    st.title("⚙️ EMS 마스터 로그인")
    pw_in = st.text_input("관리자 전용 코드를 입력하세요", type="password")
    if st.button("관리자 인증"):
        if pw_in == ADMIN_PASSWORD_MANAGE:
            st.session_state.admin_logged_in = True
            st.rerun()
        else: st.error("❌ 코드가 올바르지 않습니다.")
    st.stop()

# =========================
# 🔑 데이터 연결
# =========================
@st.cache_resource(ttl=60)
def get_ems_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open("EMS")

sheet = get_ems_sheet()
TIME_SLOTS = ["10:00 ~ 10:45", "11:00 ~ 11:45", "13:00 ~ 13:45", "14:00 ~ 14:45", "15:00 ~ 15:45", "16:00 ~ 16:45", "17:00 ~ 17:45"]
COL_NAMES = ["예약날짜", "예약자", "중개업소", "관람세대수", "동호수", "타입", "예약시간", "비고", "ID"]

@st.cache_data(ttl=60)
def load_admin_data():
    sheets = ["1단지_매매","1단지_임대","2단지_매매","2단지_임대","3단지_매매","3단지_임대"]
    df_list = []
    for s in sheets:
        try:
            ws = sheet.worksheet(s); data = ws.get_all_values()
            if len(data) > 1:
                df = pd.DataFrame(data[1:], columns=["NO.","분양구분","동","호수","타입","매물구분","매매가","월세","거래여부", "비고"])
                df["단지"] = s.split("_")[0]; df["거래유형"] = s.split("_")[1]
                df_list.append(df)
        except: continue
    return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()

df_total = load_admin_data()

# 표 스타일 정의 (조회용)
def apply_style(df):
    def style_row(row):
        color = 'background-color: #f1f8e9' if row['거래여부'] == '관람가능' else 'background-color: #fce4ec'
        return [color] * len(row)
    return df.style.apply(style_row, axis=1)

# =========================
# 🏠 사이드바 및 메뉴
# =========================
st.sidebar.title("🛠️ 관리자 메뉴")
choice = st.sidebar.radio("작업 선택", ["🏠 통합 대시보드", "📅 통합 예약 조회", "✂️ 예약 수정/삭제"])
if st.sidebar.button("🔄 새로고침"): st.cache_data.clear(); st.rerun()
if st.sidebar.button("🔒 로그아웃"): st.session_state.clear(); st.rerun()

# --- [작업 1: 통합 대시보드 (상태변경 + 매물조회 + 예약등록)] ---
if choice == "🏠 통합 대시보드":
    st.title("🏠 매물 및 예약 관리 대시보드")
    
    adm_tab1, adm_tab2, adm_tab3 = st.tabs(["📍 거래상태 변경", "🔍 매물 통합 조회", "📝 관리자 예약 등록"])

    # [탭 1: 거래상태 변경]
    with adm_tab1:
        st.subheader("📍 매물 상태 업데이트")
        c1, c2, c3 = st.columns(3)
        a_dj = c1.selectbox("단지", ["1단지", "2단지", "3단지"], key="sb_dj")
        a_dong = c2.text_input("동", key="ti_dong")
        a_ho = c3.text_input("호수", key="ti_ho")
        if a_dong and a_ho:
            target = df_total[(df_total["단지"] == a_dj) & (df_total["동"] == a_dong) & (df_total["호수"] == a_ho)]
            if not target.empty:
                curr = target.iloc[0]
                with st.form("adm_status"):
                    new_s = st.selectbox("거래 상태", ["관람가능", "거래완료"], index=0 if curr["거래여부"]=="관람가능" else 1)
                    new_n = st.text_input("비고", value=curr["비고"])
                    if st.form_submit_button("저장"):
                        ws = sheet.worksheet(f"{a_dj}_{curr['거래유형']}")
                        rows = ws.get_all_values()
                        idx = next((i+1 for i, r in enumerate(rows) if len(r)>3 and r[2]==a_dong and r[3]==a_ho), -1)
                        if idx != -1:
                            ws.update(f'I{idx}:J{idx}', [[new_s, new_n]])
                            st.success("✅ 변경 완료!"); st.cache_data.clear(); time.sleep(1); st.rerun()
            else: st.error("매물을 찾을 수 없습니다.")

    with adm_tab2:
        st.subheader("🔍 전체 매물 실시간 조회")
        
        # 1줄: 대분류 필터
        af1, af2, af3, af4 = st.columns(4)
        as_danji = af1.multiselect("단지 선택", df_total["단지"].unique(), key="adm_s_dj")
        as_bunyang = af2.multiselect("분양구분 선택", df_total["분양구분"].unique(), key="adm_s_by")
        as_gubun = af3.multiselect("매물구분 선택", df_total["매물구분"].unique(), key="adm_s_gb")
        as_type = af4.multiselect("타입 선택", sorted(df_total["타입"].unique()), key="adm_s_tp")
        
        # 2줄: 동/호수 상세 검색 (추가된 부분)
        ac1, ac2, _ = st.columns([1, 1, 2])
        asearch_dong = ac1.text_input("🏢 동 검색", key="adm_s_dong")
        asearch_ho = ac2.text_input("🔑 호수 검색", key="adm_s_ho")
        
        df_adm_v = df_total.copy()
        
        # 필터링 로직
        if as_danji: df_adm_v = df_adm_v[df_adm_v["단지"].isin(as_danji)]
        if as_bunyang: df_adm_v = df_adm_v[df_adm_v["분양구분"].isin(as_bunyang)]
        if as_gubun: df_adm_v = df_adm_v[df_adm_v["매물구분"].isin(as_gubun)]
        if as_type: df_adm_v = df_adm_v[df_adm_v["타입"].isin(as_type)]
        
        # 동/호수 검색 로직 (추가된 부분)
        if asearch_dong: df_adm_v = df_adm_v[df_adm_v["동"].str.contains(asearch_dong, na=False)]
        if asearch_ho: df_adm_v = df_adm_v[df_adm_v["호수"].str.contains(asearch_ho, na=False)]
        
        st.dataframe(apply_style(df_adm_v[["단지", "분양구분", "동", "호수", "타입", "매물구분", "매매가", "월세", "거래여부", "비고"]]), 
                     use_container_width=True, hide_index=True)

    # [탭 3: 관리자 예약 등록]
    with adm_tab3:
        st.subheader("📝 관리자 직접 예약 등록")
        from datetime import timedelta, timezone
        KST = timezone(timedelta(hours=9))
        adm_now = datetime.now(KST)
        
        arc1, arc2 = st.columns(2)
        a_res_dj = arc1.selectbox("단지 선택", ["1단지", "2단지", "3단지"], key="ar_dj")
        a_res_date = arc2.date_input("예약 날짜", value=adm_now.date(), key="ar_date")
        a_t_val = st.selectbox("🕒 관람 시간 선택", TIME_SLOTS, key="ar_time")
        
        a_f_unit = df_total[df_total["단지"] == a_res_dj]
        a_u_dongs = sorted(a_f_unit["동"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
        a_r_count = st.selectbox("🏠 관람 세대수", [1, 2], key="ar_count")
        
        a_r_items = []
        for i in range(a_r_count):
            arow_c1, arow_c2 = st.columns(2)
            asel_d = arow_c1.selectbox(f"동 ({i+1})", a_u_dongs, key=f"ar_d_{i}")
            au_hos = sorted(a_f_unit[a_f_unit["동"] == asel_d]["호수"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
            asel_h = arow_c2.selectbox(f"호수 ({i+1})", au_hos, key=f"ar_h_{i}")
            amatch = a_f_unit[(a_f_unit["동"] == asel_d) & (a_f_unit["호수"] == asel_h)]
            if not amatch.empty:
                a_r_items.append({"동": asel_d, "호수": asel_h, "타입": amatch.iloc[0]['타입']})

        with st.form("adm_reserve_form"):
            ar_name = st.text_input("예약자 성함(실명)")
            ar_agency = st.text_input("중개업소 명칭")
            amemo = st.text_area("비고(관리자 메모)")
            if st.form_submit_button("📅 예약 등록 (관리자 권한)"):
                if not ar_name or not ar_agency:
                    st.error("성함과 업소명을 입력하세요.")
                else:
                    a_target_ws = sheet.worksheet(f"{a_res_dj}_관람예약")
                    a_combined = " / ".join([f"{it['동']}동 {it['호수']}호" for it in a_r_items])
                    a_types = ", ".join([s["타입"] for s in a_r_items])
                    a_new_row = [
                        a_res_date.strftime("%Y-%m-%d"), ar_name, ar_agency, 
                        f"{len(a_r_items)}세대", a_combined, a_types, 
                        a_t_val, amemo, "ADMIN_DIRECT"
                    ]
                    a_target_ws.append_row(a_new_row)
                    st.success("✅ 관리자 예약 등록 완료!"); st.cache_data.clear(); time.sleep(1); st.rerun()

# --- [작업 2: 통합 조회 (기존 유지)] ---
elif choice == "📅 통합 예약 조회":
    st.title("📅 전체 예약 현황")
    adm_date = st.date_input("조회 날짜", date.today())
    formatted_date = adm_date.strftime("%Y-%m-%d")
    
    tabs = st.tabs(["1단지", "2단지", "3단지", "📊 전체보기"])
    for i, dj in enumerate(["1단지", "2단지", "3단지"]):
        with tabs[i]:
            ws = sheet.worksheet(f"{dj}_관람예약"); data = ws.get_all_values()
            df = pd.DataFrame(data[1:], columns=data[0]) if len(data)>1 else pd.DataFrame(columns=COL_NAMES)
            df = df[df["예약날짜"] == formatted_date]
            st.write(f"🏠 {dj} 예약: {len(df)}건")
            st.dataframe(df, use_container_width=True, hide_index=True)
    
    with tabs[3]:
        all_res = []
        for dj in ["1단지", "2단지", "3단지"]:
            ws = sheet.worksheet(f"{dj}_관람예약"); data = ws.get_all_values()
            if len(data)>1:
                df = pd.DataFrame(data[1:], columns=data[0])
                df = df[df["예약날짜"] == formatted_date]; df["단지"] = dj
                all_res.append(df)
        if all_res: st.dataframe(pd.concat(all_res), use_container_width=True, hide_index=True)

# --- [작업 3: 마스터 모든 필드 수정/삭제 (기존 유지)] ---
elif choice == "✂️ 예약 수정/삭제":
    st.title("✂️ 예약 정보 마스터 수정")
    col1, col2 = st.columns(2)
    d_date = col1.date_input("날짜 선택", date.today())
    d_dj = col2.selectbox("단지 선택", ["1단지_관람예약", "2단지_관람예약", "3단지_관람예약"])
    
    ws_mod = sheet.worksheet(d_dj); rows_mod = ws_mod.get_all_values()
    if len(rows_mod) > 1:
        df_mod = pd.DataFrame(rows_mod[1:], columns=rows_mod[0])
        day_mod = df_mod[df_mod["예약날짜"] == d_date.strftime("%Y-%m-%d")]
        
        if not day_mod.empty:
            opts = [f"[{r['예약시간']}] {r['예약자']} ({r['중개업소']}) - {r['동호수']}" for i, r in day_mod.iterrows()]
            sel_text = st.selectbox("수정할 항목을 선택하세요", opts)
            
            row_idx = day_mod.index[opts.index(sel_text)] + 2
            curr_r = rows_mod[row_idx-1]
            
            st.markdown("---")
            st.warning(f"✅ 현재 선택된 행 번호: {row_idx} (구글 시트 기준)")
            
            with st.form("master_edit_form"):
                mc1, mc2 = st.columns(2)
                m_date = mc1.date_input("📅 예약날짜", value=datetime.strptime(curr_r[0], "%Y-%m-%d"))
                m_time = mc2.selectbox("🕒 예약시간", TIME_SLOTS, index=TIME_SLOTS.index(curr_r[6]) if curr_r[6] in TIME_SLOTS else 0)
                
                mc3, mc4 = st.columns(2)
                m_name = mc3.text_input("👤 예약자 성함", value=curr_r[1])
                m_agency = mc4.text_input("🏢 중개업소", value=curr_r[2])
                
                mc5, mc6, mc7 = st.columns([1, 2, 1])
                m_count = mc5.text_input("🔢 세대수", value=curr_r[3])
                m_info = mc6.text_input("🏠 동호수 정보", value=curr_r[4])
                m_type = mc7.text_input("📋 타입", value=curr_r[5])
                
                m_memo = st.text_area("📝 비고", value=curr_r[7])
                
                c_edit, c_del = st.columns(2)
                if c_edit.form_submit_button("💾 수정된 내용 저장", use_container_width=True):
                    updated_row = [
                        m_date.strftime("%Y-%m-%d"), m_name, m_agency, 
                        m_count, m_info, m_type, m_time, m_memo, curr_r[8]
                    ]
                    ws_mod.update(f'A{row_idx}:I{row_idx}', [updated_row])
                    st.success("✅ 모든 정보가 수정되었습니다."); st.cache_data.clear(); time.sleep(1); st.rerun()
                
                if c_del.form_submit_button("🗑️ 예약 삭제", use_container_width=True):
                    ws_mod.delete_rows(row_idx)
                    st.success("🗑️ 해당 예약이 삭제되었습니다."); st.cache_data.clear(); time.sleep(1); st.rerun()
        else:
            st.info("해당 날짜에 예약 내역이 없습니다.")
