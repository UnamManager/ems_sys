import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, datetime, timedelta
from st_aggrid import AgGrid, GridOptionsBuilder
import plotly.express as px
import smtplib  # 📧 이메일 발송용
from email.mime.text import MIMEText
import json
import os

# 페이지 설정
st.set_page_config(page_title="EMS 통합 관리 시스템 v2.5", layout="wide")

# =========================
# 🔐 환경 설정 (이메일 정보)
# =========================
# 구글 앱 비밀번호를 사용해야 합니다 (환경변수에 저장 권장)
EMAIL_SENDER = os.environ.get("EMAIL_ADDR", "your_gmail@gmail.com") 
EMAIL_PASSWORD = os.environ.get("EMAIL_PW", "your_app_password")
ADMIN_RECEIVER = "manager_mail@naver.com" # 알림 받을 메일 주소

def send_email_notification(subject, body):
    """지정한 관리자 메일로 알림 전송"""
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = EMAIL_SENDER
        msg['To'] = ADMIN_RECEIVER

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, ADMIN_RECEIVER, msg.as_string())
        return True
    except Exception as e:
        st.error(f"메일 발송 실패: {e}")
        return False

# --- (데이터 로딩 및 시트 인증 로직은 이전과 동일) ---
# ... [load_all_data 함수 및 기본 설정 생략] ...

# =========================
# 🔐 관리자 모드 - 예약 등록 섹션 수정
# =========================
# [기존 예약 등록 로직 내 'submitted' 부분만 교체]
if choice == "🔐 관리자 모드":
    # ... (생략) ...
    with tab1:
        # ... (폼 구성 생략) ...
        submitted = st.form_submit_button("📅 예약 확정 및 메일 알림 발송")
        
        if submitted:
            if not res_name:
                st.warning("예약자명을 입력해주세요.")
            else:
                # 1. 구글 시트 저장
                target_ws = f"{res_danji}_관람예약" if int(time_val[:2]) < 16 else "야간_관람예약"
                ws = sheet.worksheet(target_ws)
                rows = [[date.today().strftime("%Y-%m-%d"), res_name, "", f"{count}세대", s["동"], s["호수"], s["타입"], time_val, "", memo] for s in res_items]
                ws.append_rows(rows)
                
                # 2. 📧 알림 내용 생성 (메일/팩스용)
                detail_text = "\n".join([f"- {s['동']}동 {s['호수']}호 ({s['타입']})" for s in res_items])
                email_body = f"""
[EMS 관람 예약 알림]
-----------------------
● 예약단지: {res_danji}
● 예약자명: {res_name}
● 관람시간: {time_val}
● 상세내역:
{detail_text}
● 비고: {memo}
-----------------------
본 메일은 시스템에서 자동으로 발송되었습니다.
                """
                
                # 3. 알림 발송
                success = send_email_notification(f"📢 [{res_danji}] 새 예약 등록: {res_name}", email_body)
                
                if success:
                    st.success("✅ 예약 완료 및 관리자 메일 알림이 발송되었습니다.")
                else:
                    st.warning("✅ 예약은 저장되었으나, 메일 알림 발송에 실패했습니다.")
                
                st.cache_data.clear()
