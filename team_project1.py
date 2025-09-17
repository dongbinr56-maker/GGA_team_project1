# app.py
# ============================================================
# 요구사항:
#  - 첫 화면: 좌측(미리보기), 우측(카카오 계정 안내 + 버튼)
#  - 카카오 연동 시: 복원 이력 남김
#  - 연동 안 할 시: 바로 복원 기능만 제공
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

# ------------------------------[ CSS: Tailwind 느낌 레이아웃 ]------------------------------
st.markdown(
    """
    <style>
    .main-container {
        max-width: 900px;
        margin: auto;
    }

    /* flex 컨테이너 */
    .flex-container {
        display: flex;
        flex-direction: column;
        gap: 24px;
        margin-top: 2rem;
    }
    @media (min-width: 768px) {
        .flex-container {
            flex-direction: row;
            justify-content: space-between;
            align-items: stretch; /* 좌우 컬럼 같은 높이 */
            gap: 40px;
        }
    }

    /* st.columns 강제로 stretch */
    [data-testid="stHorizontalBlock"] {
        align-items: stretch !important;
    }
    [data-testid="stHorizontalBlock"] [data-testid="column"] {
        display: flex;
    }
    [data-testid="stHorizontalBlock"] [data-testid="column"] > div {
        flex: 1;
        display: flex;
        flex-direction: column;
    }

    /* 좌/우 박스 */
    .left-box, .right-box {
        flex: 1;
    }
    .right-box {
        max-width: 360px;
        border: 2px dashed #ff99cc;
        border-radius: 20px;
        background: #fff0f5;
        padding: 30px;
        text-align: center;
        display: flex;
        flex-direction: column;
        justify-content: center;
        height: 100%;
    }
    .right-box {
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }

    /* 제목/본문 간격 */
    .main-container h1 {
        margin-bottom: 24px;
    }
    .main-container p {
        margin-bottom: 40px;
    }
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
    # ===== 좌/우 나누기 =====
    # ===== 좌/우 나누기 =====
    left_col, right_col = st.columns([1, 1], gap="large")
    
    # 좌측: 미리보기
    with left_col:
        st.markdown('<div class="column-box">', unsafe_allow_html=True)
        image_comparison(
            img1="before.png",  # 원본
            img2="after.png",   # 복원본
            label1="Before",
            label2="After",
        )
        st.markdown('</div>', unsafe_allow_html=True)
    # 우측: 카카오 안내 + 업로드 + 버튼  (네 긴 HTML 그대로 둠)
    with right_col:
    
        st.markdown('<div class="column-box">', unsafe_allow_html=True)
        st.markdown(
            """
            <div style="
                border:2px dashed #ff99cc;
                border-radius:20px;
                padding:30px;
                text-align:center;
                background:#fff0f5;">
    
            <!-- 안내 멘트 -->
            <p style="
                font-size:14px;
                font-weight:bold;
                margin-bottom:20px;
                background: linear-gradient(90deg, orange, hotpink);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;">
                카카오톡 계정을 연동하면 복원된 이미지 데이터를 <br>
                복원 기록으로 남겨 언제든지 다운받으세요!</p>
    
            <!-- 카카오 계정 버튼 -->
            <button style="
                width: 100%;
                padding: 14px;
                border: none;
                border-radius: 999px;
                background: #ff4fa2;
                color: white;
                font-size: 15px;
                font-weight: bold;
                cursor: pointer;
                margin-bottom: 14px;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;"
                onclick="window.location.reload()">
                <img src="https://developers.kakao.com/assets/img/about/logos/kakaotalk-symbol-yellow.png" 
                alt="kakao" style="width:20px; height:20px; border-radius:4px;">
                카카오톡 계정 사용하기
            </button>
    
            <!-- 계정 연동 없이 버튼 -->
            <button style="
                width: 100%;
                padding: 14px;
                border: 2px solid #ff4fa2;
                border-radius: 999px;
                background: transparent;
                color: #ff4fa2;
                font-size: 15px;
                font-weight: bold;
                cursor: pointer;" onclick="window.location.reload()">
                계정 연동없이 사용하기
            </button>
            </div>
            """,
            unsafe_allow_html=True
        )
        st.markdown('</div>', unsafe_allow_html=True)
        
        #st.markdown('</p></div></div>', unsafe_allow_html=True)

        # 업로드 박스 느낌으로 감싸기
        #st.markdown(
        #    """
        #    <div style="
        #        border:2px dashed #ccc;
        #        border-radius:20px;
        #        padding:20px;
        #        text-align:center;
        #        margin:16px 0;
        #        background:#fff;
        #    ">
        #        <p style="font-size:15px; color:#555; margin-bottom:8px;">이미지를 여기로 끌어다 놓으세요</p>
        #    </div>
        #    """,
        #    unsafe_allow_html=True
        #)
        #<div style = "border:2px dashed #ccc; border - radius : 20 px;padding : 20 px;text - align: center;margin : 16 px 0;background: #fff;">
        #<p style="font-size:15px; color:#555; margin-bottom:8px;">이미지를 여기로 끌어다 놓으세요</p>
        #uploaded_file = st.file_uploader("이미지 업로드", type=["png", "jpg", "jpeg"], label_visibility="collapsed")

#        # 버튼 2개 나란히
#        col1, col2 = st.columns(2, gap="small")
#        with col1:
#            if st.button("카카오 계정 연동"):
#                st.session_state.kakao_logged_in = True
#                st.session_state.history.append("📌 복원 작업 #1")
#                st.rerun()
#        with col2:
#            if st.button("계정 연동 없이 이용하기"):
#                st.session_state.skip_login = True
#                st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)


# ------------------------------[ 로그인 했거나, 연동 안하고 넘어간 경우 ]------------------------------
else:
    st.subheader("복원 기능 실행 화면")

    if st.session_state.kakao_logged_in:
        st.success("카카오 계정 연동됨 ✅ 복원 이력이 기록됩니다.")
        st.write("📜 복원 이력:")
        for item in st.session_state.history:
            st.write(item)

    if st.session_state.skip_login:
        st.warning("계정 연동 없이 이용 중입니다. 복원 이력이 저장되지 않습니다.")

    # ---- 여기에 실제 복원 기능 ----
    st.write("👉 여기에 이미지 업로드 & 복원 결과 표시 기능 구현 예정")
