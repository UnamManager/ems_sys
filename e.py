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

# =========================
# 📊 데이터 로드 및 정렬 로직
# =========================
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# ⚠️ 파일명 대문자 "EMS" 연결
try:
    sheet = client.open("EMS")
except gspread.exceptions.SpreadsheetNotFound:
    st.error("🚨 구글 시트 'EMS' 파일을 찾을 수 없습니다. 대문자 파일명과 공유 권한을 확인해주세요.")
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
                
                # 숫자 변환 (콤마 제거 후 변환)
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

# --- 🎨 UI 스타일 함수 ---
def apply_final_style(df, columns):
    df_styled = df.copy()
    rename_dict = {'매매가': '매매가/임대보증금 (만원)'}
    df_styled['매매가'] = df_styled['매매가_num']
    df_styled['월세'] = df_styled['월세_num']
    df_display = df_styled[columns].rename(columns=rename_dict)
    
    return df_display.style.applymap(
        lambda val: f'background-color: {"#d4edda" if val == "관람가능" else "#f8d7da" if val == "거래완료" else "white"}',
        subset=['거래여부']
    ).format({'매매가/임대보증금 (만원)': '{:,.0f}', '월세': '{:,.0f}'})

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

# --- 1번 메뉴: 실시간 매물 현황 ---
if choice == "📊 실시간 매물 현황":
    st.title("📊 실시간 매물 현황 및 시세")
    
    # 1. 상단 메트릭
    c1, c2, c3 = st.columns(3)
    c1.metric("📌 전체 관리 매물", f"{len(df_total)}개")
    c2.metric("✅ 완료 매물", f"{len(df_total[df_total['거래여부'] == '거래완료'])}개")
    c3.metric("🏠 관람 가능 매물", f"{len(df_total[df_total['거래여부'] == '관람가능'])}개")
    st.divider()

    # 2. 단지별 시세 대시보드 (거래완료 제외)
    st.subheader("💰 단지별 실시간 시세 (거래완료 제외, 단위: 만원)")
    tabs = st.tabs(["1단지 시세", "2단지 시세", "3단지 시세"])
    
    for i, tab in enumerate(tabs):
        danji_name = f"{i+1}단지"
        with tab:
            col_m, col_j = st.columns(2)
            # 거래완료가 아닌 매물만 필터링
            df_active = df_total[df_total["거래여부"] != "거래완료"]
            
            # 매매 통계
            df_m = df_active[(df_active["단지"] == danji_name) & (df_active["거래유형"] == "매매") & (df_active["매매가_num"] > 0)]
            with col_m:
                st.markdown(f"**🏠 {danji_name} 매매**")
                if not df_m.empty:
                    m_min, m_max, m_avg = df_m["매매가_num"].min(), df_m["매매가_num"].max(), df_m["매매가_num"].mean()
                    cc1, cc2, cc3 = st.columns(3)
                    cc1.metric("최저", f"{m_min:,.0f}")
                    cc2.metric("최고", f"{m_max:,.0f}")
                    cc3.metric("평균", f"{m_avg:,.0f}")
                else: st.info("매물이 없습니다.")

            # 전세 통계 (매물구분이 '전세'인 것만)
            df_j = df_active[(df_active["단지"] == danji_name) & (df_active["거래유형"] == "임대") & (df_active["매물구분"] == "전세") & (df_active["매매가_num"] > 0)]
            with col_j:
                st.markdown(f"**📑 {danji_name} 전세**")
                if not df_j.empty:
                    j_min, j_max, j_avg = df_j["매매가_num"].min(), df_j["매매가_num"].max(), df_j["매매가_num"].mean()
                    cc1, cc2, cc3 = st.columns(3)
                    cc1.metric("최저", f"{j_min:,.0f}")
                    cc2.metric("최고", f"{j_max:,.0f}")
                    cc3.metric("평균", f"{j_avg:,.0f}")
                else: st.info("매물이 없습니다.")

    st.divider()
    # 최근 완료 매물
    st.subheader("📋 완료 매물 리스트")
    df_done = df_total[df_total["거래여부"] == "거래완료"].copy()
    if not df_done.empty:
        done_cols = ["분양구분", "동", "호수", "타입", "매물구분", "매매가", "월세", "거래여부", "비고"]
        st.dataframe(apply_final_style(df_done, done_cols), use_container_width=True, hide_index=True)

# --- 2번 메뉴: 등록 매물 조회 ---
elif choice == "🔍 등록 매물 조회":
    st.title("🔍 등록 매물 조회")
    f1, f2, f3, f4 = st.columns(4)
    s_danji = f1.multiselect("단지", df_total["단지"].unique())
    s_bunyang = f2.multiselect("분양구분", df_total["분양구분"].unique())
    s_gubun = f3.multiselect("매물구분", df_total["매물구분"].unique())
    s_type = f4.multiselect("타입", sorted(df_total["타입"].unique()))
    
    # ✅ 동/호수 개별 정확 매칭 검색
    st.markdown("---")
    c1, c2, _ = st.columns([1, 1, 2])
    search_dong = c1.text_input("🏢 동 검색 (정확히 입력)")
    search_ho = c2.text_input("🔑 호수 검색 (정확히 입력)")
    
    df_v = df_total.copy()
    if s_danji: df_v = df_v[df_v["단지"].isin(s_danji)]
    if s_bunyang: df_v = df_v[df_v["분양구분"].isin(s_bunyang)]
    if s_gubun: df_v = df_v[df_v["매물구분"].isin(s_gubun)]
    if s_type: df_v = df_v[df_v["타입"].isin(s_type)]
    
    # 문자열 비교로 정확 매칭
    if search_dong: df_v = df_v[df_v["동"] == search_dong]
    if search_ho: df_v = df_v[df_v["호수"] == search_ho]
    
    main_cols = ["분양구분", "동", "호수", "타입", "매물구분", "매매가", "월세", "거래여부", "비고"]
    st.dataframe(apply_final_style(df_v, main_cols), use_container_width=True, hide_index=True)

# --- 3번 메뉴: 관리자 모드 --- (이하 형의 원본 코드와 동일)
elif choice == "🔐 관리자 모드":
    if not st.session_state.admin_auth:
        pwd = st.text_input("관리자 인증", type="password")
        if pwd == ADMIN_PASSWORD:
            st.session_state.admin_auth = True
            st.rerun()
        st.stop()
    
    tab1, tab2, tab3 = st.tabs(["📅 세대관람 예약", "📊 세대관람 현황", "⚙️ 관람 가능여부 관리"])
    # ... (기존 예약/현황/상세관리 로직)
    # [생략된 관리자 모드 코드는 형의 원본 코드를 그대로 붙여넣으시면 됩니다.]
