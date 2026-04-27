import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, date, timedelta, timezone
import json
import uuid
import time

# =========================
st.set_page_config(page_title="EMS 마스터 관리 시스템", layout="wide")
ADMIN_PASSWORD_MANAGE = "unam0119" 

# 스타일 정의 (보류 상태 색상 추가)
st.markdown("""
    <style>
    [data-testid="stElementToolbar"] { display: none !important; }
    .stButton>button { width: 100%; height: 3em; border-radius: 8px; font-weight: bold; }
    .section-box { border: 2px solid #4A90E2; padding: 25px; border-radius: 12px; background-color: #ffffff; margin-bottom: 25px; box-shadow: 2px 2px 10px rgba(0,0,0,0.05); }
    .admin-header { color: #4A90E2; font-weight: bold; border-left: 5px solid #4A90E2; padding-left: 10px; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

if "admin_logged_in" not in st.session_state:
    st.title("⚙️ EMS 마스터 로그인")
    pw_in = st.text_input("관리자 전용 코드를 입력하세요", type="password")
    if st.button("관리자 인증"):
        if pw_in == ADMIN_PASSWORD_MANAGE:
            st.session_state.admin_logged_in = True; st.rerun()
        else: st.error("❌ 코드가 올바르지 않습니다.")
    st.stop()

# =========================
@st.cache_resource(ttl=3600)
def get_ems_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open("EMS")

sheet = get_ems_sheet()
TIME_SLOTS = ["10:00 ~ 10:45", "11:00 ~ 11:45", "13:00 ~ 13:45", "14:00 ~ 14:45", "15:00 ~ 15:45", "16:00 ~ 16:45", "17:00 ~ 17:45"]

@st.cache_data(ttl=300)
def load_admin_data_all():
    sheets = ["1단지_매매","1단지_임대","2단지_매매","2단지_임대","3단지_매매","3단지_임대"]
    df_list = []
    for s in sheets:
        try:
            ws = sheet.worksheet(s); data = ws.get_all_values()
            if len(data) > 1:
                df = pd.DataFrame(data[1:], columns=["NO.","분양구분","동","호수","타입","매물구분","매매가","월세","거래여부", "비고"])
                df["단지"] = s.split("_")[0]; df["거래유형"] = s.split("_")[1]
                df['temp_no'] = pd.to_numeric(df['NO.'], errors='coerce')
                if not df.empty:
                    top_3_val = df['temp_no'].nlargest(3).min()
                    df['호수'] = df.apply(lambda x: f"🆕 {x['호수']}" if x['temp_no'] >= top_3_val else x['호수'], axis=1)
                df_list.append(df)
        except: continue
    return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()

df_total = load_admin_data_all()

# =========================
st.sidebar.title("🛠️ 관리자 메뉴")
choice = st.sidebar.radio("작업 선택", ["📋 매물 현황 & 관리", "📝 관리자 예약 등록", "📅 통합 예약 현황판", "✂️ 예약 수정/삭제"])
if st.sidebar.button("🔄 데이터 새로고침"): st.cache_data.clear(); st.rerun()

# =========================
# [1] 매물 현황 & 관리 (상태변경에 '보류' 추가)
# =========================
if choice == "📋 매물 현황 & 관리":
    st.title("📋 매물 실시간 현황")
    # ... (상단 요약 생략) ...

    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.markdown('<div class="admin-header">⚙️ 매물 상태 변경</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    a_dj = c1.selectbox("변경 단지 선택", ["1단지", "2단지", "3단지"])
    a_dong = c2.text_input("변경 동 입력")
    a_ho = c3.text_input("변경 호수 입력")

    if a_dong and a_ho:
        target = df_total[(df_total["단지"] == a_dj) & (df_total["동"] == a_dong) & (df_total["호수"].str.contains(a_ho))]
        if not target.empty:
            curr = target.iloc[0]
            with st.form("status_update"):
                st.write(f"현재 선택: **{a_dj} {a_dong}동 {curr['호수']}** (상태: {curr['거래여부']})")
                # --- 보류 선택지 추가 ---
                status_opts = ["관람가능", "거래완료", "보류"]
                curr_idx = status_opts.index(curr["거래여부"]) if curr["거래여부"] in status_opts else 0
                new_s = st.selectbox("변경할 상태", status_opts, index=curr_idx)
                new_n = st.text_input("비고 수정", value=curr["비고"])
                if st.form_submit_button("상태 저장"):
                    ws = sheet.worksheet(f"{a_dj}_{curr['거래유형']}")
                    rows = ws.get_all_values()
                    idx = -1
                    clean_ho = a_ho.replace("🆕 ", "")
                    for i, r in enumerate(rows):
                        if len(r) > 3 and r[2] == a_dong and r[3] == clean_ho: idx = i + 1; break
                    if idx != -1:
                        ws.update(f'I{idx}:J{idx}', [[new_s, new_n]])
                        st.success("✅ 저장 성공!"); st.cache_data.clear(); time.sleep(1); st.rerun()
        else: st.warning("해당 매물을 찾을 수 없습니다.")
    st.markdown('</div>', unsafe_allow_html=True)
    # ... (조회 데이터프레임 생략) ...

# =========================
# [4] 예약 수정/삭제 (고도화 버전)
# =========================
elif choice == "✂️ 예약 수정/삭제":
    st.title("✂️ 예약 정보 고도화 수정")
    col1, col2 = st.columns(2)
    d_date = col1.date_input("날짜 선택", date.today())
    d_dj_short = col2.selectbox("단지 선택", ["1단지", "2단지", "3단지"])
    d_dj = f"{d_dj_short}_관람예약"
    
    ws_mod = sheet.worksheet(d_dj); rows_mod = ws_mod.get_all_values()
    if len(rows_mod) > 1:
        df_mod = pd.DataFrame(rows_mod[1:], columns=rows_mod[0])
        day_mod = df_mod[df_mod["예약날짜"] == d_date.strftime("%Y-%m-%d")]
        
        if not day_mod.empty:
            day_mod = day_mod.sort_values("예약시간")
            opts = [f"[{r['예약시간']}] {r['예약자']} ({r['중개업소']})" for i, r in day_mod.iterrows()]
            sel_text = st.selectbox("수정할 예약건 선택", opts)
            selected_row = day_mod.iloc[opts.index(sel_text)]
            row_idx = int(selected_row.name) + 2 
            
            st.divider()
            # 수정 폼 시작
            with st.form("master_edit_v2"):
                st.subheader("🛠️ 상세 정보 수정")
                
                # 1. 인적 사항 및 시간
                c1, c2, c3 = st.columns(3)
                edit_name = c1.text_input("예약자 성함", value=selected_row['예약자'])
                edit_agency = c2.text_input("중개업소명", value=selected_row['중개업소'])
                edit_time = c3.selectbox("예약 시간대", TIME_SLOTS, index=TIME_SLOTS.index(selected_row['예약시간']))
                
                # 2. 관람 세대 수정 로직
                st.markdown("---")
                # 관람 가능 매물만 필터링 (보류/완료 제외)
                avail_units = df_total[(df_total["단지"] == d_dj_short) & (df_total["거래여부"] == "관람가능")]
                u_dongs = sorted(list(set(avail_units["동"].unique())), key=lambda x: int(x) if x.isdigit() else 0)
                
                edit_count = st.selectbox("관람 세대수", [1, 2], index=0 if "1세대" in selected_row['관람세대수'] else 1)
                
                new_items = []
                for i in range(edit_count):
                    st.write(f"🏠 세대 {i+1} 선택")
                    sc1, sc2 = st.columns(2)
                    sel_d = sc1.selectbox(f"동 선택 ({i+1})", u_dongs, key=f"edit_d_{i}")
                    
                    raw_hos = avail_units[avail_units["동"] == sel_d]["호수"].tolist()
                    clean_hos = sorted(list(set([h.replace("🆕 ", "") for h in raw_hos])), key=lambda x: int(x) if x.isdigit() else 0)
                    sel_h = sc2.selectbox(f"호수 선택 ({i+1})", clean_hos, key=f"edit_h_{i}")
                    
                    match = avail_units[(avail_units["동"] == sel_d) & (avail_units["호수"].str.contains(sel_h))]
                    if not match.empty:
                        new_items.append({"동": sel_d, "호수": sel_h, "타입": match.iloc[0]['타입']})

                edit_memo = st.text_area("비고 수정", value=selected_row['비고'] if '비고' in selected_row else "")

                # 3. 버튼 레이아웃
                b1, b2 = st.columns(2)
                if b1.form_submit_button("💾 수정 내용 저장"):
                    combined_ho = " / ".join([f"{it['동']}동 {it['호수']}호" for it in new_items])
                    combined_type = ", ".join([str(it['타입']) for it in new_items])
                    
                    # 구글 시트 업데이트 (B:예약자, C:업소, D:세대수, E:동호수, F:타입, G:시간, H:비고)
                    update_data = [[
                        edit_name, edit_agency, f"{len(new_items)}세대", 
                        combined_ho, combined_type, edit_time, edit_memo
                    ]]
                    ws_mod.update(f'B{row_idx}:H{row_idx}', update_data)
                    st.success("✅ 예약 정보가 업데이트되었습니다."); st.cache_data.clear(); time.sleep(1); st.rerun()
                
                if b2.form_submit_button("🚨 이 예약 삭제"):
                    ws_mod.delete_rows(row_idx)
                    st.warning("🗑️ 예약이 삭제되었습니다."); st.cache_data.clear(); time.sleep(1); st.rerun()
                    
        else: st.info("선택한 날짜에 예약이 없습니다.")
