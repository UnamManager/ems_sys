import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, datetime
from st_aggrid import AgGrid, GridOptionsBuilder

# ------------------------------
# 구글 시트 인증
# ------------------------------
import json
import os

scope = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]

creds_dict = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT"])

creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("EMS")
# =========================
# CSS UI 업그레이드
# =========================
st.markdown("""
<style>
.main {
    background-color: #f4f7fa;
}
.sidebar .sidebar-content {
    background-color: #002b45;
    color: white;
}
div.stButton > button {
    background-color: #004c7a;
    color: white;
    border-radius: 8px;
    height: 3em;
}
.card {
    background-color:white;
    padding:15px;
    border-radius:10px;
    box-shadow:0px 2px 8px rgba(0,0,0,0.1);
    margin-bottom:10px;
}
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='text-align:center;color:#002b45;'>🏢 EMS 매물등록관리시스템</h1>", unsafe_allow_html=True)

# ------------------------------
# 메뉴
# ------------------------------
menu = ["통합 대시보드", "매물 조회", "세대관람 예약", "세대관람 현황표", "관리자 관리페이지"]
choice = st.sidebar.selectbox("메뉴 선택", menu)

# ------------------------------
# 데이터 로드 캐싱
# ------------------------------
@st.cache_data(show_spinner=False)
def load_sheet_data(sheets_to_load, columns):
    df_list = []
    for s in sheets_to_load:
        ws = sheet.worksheet(s)
        data = ws.get_all_values()
        df = pd.DataFrame(data[1:], columns=columns) if len(data) > 1 else pd.DataFrame(columns=columns)
        df["단지"] = s.split("_")[0]
        df["거래유형"] = s.split("_")[1]
        df_list.append(df)
    return pd.concat(df_list, ignore_index=True)

sheets_to_load = ["1단지_매매","1단지_임대","2단지_매매","2단지_임대","3단지_매매","3단지_임대"]
columns = ["NO.","분양구분","동","호수","타입","매물구분","매매가","월세","거래여부"]
df_total = load_sheet_data(sheets_to_load, columns)

# ------------------------------
# 1️⃣ 통합 대시보드
# ------------------------------
if choice == "통합 대시보드":
    단지_filter = st.multiselect("단지", df_total["단지"].unique(), default=df_total["단지"].unique())
    분양_filter = st.multiselect("분양구분", df_total["분양구분"].unique(), default=df_total["분양구분"].unique())
    매물_filter = st.multiselect("매물구분", df_total["매물구분"].unique(), default=df_total["매물구분"].unique())
    거래_filter = st.multiselect("거래여부", df_total["거래여부"].unique(),
                                  default=["관람가능"] if "관람가능" in df_total["거래여부"].unique() else df_total["거래여부"].unique())
    df_filtered = df_total[
        (df_total["단지"].isin(단지_filter)) &
        (df_total["분양구분"].isin(분양_filter)) &
        (df_total["매물구분"].isin(매물_filter)) &
        (df_total["거래여부"].isin(거래_filter))
    ]
    gb = GridOptionsBuilder.from_dataframe(df_filtered)
    gb.configure_pagination(paginationAutoPageSize=True)
    AgGrid(df_filtered, gridOptions=gb.build(), enable_enterprise_modules=False, height=500)

# ------------------------------
# 2️⃣ 매물 조회
# ------------------------------
elif choice == "매물 조회":
    단지 = st.selectbox("단지 선택", ["1단지","2단지","3단지"])
    분양구분 = st.selectbox("분양구분 선택", ["조합","일반"])
    거래유형 = st.selectbox("매매/임대 선택", ["매매","임대"])
    ws = sheet.worksheet(f"{단지}_{거래유형}")
    data = ws.get_all_values()
    df = pd.DataFrame(data[1:], columns=columns) if len(data) > 1 else pd.DataFrame(columns=columns)
    AgGrid(df,height=400)

# ------------------------------
# 3️⃣ 세대관람 예약 (완전 업그레이드)
# ------------------------------
elif choice == "세대관람 예약":

    단지 = st.selectbox("단지 선택", ["1단지","2단지","3단지"])

    ws_day = sheet.worksheet(f"{단지}_관람예약")
    ws_night = sheet.worksheet("야간_관람예약")

    with st.form("reservation_form"):

        예약자 = st.text_input("예약자")
        연락처 = st.text_input("연락처")
        관람세대수 = st.selectbox("관람 세대 수", [1,2,3])

        세대목록 = []
        오류여부 = False

        for i in range(관람세대수):

            cols = st.columns(3)

            동 = cols[0].text_input(f"{i+1}번째 동", key=f"d{i}")
            호수 = cols[1].text_input(f"{i+1}번째 호수", key=f"h{i}")

            타입 = ""
            거래상태 = ""

            if 동 and 호수:
                match = df_total[
                    (df_total["단지"]==단지) &
                    (df_total["동"]==동) &
                    (df_total["호수"]==호수)
                ]

                if not match.empty:
                    타입 = match.iloc[0]["타입"]
                    거래상태 = match.iloc[0]["거래여부"]

                    if 거래상태 == "거래완료":
                        cols[2].error("거래완료 매물")
                        오류여부 = True
                    else:
                        cols[2].success(f"타입: {타입}")
                else:
                    cols[2].error("매물 없음")
                    오류여부 = True

            세대목록.append({"동":동,"호수":호수,"타입":타입})

        중개업소 = st.text_input("중개업소")
        동행매니저 = st.text_input("동행매니저")
        비고 = st.text_input("비고")

        예약시간 = st.selectbox(
            "예약시간",
            [f"{h:02d}:00~{h+1:02d}:00" for h in range(8,21)]
        )

        submit = st.form_submit_button("예약 등록")

        if submit:

            if 오류여부:
                st.error("예약 불가한 세대가 포함되어 있습니다.")
            else:

                target_ws = ws_day if int(예약시간[:2]) < 16 else ws_night
                기존데이터 = target_ws.get_all_values()

                for 세대 in 세대목록:

                    # 🔥 중복예약 체크
                    중복 = False
                    for row in 기존데이터:
                        if (
                            row[0] == date.today().strftime("%Y-%m-%d") and
                            row[4] == 세대["동"] and
                            row[5] == 세대["호수"] and
                            row[7] == 예약시간
                        ):
                            중복 = True
                            break

                    if 중복:
                        st.warning(f"{세대['동']}동 {세대['호수']}호 이미 예약됨")
                        continue

                    new_row = [
                        date.today().strftime("%Y-%m-%d"),
                        예약자,
                        중개업소,
                        f"{관람세대수}세대",
                        세대["동"],
                        세대["호수"],
                        세대["타입"],
                        예약시간,
                        동행매니저,
                        비고
                    ]

                    target_ws.append_row(new_row)

                st.success("✅ 예약 완료!")

# ------------------------------
# 4️⃣ 세대관람 예약현황표
# ------------------------------
elif choice == "세대관람 예약현황표":
    선택단지 = st.selectbox("단지 선택", ["1단지","2단지","3단지","야간"])
    선택날짜 = st.date_input("날짜 선택", date.today())
    all_data = []
    columns_res = ["예약날짜","예약자","중개업소","관람세대수","동","호수","타입","예약시간","동행매니저","비고"]
    target_sheets = [f"{선택단지}_관람예약"] if 선택단지 != "야간" else ["야간_관람예약"]
    for ws_name in target_sheets:
        ws = sheet.worksheet(ws_name)
        data = ws.get_all_values()
        df = pd.DataFrame(data[1:], columns=columns_res) if len(data) > 1 else pd.DataFrame(columns=columns_res)
        all_data.append(df)
    if all_data:
        df_all = pd.concat(all_data, ignore_index=True)
        df_filtered = df_all[df_all["예약날짜"] == 선택날짜.strftime("%Y-%m-%d")]
        for idx,row in df_filtered.iterrows():
            st.markdown(f"""
            <div style='border:1px solid #003366;padding:10px;margin:5px;border-radius:5px;background-color:#e6f2ff'>
            <b>{row['예약자']}</b> | {row['관람세대수']} | {row['동']}동 {row['호수']}호 | {row['타입']} | {row['예약시간']}<br>
            중개업소: {row['중개업소']} | 동행매니저: {row['동행매니저']} | 비고: {row['비고']}
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("예약 데이터 없음")

# ------------------------------
# 5️⃣ 관리자 관리페이지 (완전 업그레이드)
# ------------------------------
elif choice == "관리자 관리페이지":

    if "admin_auth" not in st.session_state:
        st.session_state.admin_auth = False

    if not st.session_state.admin_auth:
        pwd = st.text_input("관리자 비밀번호", type="password")
        if pwd == "ems0952":
            st.session_state.admin_auth = True
            st.rerun()
        else:
            st.stop()

    st.subheader("관리자 관리페이지")

    단지_sel = st.selectbox("단지 선택", ["1단지","2단지","3단지"])
    동_sel = st.text_input("동 입력")
    호수_sel = st.text_input("호수 입력")

    if 동_sel and 호수_sel:

        match = df_total[
            (df_total["단지"]==단지_sel) &
            (df_total["동"]==동_sel) &
            (df_total["호수"]==호수_sel)
        ]

        if not match.empty:

            row = match.iloc[0]

            st.info(f"""
            분양구분: {row['분양구분']}
            타입: {row['타입']}
            매물구분: {row['매물구분']}
            거래유형: {row['거래유형']}
            현재상태: {row['거래여부']}
            """)

            new_status = st.selectbox(
                "관람 여부 변경",
                ["관람가능","거래완료"],
                index=0 if row["거래여부"]=="관람가능" else 1
            )

            if st.button("저장"):

                ws = sheet.worksheet(f"{단지_sel}_{row['거래유형']}")
                data = ws.get_all_values()

                for idx, r in enumerate(data):
                    if r[2]==동_sel and r[3]==호수_sel:
                        ws.update_cell(idx+1, 9, new_status)
                        break

                st.success("✅ 변경 완료")
                st.cache_data.clear()
                st.rerun()

        else:
            st.error("해당 매물 없음")