import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, datetime
import smtplib
from email.mime.text import MIMEText
import json
import os

# 1. 페이지 설정
st.set_page_config(page_title="EMS 통합 관리 시스템", layout="wide")

# =========================
# 🔐 보안 및 이메일 설정
# =========================
if "admin_auth" not in st.session_state:
    st.session_state.admin_auth = False

ADMIN_PASSWORD = "3090"

try:
    EMAIL_SENDER = st.secrets["EMAIL_ADDRESS"]
    EMAIL_PASSWORD = st.secrets["EMAIL_PASSWORD"]
    ADMIN_RECEIVER = st.secrets["ADMIN_NOTIFY_EMAIL"]
except KeyError as e:
    st.error(f"Secrets 설정 오류: {e} 항목을 찾을 수 없습니다.")
    st.stop()

def send_email_notification(subject, body):
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = EMAIL_SENDER
        msg['To'] = ADMIN_RECEIVER
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, ADMIN_RECEIVER, msg.as_string())
        return True
    except: return False

# =========================
# 📊 데이터 로드 및 정렬 로직
# =========================
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("EMS")

@st.cache_data(show_spinner="데이터 동기화 중...", ttl=300)
def load_all_data():
    sheets = ["1단지_매매","1단지_임대","2단지_매매","2단지_임대","3단지_매매","3단지_임대"]
    cols = ["NO.","분양구분","동","호수","타입","매물구분","매매가","월세","거래여부"]
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
                df["동_num"] = pd.to_numeric(df["동"], errors='coerce').fillna(0)
                df["호_num"] = pd.to_numeric(df["호수"], errors='coerce').fillna(0)
                
                df_list.append(df)
        except: continue
    
    if df_list:
        full_df = pd.concat(df_list, ignore_index=True)
        return full_df.sort_values(by=["단지", "동_num", "호_num"])
    return pd.DataFrame(columns=cols + ["단지", "거래유형"])

df_total = load_all_data()

def apply_final_style(df, columns):
    df_styled = df.copy()
    rename_dict = {'매매가': '매매가(만원)'}
    df_styled['매매가'] = df_styled['매매가_num']
    df_styled['월세'] = df_styled['월세_num']
    df_display = df_styled[columns].rename(columns=rename_dict)
    
    return df_display.style.applymap(
        lambda val: f'background-color: {"#d4edda" if val == "관람가능" else "#f8d7da" if val == "거래완료" else "white"}',
        subset=['거래여부']
    ).format({
        '매매가(만원)': '{:,.0f}',
        '월세': '{:,.0f}'
    })

# =========================
# 🏠 메인 메뉴
# =========================
with st.sidebar:
    st.markdown("### 🏢 EMS 관리 센터")
    choice = st.radio("메뉴 이동", ["📊 실시간 매물 현황", "🔍 등록 매물 조회", "🔐 관리자 모드"])
    st.divider()
    if st.button("🔄 데이터 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- 1번 메뉴 ---
if choice == "📊 실시간 매물 현황":
    st.title("📊 실시간 매물 현황")
    c1, c2, c3 = st.columns(3)
    c1.metric("📌 전체 관리 매물", f"{len(df_total)}개")
    c2.metric("✅ 완료 매물", f"{len(df_total[df_total['거래여부'] == '거래완료'])}개")
    c3.metric("🏠 관람 가능 매물", f"{len(df_total[df_total['거래여부'] == '관람가능'])}개")
    st.divider()
    df_done = df_total[df_total["거래여부"] == "거래완료"].copy()
    if not df_done.empty:
        st.dataframe(apply_final_style(df_done, ["분양구분", "동", "타입", "매물구분", "매매가", "월세", "거래여부"]), use_container_width=True, hide_index=True)
    else: st.info("완료된 매물이 없습니다.")

# --- 2번 메뉴 ---
elif choice == "🔍 등록 매물 조회":
    st.title("🔍 등록 매물 조회")
    f1, f2, f3, f4 = st.columns(4)
    s_danji = f1.multiselect("단지", df_total["단지"].unique())
    s_bunyang = f2.multiselect("분양구분", df_total["분양구분"].unique())
    s_gubun = f3.multiselect("매물구분", df_total["매물구분"].unique())
    s_type = f4.multiselect("타입", sorted(df_total["타입"].unique()))
    search_q = st.text_input("동 또는 호수 직접 검색")
    
    df_v = df_total.copy()
    if s_danji: df_v = df_v[df_v["단지"].isin(s_danji)]
    if s_bunyang: df_v = df_v[df_v["분양구분"].isin(s_bunyang)]
    if s_gubun: df_v = df_v[df_v["매물구분"].isin(s_gubun)]
    if s_type: df_v = df_v[df_v["타입"].isin(s_type)]
    if search_q: df_v = df_v[df_v["동"].str.contains(search_q) | df_v["호수"].str.contains(search_q)]
    st.dataframe(apply_final_style(df_v, ["분양구분", "동", "호수", "타입", "매물구분", "매매가", "월세", "거래여부"]), use_container_width=True, hide_index=True)

# --- 3번 메뉴 ---
elif choice == "🔐 관리자 모드":
    if not st.session_state.admin_auth:
        pwd = st.text_input("관리자 인증", type="password")
        if pwd == ADMIN_PASSWORD:
            st.session_state.admin_auth = True
            st.rerun()
        st.stop()

    tab1, tab2, tab3 = st.tabs(["📅 세대관람 예약", "📊 세대관람 현황", "⚙️ 관람 가능여부 관리"])

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
                d_sel = col1.selectbox("동", u_dongs, key=f"d_reg_{i}")
                u_hos = sorted(f_unit[f_unit["동"]==d_sel]["호수"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
                h_sel = col2.selectbox("호수", u_hos, key=f"h_reg_{i}")
                match = f_unit[(f_unit["동"]==d_sel) & (f_unit["호수"]==h_sel)]
                if not match.empty:
                    m_row = match.iloc[0]
                    st.markdown(f"✅ 타입: **{m_row['타입']}** | 상태: **{m_row['거래여부']}**")
                    r_items.append({"동":d_sel, "호수":h_sel, "타입":m_row['타입'], "상태":m_row['거래여부']})

        time_options = [f"{h:02d}:00 ~ {h:02d}:45" for h in range(9, 21) if h != 12]
        with st.form("final_reserve_date_form"):
            c1, c2 = st.columns(2)
            r_date = c1.date_input("방문 날짜 선택", date.today())
            r_name = c2.text_input("예약자 성함")
            c3, c4 = st.columns(2)
            r_agency = c3.text_input("중개업소 명칭")
            r_manager = c4.text_input("동행 매니저")
            t_val = st.selectbox("방문 시간", time_options)
            memo_input = st.text_input("상세 메모")
            if st.form_submit_button("📅 예약 최종 확정", use_container_width=True):
                if not r_name: st.error("성함을 입력해주세요.")
                else:
                    target_ws = f"{res_dj}_관람예약" if int(t_val[:2]) < 16 else "야간_관람예약"
                    ws = sheet.worksheet(target_ws)
                    f_date = r_date.strftime("%Y-%m-%d")
                    rows = [[f_date, r_name, r_agency, f"{r_count}세대", s["동"], s["호수"], s["타입"], t_val, r_manager, memo_input] for s in r_items]
                    ws.append_rows(rows)
                    send_email_notification(f"📢 [{res_dj}] 예약 알림: {r_name}님", f"방문일: {f_date}\n시간: {t_val}\n예약자: {r_name}\n업소: {r_agency}\n매니저: {r_manager}")
                    st.success(f"✅ {f_date} 예약 완료")
                    st.cache_data.clear()

    with tab2:
        # =========================
        # 🛡️ 현황 페이지 오류 방지 섹션
        # =========================
        st.subheader("📊 세대관람 스케줄 조회")
        v_dj = st.selectbox("조회 단지 선택", ["1단지", "2단지", "3단지", "야간"])
        
        try:
            ws_n = f"{v_dj}_관람예약" if v_dj != "야간" else "야간_관람예약"
            v_data = sheet.worksheet(ws_n).get_all_values()
            
            # 헤더 정의
            res_cols = ["날짜","예약자","중개업소","세대수","동","호수","타입","시간","동행매니저","비고"]
            
            if len(v_data) > 1:
                # 데이터를 데이터프레임으로 변환 (길이가 안 맞아도 에러 안 나게 처리)
                df_c = pd.DataFrame(v_data[1:], columns=res_cols)
                # 데이터 정제 (None 값 제거)
                df_c = df_c.fillna("")
                
                # --- 금일 스케줄 ---
                today_s = date.today().strftime("%Y-%m-%d")
                st.markdown(f"#### 📅 오늘({today_s})의 스케줄")
                df_t = df_c[df_c['날짜'] == today_s]
                if not df_t.empty:
                    st.dataframe(df_t, use_container_width=True, hide_index=True)
                else: st.info("오늘 예약 내역이 없습니다.")
                
                st.divider()
                
                # --- 날짜별 조회 ---
                st.markdown("#### 🔍 특정 날짜 조회")
                sel_date = st.date_input("날짜 선택", date.today(), key="sch_dp")
                sel_date_s = sel_date.strftime("%Y-%m-%d")
                df_s = df_c[df_c['날짜'] == sel_date_s]
                if not df_s.empty:
                    st.dataframe(df_s, use_container_width=True, hide_index=True)
                else: st.warning(f"{sel_date_s}에 등록된 예약이 없습니다.")
            else:
                st.info(f"'{v_dj}' 단지에 등록된 예약 데이터가 시트에 아예 없습니다.")
                
        except Exception as e:
            st.error(f"⚠️ 데이터를 불러오는 중 오류가 발생했습니다. 구글 시트의 '{v_dj}_관람예약' 탭 이름이 정확한지 확인해 주세요. (에러내용: {e})")

    with tab3:
        u_dj = st.selectbox("상태 관리 단지", ["1단지", "2단지", "3단지"], key="m_dj_tab3_ff")
        u_f = df_total[df_total["단지"]==u_dj]
        if not u_f.empty:
            c1, c2 = st.columns(2)
            u_dongs = sorted(u_f["동"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
            ud = c1.selectbox("동 선택", u_dongs, key="m_d_tab3_ff")
            u_hos = sorted(u_f[u_f["동"]==ud]["호수"].unique(), key=lambda x: int(x) if x.isdigit() else 0)
            uh = c2.selectbox("호수 선택", u_hos, key="m_h_tab3_ff")
            match_u = u_f[(u_f["동"]==ud) & (u_f["호수"]==uh)]
            if not match_u.empty:
                curr = match_u.iloc[0]
                new_s = st.radio(f"현재: {curr['거래여부']}", ["관람가능", "거래완료"])
                if st.button("💾 상태 업데이트 저장", key="save_btn_ff"):
                    ws = sheet.worksheet(f"{u_dj}_{curr['거래유형']}")
                    for i, r in enumerate(ws.get_all_values()):
                        if len(r) > 3 and r[2] == ud and r[3] == uh:
                            ws.update_cell(i+1, 9, new_s)
                            break
                    st.success("상태 변경 완료")
                    st.cache_data.clear()
                    st.rerun()
