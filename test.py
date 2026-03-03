import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, datetime, timedelta
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
# 📊 데이터 로드
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
                df_list.append(df)
        except: continue
    return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame(columns=cols + ["단지", "거래유형"])

df_total = load_all_data()

# =========================
# 🏠 사이드바 메뉴
# =========================
with st.sidebar:
    st.markdown("### 🏢 EMS 관리 센터")
    choice = st.radio("메뉴 이동", ["📊 실시간 매물 현황", "🔍 등록 매물 조회", "🔐 관리자 모드"])
    st.divider()
    if st.button("🔄 데이터 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# =========================
# 1️⃣ 📊 실시간 매물 현황
# =========================
if choice == "📊 실시간 매물 현황":
    st.title("📊 실시간 매물 현황")
    c1, c2, c3 = st.columns(3)
    c1.metric("📌 전체 관리 매물", f"{len(df_total)}개")
    c2.metric("✅ 완료 매물", f"{len(df_total[df_total['거래여부'] == '거래완료'])}개")
    c3.metric("🏠 관람 가능 매물", f"{len(df_total[df_total['거래여부'] == '관람가능'])}개")

    st.divider()
    st.subheader("🏆 완료 세대 현황")
    df_done = df_total[df_total["거래여부"] == "거래완료"]
    view_cols = ["분양구분", "동", "호수", "타입", "매물구분", "매매가", "월세", "거래여부"]
    st.dataframe(df_done[view_cols], use_container_width=True, hide_index=True)

# =========================
# 2️⃣ 🔍 등록 매물 조회
# =========================
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
    
    st.dataframe(df_v[["분양구분", "동", "호수", "타입", "매물구분", "매매가", "월세", "거래여부"]], use_container_width=True, hide_index=True)

# =========================
# 3️⃣ 🔐 관리자 모드
# =========================
elif choice == "🔐 관리자 모드":
    if not st.session_state.admin_auth:
        pwd = st.text_input("관리자 인증", type="password")
        if pwd == ADMIN_PASSWORD:
            st.session_state.admin_auth = True
            st.rerun()
        st.stop()

    tab1, tab2, tab3 = st.tabs(["📅 세대관람 예약", "📊 세대관람 현황", "⚙️ 관람 가능여부 관리"])

    with tab1:
        res_dj = st.selectbox("예약 단지 선택", ["1단지", "2단지", "3단지"])
        f_unit = df_total[df_total["단지"] == res_dj]
        
        # 💡 Form 밖에서 세대수를 선택해야 입력란이 즉시 반응합니다.
        r_count = st.selectbox("관람 세대수 선택", [1, 2, 3])
        
        with st.form("res_form_v6"):
            c1, c2 = st.columns(2)
            r_name = c1.text_input("예약자 성함")
            r_agency = c2.text_input("중개업소 명칭")
            c3, c4 = st.columns(2)
            r_phone = c3.text_input("연락처 (알림용)")
            r_manager = c4.text_input("동행 매니저")
            
            st.divider()
            r_items = []
            for i in range(r_count):
                st.markdown(f"**📍 세대 선택 {i+1}**")
                col1, col2 = st.columns(2)
                d_sel = col1.selectbox("동", sorted(f_unit["동"].unique()), key=f"d_v6_{i}")
                h_sel = col2.selectbox("호수", sorted(f_unit[f_unit["동"]==d_sel]["호수"].unique()), key=f"h_v6_{i}")
                match = f_unit[(f_unit["동"]==d_sel) & (f_unit["호수"]==h_sel)]
                if not match.empty:
                    m_row = match.iloc[0]
                    st.caption(f"타입: {m_row['타입']} | 상태: {m_row['거래여부']}")
                    r_items.append({"동":d_sel, "호수":h_sel, "타입":m_row['타입'], "상태":m_row['거래여부']})
            
            st.divider()
            t_val = st.selectbox("방문 시간", [f"{h:02d}:00" for h in range(8,21)])
            memo_input = st.text_input("상세 메모")
            
            if st.form_submit_button("📅 예약 확정 및 메일 발송", use_container_width=True):
                if not r_name: st.error("예약자 성함을 입력해주세요.")
                elif any(x["상태"] == "거래완료" for x in r_items): st.error("거래완료 세대 포함됨")
                else:
                    target_ws = f"{res_dj}_관람예약" if int(t_val[:2]) < 16 else "야간_관람예약"
                    ws = sheet.worksheet(target_ws)
                    
                    # 💡 연락처를 '비고'란에 합쳐서 저장 (기존 시트 10열 구조 유지)
                    final_memo = f"[연락처: {r_phone}] {memo_input}" if r_phone else memo_input
                    
                    rows = [[date.today().strftime("%Y-%m-%d"), r_name, r_agency, f"{r_count}세대", s["동"], s["호수"], s["타입"], t_val, r_manager, final_memo] for s in r_items]
                    ws.append_rows(rows)
                    
                    # 📧 이메일 알림
                    m_body = f"세대관람 예약 알림\n예약자: {r_name}\n업소: {r_agency}\n연락처: {r_phone}\n매니저: {r_manager}\n시간: {t_val}\n세대:\n"
                    for s in r_items: m_body += f"- {s['동']}동 {s['호수']}호\n"
                    m_body += f"메모: {memo_input}"
                    send_email_notification(f"📢 [{res_dj}] 예약: {r_name}님", m_body)
                    
                    st.success("✅ 예약이 완료되었습니다!")
                    st.cache_data.clear()

    with tab2:
        v_dj = st.selectbox("현황 조회 단지", ["1단지", "2단지", "3단지", "야간"])
        try:
            ws_n = f"{v_dj}_관람예약" if v_dj != "야간" else "야간_관람예약"
            v_data = sheet.worksheet(ws_n).get_all_values()
            df_c = pd.DataFrame(v_data[1:], columns=["날짜","예약자","중개업소","세대수","동","호수","타입","시간","동행매니저","비고"])
            st.dataframe(df_c[df_c['날짜'] == date.today().strftime("%Y-%m-%d")], use_container_width=True, hide_index=True)
        except: st.info("내역이 없습니다.")

    with tab3:
        u_dj = st.selectbox("관리 단지", ["1단지", "2단지", "3단지"], key="m_dj")
        u_f = df_total[df_total["단지"]==u_dj]
        if not u_f.empty:
            c1, c2 = st.columns(2)
            ud = c1.selectbox("동", sorted(u_f["동"].unique()), key="m_d")
            uh = c2.selectbox("호수", sorted(u_f[u_f["동"]==ud]["호수"].unique()), key="m_h")
            match_u = u_f[(u_f["동"]==ud) & (u_f["호수"]==uh)]
            if not match_u.empty:
                curr = match_u.iloc[0]
                new_s = st.radio(f"현재: {curr['거래여부']}", ["관람가능", "거래완료"], key="m_s")
                if st.button("💾 상태 업데이트 저장", use_container_width=True):
                    ws = sheet.worksheet(f"{u_dj}_{curr['거래유형']}")
                    for i, r in enumerate(ws.get_all_values()):
                        if r[2] == ud and r[3] == uh:
                            ws.update_cell(i+1, 9, new_s)
                            break
                    st.success("반영 완료!")
                    st.cache_data.clear()
                    st.rerun()
