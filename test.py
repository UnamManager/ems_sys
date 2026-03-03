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

# 1. 페이지 설정 (모바일 최적화 레이아웃)
st.set_page_config(page_title="EMS 모바일 관리 시스템", layout="wide")

# =========================
# 🔐 보안 및 이메일 설정
# =========================
if "admin_auth" not in st.session_state:
    st.session_state.admin_auth = False

ADMIN_PASSWORD = "3090"
# Gmail 앱 비밀번호 16자리 입력 필요
EMAIL_SENDER = os.environ.get("EMAIL_ADDR", "your_gmail@gmail.com") 
EMAIL_PASSWORD = os.environ.get("EMAIL_PW", "your_app_password")
ADMIN_RECEIVER = "manager_mail@naver.com" 

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
# 📊 데이터 동기화
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
# 📱 모바일 최적화 CSS
# =========================
st.markdown("""
<style>
    /* 메트릭 폰트 크기 조정 */
    [data-testid="stMetricValue"] { font-size: 1.8rem !important; }
    /* 모바일에서 카드 여백 줄이기 */
    .stTable { font-size: 0.8rem; }
    /* 반응형 컨테이너 스타일 */
    .view-card {
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #e0e0e0;
        margin-bottom: 10px;
        background-color: white;
    }
</style>
""", unsafe_allow_html=True)

# =========================
# 🏠 사이드바 메뉴 (반응형)
# =========================
with st.sidebar:
    st.markdown("### 🏢 EMS 모바일 센터")
    choice = st.radio("메뉴 이동", ["📊 통합 대시보드", "🔍 매물 상세조회", "🔐 관리자 모드"])
    st.divider()
    if st.button("🔄 전체 데이터 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# =========================
# 1️⃣ 📊 통합 대시보드 (반응형 지표 + 카드)
# =========================
if choice == "📊 통합 대시보드":
    st.title("📊 실시간 현황")
    
    # 지표 2열 배치 (모바일 가독성 최우선)
    c1, c2 = st.columns(2)
    t_m = len(df_total)
    a_m = len(df_total[df_total["거래여부"] == "관람가능"])
    c1.metric("📌 전체 매물", f"{t_m}개")
    c2.metric("✅ 관람 가능", f"{a_m}개")

    st.divider()
    
    # [업그레이드] 시각화 차트
    fig_bar = px.bar(df_total.groupby(['단지', '거래여부']).size().reset_index(name='수량'), 
                     x='단지', y='수량', color='거래여부', barmode='group', title="단지별 보유 현황")
    fig_bar.update_layout(margin=dict(l=20, r=20, t=40, b=20))
    st.plotly_chart(fig_bar, use_container_width=True)

    # 모바일용 상세 리스트 (AgGrid 대신 st.dataframe 사용 - 모바일 터치 유리)
    st.write("#### 🏠 전체 리스트 요약")
    st.dataframe(df_total[["단지", "동", "호수", "타입", "거래여부"]], use_container_width=True, hide_index=True)

# =========================
# 2️⃣ 🔍 매물 상세조회
# =========================
elif choice == "🔍 매물 상세조회":
    st.title("🔍 매물 퀵 검색")
    search_q = st.text_input("동 또는 호수로 검색 (예: 101)", "")
    
    df_v = df_total.copy()
    if search_q:
        df_v = df_v[df_v["동"].str.contains(search_q) | df_v["호수"].str.contains(search_q)]
    
    # 검색 결과를 카드형태로 출력 (모바일 최적화)
    for _, row in df_v.head(20).iterrows():
        with st.container(border=True):
            col_a, col_b = st.columns([3, 1])
            col_a.markdown(f"**{row['단지']} {row['동']}동 {row['호수']}호**")
            col_a.caption(f"타입: {row['타입']} | 거래: {row['거래유형']}")
            color = "green" if row['거래여부'] == "관람가능" else "red"
            col_b.markdown(f":{color}[**{row['거래여부']}**]")

# =========================
# 3️⃣ 🔐 관리자 모드 (이메일 알림 + 주간 스케줄러)
# =========================
elif choice == "🔐 관리자 모드":
    if not st.session_state.admin_auth:
        pwd = st.text_input("관리자 비번", type="password")
        if pwd == ADMIN_PASSWORD:
            st.session_state.admin_auth = True
            st.rerun()
        st.stop()

    tab1, tab2, tab3 = st.tabs(["📅 예약", "📊 스케줄", "⚙️ 상태"])

    # --- 📅 예약 등록 및 이메일 ---
    with tab1:
        res_dj = st.selectbox("단지", ["1단지", "2단지", "3단지"])
        f_unit = df_total[df_total["단지"] == res_dj]
        
        with st.form("mobile_res_form"):
            r_name = st.text_input("예약자/업체명")
            r_count = st.select_slider("관람 세대수", options=[1, 2, 3])
            
            r_items = []
            for i in range(r_count):
                st.markdown(f"**[{i+1}번째 세대]**")
                c1, c2 = st.columns(2)
                d = c1.selectbox(f"동", sorted(f_unit["동"].unique()), key=f"md_{i}")
                h = c2.selectbox(f"호", sorted(f_unit[f_unit["동"]==d]["호수"].unique()), key=f"mh_{i}")
                m_match = f_unit[(f_unit["동"]==d) & (f_unit["호수"]==h)]
                if not m_match.empty:
                    m = m_match.iloc[0]
                    st.caption(f"→ {m['타입']} / {m['거래여부']}")
                    r_items.append({"동":d, "호수":h, "타입":m['타입'], "상태":m['거래여부']})
            
            t_v = st.selectbox("시간 선택", [f"{h:02d}:00" for h in range(8,21)])
            memo = st.text_input("비고(특이사항)")
            
            if st.form_submit_button("📅 예약 및 메일발송", use_container_width=True):
                if any(x["상태"] == "거래완료" for x in r_items):
                    st.error("거래완료 세대가 포함됨")
                elif not r_name:
                    st.warning("예약자명 필수")
                else:
                    target = f"{res_dj}_관람예약" if int(t_v[:2]) < 16 else "야간_관람예약"
                    ws = sheet.worksheet(target)
                    rows = [[date.today().strftime("%Y-%m-%d"), r_name, "", f"{r_count}세대", s["동"], s["호수"], s["타입"], t_v, "", memo] for s in r_items]
                    ws.append_rows(rows)
                    
                    # 📧 메일 알림 본문 생성
                    details = "\n".join([f"- {s['동']}동 {s['호수']}호" for s in r_items])
                    body = f"[EMS 예약등록]\n단지: {res_dj}\n예약자: {r_name}\n시간: {t_v}\n대상:\n{details}\n비고: {memo}"
                    send_email_notification(f"📢 [{res_dj}] 예약: {r_name}", body)
                    
                    st.success("✅ 완료!")
                    st.cache_data.clear()

    # --- 📊 주간 스케줄러 (카드형 뷰) ---
    with tab2:
        v_dj = st.selectbox("단지 조회", ["1단지", "2단지", "3단지", "야간"], key="vcal")
        try:
            ws_n = f"{v_dj}_관람예약" if v_dj != "야간" else "야간_관람예약"
            v_data = sheet.worksheet(ws_n).get_all_values()
            df_c = pd.DataFrame(v_data[1:], columns=["날짜","예약자","중개업소","세대수","동","호수","타입","시간","매니저","비고"])
            df_c['날짜'] = pd.to_datetime(df_c['날짜'])
            today = datetime.now().date()
            df_week = df_c[df_c['날짜'].dt.date >= today].sort_values(by=['날짜', '시간'])
            
            for _, r in df_week.head(10).iterrows():
                with st.container(border=True):
                    st.markdown(f"**📅 {r['날짜'].strftime('%m/%d')} | {r['시간']}**")
                    st.write(f"🏠 {r['동']}동 {r['호수']}호 ({r['예약자']})")
                    if r['비고']: st.caption(f"📝 {r['비고']}")
        except: st.error("일정을 가져올 수 없습니다.")

    # --- ⚙️ 상태 관리 ---
    with tab3:
        st.subheader("매물 상태 즉시 변경")
        u_dj = st.selectbox("단지 선택", ["1단지", "2단지", "3단지"], key="m_udj")
        u_f = df_total[df_total["단지"]==u_dj]
        if not u_f.empty:
            ud = st.selectbox("동", sorted(u_f["동"].unique()))
            uh = st.selectbox("호수", sorted(u_f[u_f["동"]==ud]["호수"].unique()))
            curr = u_f[(u_f["동"]==ud) & (u_f["호수"]==uh)].iloc[0]
            st.info(f"현재 상태: {curr['거래여부']}")
            new_s = st.radio("상태 변경", ["관람가능", "거래완료"], horizontal=True)
            if st.button("💾 즉시 반영", use_container_width=True):
                ws = sheet.worksheet(f"{u_dj}_{curr['거래유형']}")
                for i, r in enumerate(ws.get_all_values()):
                    if r[2] == ud and r[3] == uh:
                        ws.update_cell(i+1, 9, new_s)
                        break
                st.success("변경 완료!")
                st.cache_data.clear()
                st.rerun()
