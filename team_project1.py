# app.py
# ============================================================
# 요구사항:
#  - 첫 화면: 좌측(미리보기), 우측(카카오 계정 안내 + 버튼)
#  - 카카오 연동 시: 복원 이력 남김
#  - 연동 안 할 시: 바로 복원 기능만 제공
#  - st.columns() 기반에서도 좌/우 컬럼 높이 동일하게 보이기
# ============================================================

import streamlit as st
from streamlit_image_comparison import image_comparison

st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

# ------------------------------[ 세션 상태 관리 ]------------------------------
if "kakao_logged_in" not in st.session_state:
    st.session_state.kakao_logged_in = False
if "skip_login" not in st.session_state:
    st.session_state.skip_login = False
if "history" not in st.session_state:
    st.session_state.history = []

# ------------------------------[ CSS ]------------------------------
# 포인트
# - st.columns 내부를 flex로 강제 → 동일 높이
# - .column-box: 각 컬럼 콘텐츠 래퍼 (높이 100%, 세로 중앙)
# - 우측 패널(.right-panel)과 버튼 스타일(.btn-kakao / .btn-guest)
st.markdown(
    """
    <style>
    .main-container {
        max-width: 900px;
        margin: auto;
    }

    /* st.columns: 내부를 flex로 바꿔 같은 높이로 맞춤 */
    [data-testid="stHorizontalBlock"] { align-items: stretch !important; }
    [data-testid="stHorizontalBlock"] [data-testid="column"] { display: flex; }
    [data-testid="stHorizontalBlock"] [data-testid="column"] > div {
        flex: 1;
        display: flex;
        flex-direction: column;
    }

    /* 각 컬럼 실제 컨텐츠 래퍼 */
    .column-box {
        flex: 1;
        display: flex;
        flex-direction: column;
        justify-content: center;  /* 필요 없으면 지워도 됨 */
        height: 100%;
        min-height: 420px;        /* 이미지비율에 따라 조절 */
    }

    /* 우측 안내 카드 */
    .right-panel {
        border: 2px dashed #ff99cc;
        border-radius: 20px;
        background: #fff0f5;
        padding: 24px;
        display: flex;
        flex-direction: column;
        gap: 14px;
        align-items: stretch;
        justify-content: center;
        text-align: center;
    }

    /* 그라데이션 안내 텍스트 */
    .notice {
        font-size: 14px;
        font-weight: 700;
        margin: 0 0 6px 0;
        background: linear-gradient(90deg, orange, hotpink);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }

    /* 공통: 버튼을 컨테이너 너비에 맞춤 */
    .right-panel .stButton > button {
        width: 100%;
        padding: 14px 16px;
        font-size: 15px;
        font-weight: 700;
        border-radius: 999px;
        cursor: pointer;
    }

    /* 메인(핑크) 버튼 */
    .btn-kakao .stButton > button {
        background: #ff4fa2;
        border: none;
        color: #fff;
    }

    /* 보더(고스트) 버튼 */
    .btn-guest .stButton > button {
        background: transparent;
        border: 2px solid #ff4fa2;
        color: #ff4fa2;
    }

    /* 제목/본문 간격 */
    .main-container h1 { margin: 0 0 12px; }
    .main-container p  { margin: 0 0 28px; line-height: 1.6; }
    </style>
    """,
    unsafe_allow_html=True
)

# ------------------------------[ 헤더 타이틀 ]------------------------------
st.markdown(
    """
    <div class="main-container">
        <div style="text-align:center; padding:10px 0;">
            <h1>오래된 사진 복원 : AI로 온라인 사진 복원</h1>
            <p>온라인에서 빠르고 쉬운 복원을 경험하세요. 손상/흐릿함 제거, 색과 디테일 복원.</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

# ------------------------------[ 첫 화면 조건 분기 ]------------------------------
if not st.session_state.kakao_logged_in and not st.session_state.skip_login:
    # 좌/우 비율: 1:1 (좌측을 더 넓게 원하면 [3,2] 등으로 변경)
    left_col, right_col = st.columns([1, 1], gap="large")

    # 좌측: 미리보기
    with left_col:
        st.markdown('<div class="column-box">', unsafe_allow_html=True)
        # 이미지가 없을 때를 대비한 가드(선택)
        try:
            image_comparison(
                img1="before.png",  # 원본
                img2="after.png",   # 복원본
                label1="Before",
                label2="After",
            )
        except Exception as e:
            st.info("샘플 이미지를 찾을 수 없습니다. `before.png` / `after.png`를 프로젝트 루트에 두세요.")
        st.markdown('</div>', unsafe_allow_html=True)

    # 우측: 안내 + 실제 동작하는 버튼(세션 상태 변경)
    with right_col:
        st.markdown('<div class="column-box">', unsafe_allow_html=True)
        st.markdown('<div class="right-panel">', unsafe_allow_html=True)

        # 안내 텍스트 (그라데이션)
        st.markdown(
            """
            <p class="notice">
                카카오톡 계정을 연동하면 복원된 이미지 데이터를<br/>
                복원 기록으로 남겨 언제든지 다운받으세요!
            </p>
            """,
            unsafe_allow_html=True
        )

        # 메인 버튼 (카카오 계정 사용하기)
        st.markdown('<div class="btn-kakao">', unsafe_allow_html=True)
        kakao_clicked = st.button("카카오톡 계정 사용하기", key="btn_kakao", use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # 세컨더리 버튼 (게스트 이용)
        st.markdown('<div class="btn-guest">', unsafe_allow_html=True)
        guest_clicked = st.button("계정 연동없이 사용하기", key="btn_guest", use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)   # /right-panel
        st.markdown('</div>', unsafe_allow_html=True)   # /column-box

        # 버튼 클릭 → 세션 상태 변경
        if kakao_clicked:
            st.session_state.kakao_logged_in = True
            st.session_state.history.append("✅ 카카오 연동 완료")
            st.rerun()
        if guest_clicked:
            st.session_state.skip_login = True
            st.rerun()

# ------------------------------[ 로그인 했거나, 연동 안하고 넘어간 경우 ]------------------------------
else:
    st.subheader("복원 기능 실행 화면")

    if st.session_state.kakao_logged_in:
        st.success("카카오 계정 연동됨 ✅ 복원 이력이 기록됩니다.")
        # 간단한 이력 표시
        if st.session_state.history:
            st.write("📜 복원 이력:")
            for item in st.session_state.history:
                st.write("- ", item)

    if st.session_state.skip_login:
        st.warning("계정 연동 없이 이용 중입니다. 복원 이력이 저장되지 않습니다.")

    # ---- 여기에 실제 복원 기능 ----
    uploaded = st.file_uploader("이미지 업로드", type=["png", "jpg", "jpeg"])
    if uploaded is not None:
        # TODO: 여기에 실제 복원 모델 호출/후처리 연결
        st.image(uploaded, caption="업로드된 원본", use_column_width=True)
        st.info("여기에 복원 결과를 표시합니다. (모델 연결 예정)")
        # 예: 기록 로깅 (로그인 사용자만)
        if st.session_state.kakao_logged_in:
            st.session_state.history.append("🛠️ 복원 작업 수행")