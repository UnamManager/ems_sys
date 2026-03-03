import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, datetime, timedelta
from st_aggrid import AgGrid, GridOptionsBuilder
import plotly.express as px
import smtplib
from email.mime.text import MIMEText
import json
import os

# 1. 페이지 설정
st.set_page_config(page_title="EMS 통합 관리 시스템 v2.5", layout="wide")

# =========================
# 🔐 보안 및 알림 설정
# =========================
if "admin_auth" not in st.session_state:
    st.session_state.admin_auth = False

ADMIN_PASSWORD = "3090"
# 알림용 이메일 설정 (환경변수 권장, 테스트 시 직접 입력 가능)
EMAIL_SENDER = os.environ.get("EMAIL_ADDRESS") 
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
ADMIN_RECEIVER = os.environ.get("ADMIN_NOTIFY_EMAIL") 

def send_email_notification(subject, body):
    """관리자에게 즉시 이메일 알림 전송"""
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
# 📊 데이터 로드 및 시트 인증
# =========================
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT"])
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
# 🏠 사이드바 및 메뉴 구성 (에러 방지 위치)
# =========================
with st.sidebar:
    st.title("EMS SYSTEM")
    # choice 변수를 여기서 확실히 정의합니다.
    choice = st.radio("메뉴 선택", ["📊 통합 대시보드", "🔍 매물 상세조회", "🔐 관리자 모드"])
    if st.button("🔄 데이터 강제 새로고침"):
        st.cache_data.clear()
        st.rerun()

# =========================
# 1️⃣ 📊 통합 대시보드 (차트 포함)
# =========================
if choice == "📊 통합 대시보드":
    st.header("📈 실시간 매물 분석")
    if df_total.empty:
        st.info("데이터가 없습니다.")
    else:
        # 상단 지표
        t_m = len(df_total)
        a_m = len(df_total[df_total["거래여부"] == "관람가능"])
        c1, c2, c3 = st.columns(3)
        c1.metric("📌 전체 매물", f"{t_m}개")
        c2.metric("✅ 관람 가능", f"{a_m}개", delta=f"{(a_m/t_m*100):.1f}%" if t_m > 0 else "0%")
        c3.metric("📅 오늘 날짜", date.today().strftime("%Y-%m-%d"))

        # Plotly 차트
        st.divider()
        col_left, col_right = st.columns(2)
        with col_left:
            fig_pie = px.pie(df_total, names='단지', title="단지별 매물 비중", hole=0.3)
            st.plotly_chart(fig_pie, use_container_width=True)
        with col_right:
            fig_bar = px.bar(df_total.groupby(['단지', '거래여부']).size().reset_index(name='수량'), 
                             x='단지', y='수량', color='거래여부', barmode='group', title="단지별 상태 현황")
            st.plotly_chart(fig_bar, use_container_width=True)

        st.write("#### 📋 전체 매물 목록")
        AgGrid(df_total, height=400)

# =========================
# 2️⃣ 🔍 매물 상세조회
# =========================
elif choice == "🔍 매물 상세조회":
    st.header("🔍 매물 필터 검색")
    s_danji = st.selectbox("단지", ["1단지", "2단지", "3단지"])
    df_v = df_total[df_total["단지"] == s_danji]
    st.dataframe(df_v, use_container_width=True)

# =========================
# 3️⃣ 🔐 관리자 모드 (이메일 + 달력)
# =========================
elif choice == "🔐 관리자 모드":
    if not st.session_state.admin_auth:
        pwd = st.text_input("비밀번호 입력", type="password")
        if pwd == ADMIN_PASSWORD:
            st.session_state.admin_auth = True
            st.rerun()
        st.stop()

    tab1, tab2, tab3 = st.tabs(["📅 예약 등록", "📊 주간 스케줄러", "⚙️ 상태 관리"])

    # --- 📅 예약 등록 및 메일 발송 ---
    with tab1:
        res_dj = st.selectbox("단지 선택", ["1단지", "2단지", "3단지"], key="res_dj")
        f_unit = df_total[df_total["단지"] == res_dj]
        
        with st.form("res_form_email"):
            r_name = st.text_input("예약자/중개업소")
            r_count = st.number_input("관람 세대수", 1, 3, 1)
            
            r_items = []
            for i in range(r_count):
                cols = st.columns(3)
                d = cols[0].selectbox(f"{i+1} 동", sorted(f_unit["동"].unique()), key=f"rd_{i}")
                h = cols[1].selectbox(f"{i+1} 호", sorted(f_unit[f_unit["동"]==d]["호수"].unique()), key=f"rh_{i}")
                m_match = f_unit[(f_unit["동"]==d) & (f_unit["호수"]==h)]
                if not m_match.empty:
                    m = m_match.iloc[0]
                    cols[2].info(f"{m['타입']} ({m['거래여부']})")
                    r_items.append({"동":d, "호수":h, "타입":m['타입'], "상태":m['거래여부']})
            
            time_v = st.selectbox("시간", [f"{h:02d}:00~{h+1:02d}:00" for h in range(8,21)])
            memo = st.text_input("비고")
            
            if st.form_submit_button("📅 예약 확정 및 메일 발송"):
                if any(x["상태"] == "거래완료" for x in r_items):
                    st.error("거래완료 세대 포함됨")
                elif not r_name:
                    st.warning("예약자명을 입력하세요.")
                else:
                    # 시트 저장
                    target = f"{res_dj}_관람예약" if int(time_v[:2]) < 16 else "야간_관람예약"
                    ws = sheet.worksheet(target)
                    new_rows = [[date.today().strftime("%Y-%m-%d"), r_name, "", f"{r_count}세대", s["동"], s["호수"], s["타입"], time_v, "", memo] for s in r_items]
                    ws.append_rows(new_rows)
                    
                    # 📧 이메일 알림 본문
                    details = "\n".join([f"- {s['동']}동 {s['호수']}호" for s in r_items])
                    body = f"새 예약 알림\n\n단지: {res_dj}\n예약자: {r_name}\n시간: {time_v}\n세대내역:\n{details}\n비고: {memo}"
                    
                    # 발송
                    send_email_notification(f"📢 [{res_dj}] 새 예약: {r_name}", body)
                    st.success("✅ 저장 및 메일 발송 완료!")
                    st.cache_data.clear()

    # --- 📊 주간 스케줄러 ---
    with tab2:
        v_dj = st.selectbox("조회 단지", ["1단지", "2단지", "3단지", "야간"])
        try:
            ws_n = f"{v_dj}_관람예약" if v_dj != "야간" else "야간_관람예약"
            v_data = sheet.worksheet(ws_n).get_all_values()
            df_cal = pd.DataFrame(v_data[1:], columns=["날짜","예약자","중개업소","세대수","동","호수","타입","시간","매니저","비고"])
            # 이번 주 데이터만 필터
            df_cal['날짜'] = pd.to_datetime(df_cal['날짜'])
            today = datetime.now().date()
            start = today - timedelta(days=today.weekday())
            df_this_week = df_cal[df_cal['날짜'].dt.date >= start].sort_values(by=['날짜', '시간'])
            st.dataframe(df_this_week[["날짜", "시간", "동", "호수", "예약자", "비고"]], use_container_width=True)
        except: st.error("데이터 로드 실패")

    # --- ⚙️ 상태 관리 ---
    with tab3:
        st.subheader("매물 상태 즉시 변경")
        u_dj = st.selectbox("단지 선택", ["1단지", "2단지", "3단지"], key="udj")
        u_f = df_total[df_total["단지"]==u_dj]
        if not u_f.empty:
            ud = st.selectbox("동", sorted(u_f["동"].unique()), key="udong")
            uh = st.selectbox("호수", sorted(u_f[u_f["동"]==ud]["호수"].unique()), key="uho")
            curr = u_f[(u_f["동"]==ud) & (u_f["호수"]==uh)].iloc[0]
            new_s = st.radio("상태 변경", ["관람가능", "거래완료"], index=0 if curr["거래여부"]=="관람가능" else 1)
            if st.button("💾 즉시 반영"):
                ws = sheet.worksheet(f"{u_dj}_{curr['거래유형']}")
                for i, r in enumerate(ws.get_all_values()):
                    if r[2] == ud and r[3] == uh:
                        ws.update_cell(i+1, 9, new_s)
                        break
                st.success("변경 완료!")
                st.cache_data.clear()
                st.rerun()
