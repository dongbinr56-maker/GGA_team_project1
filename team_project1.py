# app.py
# ============================================================
# "오래된 사진 복원 : AI로 온라인 사진 복원" Hero 섹션 (핑크 배경 제거 / 업로드 UI 제거)
# - 좌측: 타이틀 + 설명문(요구 문구로 교체) + 2개 CTA 버튼(한 벌만, 동일 크기)
# - 우측: Before/After 고정 예시 이미지를 슬라이더로 비교 (오른쪽으로 밀수록 After 더 보임)
# - 외부 의존성: streamlit, pillow(PIL)
# - 이미지 경로: ./assets/before.jpg, ./assets/after.jpg  ← 직접 교체해서 사용
# ============================================================

from typing import Tuple

import streamlit.components.v1 as components
import base64
import io
import os
import time
import hmac
import hashlib
import secrets
from pathlib import Path

import requests
import streamlit as st
from PIL import Image

import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

# ------------------------------
# [설정] 페이지 레이아웃
#  - layout="wide": 가로 폭 넓게
#  - 사이드바는 기본 접힘 상태
# ------------------------------
st.set_page_config(layout="wide", initial_sidebar_state="collapsed")
# ================================
# Kakao OAuth 설정
# ================================
REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "caf4fd09d45864146cb6e75f70c713a1")
REDIRECT_URI = os.getenv("KAKAO_REDIRECT_URI", "https://hackteam32.streamlit.app")
STATE_SECRET = os.getenv("KAKAO_STATE_SECRET", "UzdfMyaTkcNsJ2eVnRoKjUIOvWbeAy5E")

KAKAO_AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
KAKAO_USER_URL = "https://kapi.kakao.com/v2/user/me"


REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "caf4fd09d45864146cb6e75f70c713a1")
REDIRECT_URI = os.getenv("KAKAO_REDIRECT_URI", "https://hackteam32.streamlit.app")
STATE_SECRET = os.getenv("KAKAO_STATE_SECRET", "UzdfMyaTkcNsJ2eVnRoKjUIOvWbeAy5E")
# or os.getenv("OAUTH_STATE_SECRET")
# or (REST_API_KEY or "dev-secret")

AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
USERME_URL = "https://kapi.kakao.com/v2/user/me"
STATE_TTL_SEC = 5 * 60


def _hmac_sha256(key: str, msg: str) -> str:
    return hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest()


def make_state() -> str:
    ts = str(int(time.time()))
    nonce = secrets.token_urlsafe(8)
    raw = f"{ts}.{nonce}"
    sig = _hmac_sha256(STATE_SECRET, raw)
    return f"{raw}.{sig}"


def verify_state(state: str) -> bool:
    if not state or state.count(".") != 2:
        return False
    ts, nonce, sig = state.split(".")
    expected = _hmac_sha256(STATE_SECRET, f"{ts}.{nonce}")
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        ts_i = int(ts)
    except ValueError:
        return False
    if time.time() - ts_i > STATE_TTL_SEC:
        return False
    return True


def build_auth_url() -> str:
    state = make_state()
    return (
        f"{AUTHORIZE_URL}"
        f"?client_id={REST_API_KEY}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&state={state}"
    )


def exchange_code_for_token(code: str) -> dict:
    data = {
        "grant_type": "authorization_code",
        "client_id": REST_API_KEY,
        "redirect_uri": REDIRECT_URI,
        "code": code,
        "client_secret": STATE_SECRET
    }
    response = requests.post(TOKEN_URL, data=data, timeout=10)
    response.raise_for_status()
    return response.json()


def get_user_profile(access_token: str) -> dict:
    response = requests.get(
        USERME_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def extract_profile(user_me: dict):
    account = (user_me or {}).get("kakao_account", {}) or {}
    profile = account.get("profile", {}) or {}
    nickname = profile.get("nickname") or None
    img = profile.get("profile_image_url") or profile.get("thumbnail_image_url") or None
    if not nickname or not img:
        props = (user_me or {}).get("properties", {}) or {}
        nickname = nickname or props.get("nickname")
        img = img or props.get("profile_image") or props.get("thumbnail_image")
    return nickname, img


# ------------------------------[ 2) 콜백/로그아웃 처리 ]------------------------
_query_params = (
    st.query_params if hasattr(st, "query_params") else st.experimental_get_query_params()
)


def _first_param(name: str):
    value = _query_params.get(name)
    return value[0] if isinstance(value, list) and value else value


if _first_param("logout") == "1":
    st.session_state.pop("kakao_token", None)
    st.session_state.pop("kakao_profile", None)
    if hasattr(st, "query_params"):
        st.query_params.clear()
    else:
        st.experimental_set_query_params()
    st.rerun()
error = _first_param("error")
error_description = _first_param("error_description")
code = _first_param("code")
state = _first_param("state")
if error:
    st.error(f"카카오 인증 에러: {error}\n{error_description or ''}")
elif code:
    if not verify_state(state):
        st.error("state 검증 실패(CSRF/만료). 다시 시도해주세요.")
    else:
        try:
            token_json = exchange_code_for_token(code)
            st.session_state.kakao_token = token_json
            st.session_state.kakao_profile = get_user_profile(token_json["access_token"])

            # === 팝업 창이면 토큰을 부모창으로 전달 ===
            st.markdown(f"""
                <script>
                  if (window.opener) {{
                    window.opener.postMessage({{"kakao_token": "{token_json['access_token']}" }}, "*");
                    window.close();
                  }} else {{
                    // fallback: 그냥 현재창 리다이렉트
                    window.location.href = "/";
                  }}
                </script>
                """, unsafe_allow_html=True)

            if hasattr(st, "query_params"):
                st.query_params.clear()
            else:
                st.experimental_set_query_params()
            st.rerun()
        except requests.HTTPError as exc:
            st.exception(exc)

# ------------------------------
# [경로] 예시 이미지 파일 경로 (수정 지점)
#  - 너가 가진 Before/After 샘플로 교체해서 쓰면 됨
# ------------------------------
BEFORE_PATH = Path("before.png")  # 복원 전(흑백) 예시
AFTER_PATH  = Path("after.png")   # 복원 후(컬러) 예시

# ------------------------------
# [유틸] PIL 이미지 → data URI(base64)
#  - HTML <img src="data:..."> 로 바로 박아 넣기 위해 사용
# ------------------------------
def pil_to_data_uri(img: Image.Image, fmt: str = "JPEG", quality: int = 90) -> str:
    buf = io.BytesIO()
    img.save(buf, format=fmt, quality=quality)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    mime = "image/png" if fmt.upper() == "PNG" else "image/jpeg"
    return f"data:{mime};base64,{b64}"

# ------------------------------
# [유틸] 예시 이미지 로드 + 가벼운 리사이즈
#  - 너무 큰 이미지는 성능/메모리 고려해서 폭을 제한
#  - 반환: (before_img, after_img, 추천_높이_px)
# ------------------------------
def load_examples(max_width: int = 300):
    if not BEFORE_PATH.exists() or not AFTER_PATH.exists():
        st.error("예시 이미지가 없습니다. before.jpg, after.jpg 를 넣어주세요.")
        st.stop()

    before = Image.open(BEFORE_PATH).convert("RGB")
    after  = Image.open(AFTER_PATH).convert("RGB")

    # 폭 제한 - 비율 유지
    def shrink(im: Image.Image) -> Image.Image:
        if im.width > max_width:
            h = int(im.height * (max_width / im.width))
            return im.resize((max_width, h))
        return im

    before = shrink(before)
    after  = shrink(after)

    # 미리보기 높이 추정: 가로형 기준으로 300~520 사이에서 적당히 잡음
    est_h = int(after.height * min(1.0, 800 / max(after.width, 1)))  # 폭 900 기준 비율
    est_h = max(300, min(est_h, 520))
    return before, after, est_h

# ------------------------------
# [UI/CSS] 스타일 정의
#  - 핑크 배경 제거(흰 배경 카드)
#  - 왼쪽 영역 '세로 가운데 정렬' (justify-content:center)
#  - 텍스트는 좌측 정렬 유지
#  - 버튼은 '한 벌만' 남기고 동일 크기 보장(고정 높이/최소 폭)
# ------------------------------
st.markdown("""
<style>

/* Streamlit 기본 상단 패딩 제거 */
.block-container {
  padding-top: 0rem !important;
  padding-bottom: 0rem !important;
}
/* 사이드바 및 토글 숨김 */
[data-testid="stSidebar"]{ display:none !important; }
[data-testid="collapsedControl"]{ display:none !important; }

/* 전체 폰트 */
html, body, [class*="css"]{
  font-family: ui-sans-serif, -apple-system, system-ui, "Apple SD Gothic Neo", "Noto Sans KR", "Segoe UI", Roboto, "Helvetica Neue", Arial;
}

.hero-wrap {
  margin-top: 130px;       /* 원하는 상단 여백 */
  padding: 24px 28px;
  background: #ffffff;
  border: 1px solid rgba(15,23,42,0.06);
  border-radius: 24px;
  box-shadow: 0 18px 50px -26px rgba(15,23,42,0.25);
}


/* 2열 그리드 */
.hero-grid{
  display: grid;
  grid-template-columns: minmax(0,1.1fr) minmax(0,0.9fr);
  gap: 42px;
  align-items: stretch;                 /* 양쪽 동일 높이로 늘림 */
}

/* 왼쪽 스택: 세로 가운데 정렬, 좌측 정렬 유지 */
.left-stack{
  display: flex; flex-direction: column;
  justify-content: center;              /* ← 가운데 위치(세로) */
  text-align: left;                     /* ← 텍스트는 좌측 정렬 */
  height: var(--hero-h, 360px);         /* 파이썬에서 동적으로 주입 */
}

/* 타이틀 */
.hero-title{ font-size: 4.8rem; line-height: 1.15; font-weight: 800; letter-spacing: -0.02em; text-align: center;   /* 가운데 정렬 */}
.hero-title .em{ color:#ec4899; }

/* 설명문(요구 문구로 교체) */
.hero-sub{font-family: 'Pretendard', 'Noto Sans KR', sans-serif;
  font-size: 1.2rem;
  color: #444;
  line-height: 3.7;text-align: center;}

/* 버튼 한 벌(동일 크기 보장) */
.btn-wrap {
  display: flex;               /* 버튼을 가로로 나란히 */
  justify-content: center;     /* 가로 가운데 정렬 */
  gap: 16px;                   /* 버튼 사이 여백 */
  margin-top: 24px;            /* 위쪽 공간 */
}

.cta-btn{
  display:inline-flex; align-items:center; justify-content:center;
  height: 48px;                         /* ← 동일 높이 */
  min-width: 240px;                     /* ← 최소 폭統一 */
  padding: 0 18px; border-radius: 12px; font-weight: 800;
  text-decoration:none !important; cursor:pointer;
  border: 2px solid transparent;
  box-shadow: 0 1px 2px rgba(0,0,0,.06);
}

.kakao-btn, .guest-btn {
  background:#fff;
  color:#ec4899 !important;
  border:2px solid #f9a8d4;
  padding:12px 20px;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
}
/* 우측 비교 위젯 컨테이너 */
.compare-wrap{
  position: relative; width:100%;
  border-radius: 18px; overflow: hidden;
  border:1px solid rgba(15,23,42,0.08);
}
.compare-wrap img{
  position:absolute; inset:0; width:100%; height:100%; object-fit:cover;
  user-select:none; -webkit-user-drag:none;
}
.compare-slider{
  -webkit-appearance:none; appearance:none;
  position:absolute; left:5%; right:5%; bottom:12px; height:22px; z-index:30; background:transparent;
}
.compare-slider::-webkit-slider-thumb{
  -webkit-appearance:none; appearance:none; width:22px; height:22px; border-radius:999px;
  background:#111; border:2px solid #fff; box-shadow:0 2px 5px rgba(0,0,0,.25);
}
.compare-slider::-webkit-slider-runnable-track{ height:3px; background:rgba(15,23,42,0.15); border-radius:999px; }
.hero-divider{ position:absolute; top:0; bottom:0; width:2px; background:#fff; mix-blend-mode:difference; z-index:20; }
.badge{ position:absolute; top:12px; padding:6px 10px; border-radius:999px; font-weight:700; font-size:12px; color:#111;
        background:rgba(255,255,255,0.9); border:1px solid rgba(0,0,0,.06); z-index:25; }
.badge.before{ left:12px; } .badge.after{ right:12px; }

@media (max-width: 900px){
  .hero-grid{ grid-template-columns: 1fr; gap:22px; }
  .cta-btn{ min-width: unset; width: 100%; }   /* 모바일에선 버튼이 폭 100%로 */
}
.compare-wrap {
  position: relative;
  width: 100%;
  overflow: hidden;
}
.compare-wrap img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
</style>
""", unsafe_allow_html=True)
st.markdown("""
<style>
/* 1) Streamlit 슬라이더/범용 range 입력, 전역에서 감추기 */
[data-testid="stSlider"],
input[type="range"]{
  display: none !important;
  height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  border: 0 !important;
}

/* 2) 혹시 슬라이더를 감싸는 빈 컨테이너가 남아있으면 공간도 제거 */
.block-container > div:has([data-testid="stSlider"]) {
  display: none !important;
  height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
}

/* 3) 타이틀과 히어로 사이 불필요한 빈 블록 제거(안전장치) */
.block-container > div:empty {
  display: none !important;
}

/* 4) 상단/중앙 여백 최소화(이미 넣어놨더라도 한번 더 확실히) */
.block-container{
  padding-top: 0 !important;
  padding-bottom: 0 !important;
  margin-top: 0 !important;
  margin-bottom: 0 !important;
}
.main-title{ margin: 8px 0 12px 0 !important; }
</style>
""", unsafe_allow_html=True)

# ------------------------------
# [데이터] 예시 이미지 로드
# ------------------------------
before_img, after_img, hero_h = load_examples(max_width=750)
st.markdown("""
<style>

/* ✅ Streamlit 기본 패딩 제거 */
.block-container {
  padding-top: 0rem !important;
  padding-bottom: 0rem !important;
  margin-top: 0rem !important;
  margin-bottom: 0rem !important;
}

/* 전체 폰트 */
html, body, [class*="css"] {
  font-family: ui-sans-serif, -apple-system, system-ui, "Apple SD Gothic Neo", "Noto Sans KR", "Segoe UI", Roboto, "Helvetica Neue", Arial;
}

/* ✅ 메인 타이틀 (애니메이션) */
.main-title {
  font-size: 6rem;
  font-weight: 800;
  text-align: center;
  margin: 10px 0 20px 0;   /* 👈 상단/하단 여백 최소화 */
  line-height: 1.1;
}

.main-title span {
  display: inline-block;
  opacity: 0;
  animation: drop 0.8s ease forwards;
  animation-fill-mode: forwards;
}

/* 애니메이션 효과 */
@keyframes drop {
  0% { transform: translateY(-150px); opacity: 0; }
  60% { transform: translateY(20px); opacity: 1; }
  80% { transform: translateY(-10px); }
  100% { transform: translateY(0); opacity: 1; }
}

/* 각 글자 딜레이 */
.main-title span:nth-child(1){ animation-delay: 0.1s; }
.main-title span:nth-child(2){ animation-delay: 0.3s; }
.main-title span:nth-child(3){ animation-delay: 0.5s; }
.main-title span:nth-child(4){ animation-delay: 0.7s; }
.main-title span:nth-child(5){ animation-delay: 0.9s; }
.main-title span:nth-child(6){ animation-delay: 1.1s; }

/* ✅ Hero 섹션 */
.hero-wrap {
  margin-top: 0px;    /* 👈 위쪽 여백 없앰 */
  padding: 24px 28px;
  background: #ffffff;
  border: 1px solid rgba(15,23,42,0.06);
  border-radius: 24px;
  box-shadow: 0 18px 50px -26px rgba(15,23,42,0.25);
}

</style>
""", unsafe_allow_html=True)
st.markdown("""
<div class="main-title">
  <span>복</span>
  <span>원</span>
  <span>이</span>
  <span> </span>
  <span>되</span>
  <span>.</span>
</div>
""", unsafe_allow_html=True)
st.markdown("""
<style>
[data-baseweb="input"] {
  display: none !important;
  visibility: hidden !important;
  height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  border: 0 !important;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
/* ✅ Streamlit 내부 검색/입력 박스 wrapper까지 싹 없애기 */
[data-testid="stTextInput"] {
  display: none !important;
  visibility: hidden !important;
  height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  border: 0 !important;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
/* ✅ Streamlit 기본 상단/하단 여백 제거 */
.block-container {
  padding-top: 0rem !important;
  padding-bottom: 0rem !important;
  margin-top: 0rem !important;
  margin-bottom: 0rem !important;
}


/* ✅ 불필요한 빈 div 제거 (타이틀과 본문 사이 길다란 박스 방지) */
.block-container > div:empty,
.block-container > div:has([data-testid="stVerticalBlock"]):empty {
  display: none !important;
  height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  border: 0 !important;
}

/* ✅ 메인 타이틀 바로 밑에 자동 생성되는 div 강제 제거 */
.main-title + div {
  display: none !important;
  margin: 0 !important;
  padding: 0 !important;
  height: 0 !important;
}

/* ✅ 본문 영역도 최소 여백만 남기기 */
.hero-wrap {
  margin-top: 0px !important;   /* 👈 위쪽 빈칸 제거 */
  padding-top: 24px;
  padding-bottom: 24px;
}
</style>
""", unsafe_allow_html=True)

# 왼쪽 스택의 높이를 파이썬에서 CSS 변수로 주입 → 세로 가운데 정렬 기준이 됨
st.markdown(f"""
<style>
  .left-stack{{ height:{hero_h}px; }}
</style>
""", unsafe_allow_html=True)

# HTML로 비교 위젯 렌더링 (오른쪽으로 밀면 After↑)
# ------------------------------
# [우측 비교 위젯] Before/After 슬라이더
# ------------------------------

def render_compare(before_b64: str, after_b64: str, start: int = 50, height_px: int = 400):
    html = f"""
<style>

.block-container {{
  padding-top: 0rem !important;
  padding-bottom: 0rem !important;
  margin-top: 0rem !important;
  margin-bottom: 0rem !important;
}}
.compare-wrap {{
  position: relative;
  width: 100%;
  height: {height_px}px;
  overflow: hidden;
  user-select: none;
}}
.compare-wrap img {{
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;

  /* 🛠 드래그/선택 방지 */
  user-select: none;       /* 텍스트/이미지 선택 안되게 */
  -webkit-user-drag: none; /* Safari/Chrome에서 이미지 드래그 방지 */
  pointer-events: none;    /* 마우스 이벤트 막음 (divider만 잡힘) */
}}
.hero-divider {{
  position: absolute;
  top: 0; bottom: 0;
  width: 3px;
  background: #fff;
  mix-blend-mode: difference;
  cursor: ew-resize;
  z-index: 20;
  transition: left 0.12s ease-out;       /* ← 이동 부드럽게 */
}}
.badge {{
  position: absolute;
  top: 12px;
  padding: 4px 8px;
  background: rgba(255,255,255,0.9);
  border-radius: 6px;
  font-weight: 700;
  font-size: 12px;
  z-index: 30;
}}
.badge.before {{ left: 12px; }}
.badge.after  {{ right: 12px; }}
</style>

<div class="compare-wrap" id="compare-box">
  <span class="badge before">Before</span>
  <span class="badge after">After</span>
  <img class="hero-img before" src="{before_b64}" />
  <img class="hero-img after"  src="{after_b64}" style="clip-path: inset(0 {100-start}% 0 0);" />
  <div class="hero-divider" id="divider" style="left:{start}%"></div>
</div>

<script>
(function(){{
  var wrap = document.getElementById("compare-box");
  var afterImg = wrap.querySelector(".hero-img.after");
  var divider  = document.getElementById("divider");
  var dragging = false;
  var lastX = null;

  function updatePos(x) {{
    var rect = wrap.getBoundingClientRect();
    var offsetX = x - rect.left;
    var percent = Math.max(0, Math.min(100, (offsetX / rect.width) * 100));
    afterImg.style.clipPath = "inset(0 " + (100 - percent) + "% 0 0)";
    divider.style.left = percent + "%";
  }}

  function smoothUpdate(x) {{
    lastX = x;
    requestAnimationFrame(function(){{
      if (lastX !== null) {{
        updatePos(lastX);
        lastX = null;
      }}
    }});
  }}

  // 마우스
  wrap.addEventListener("mousedown", function(e) {{
    dragging = true;
    smoothUpdate(e.clientX);
  }});
  document.addEventListener("mouseup", function() {{ dragging = false; }});
  document.addEventListener("mousemove", function(e) {{
    if (!dragging) return;
    smoothUpdate(e.clientX);
  }});

  // 터치
  wrap.addEventListener("touchstart", function(e) {{
    dragging = true;
    smoothUpdate(e.touches[0].clientX);
  }});
  document.addEventListener("touchend", function() {{ dragging = false; }});
  document.addEventListener("touchmove", function(e) {{
    if (!dragging) return;
    smoothUpdate(e.touches[0].clientX);
  }});
}})();
</script>
"""
    components.html(html, height=height_px+40)

st.markdown("""
<style>
/* 1) Streamlit 슬라이더/범용 range 입력, 전역에서 감추기 */
[data-testid="stSlider"],
input[type="range"]{
  display: none !important;
  height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  border: 0 !important;
}

/* 2) 혹시 슬라이더를 감싸는 빈 컨테이너가 남아있으면 공간도 제거 */
.block-container > div:has([data-testid="stSlider"]) {
  display: none !important;
  height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
}

/* 3) 타이틀과 히어로 사이 불필요한 빈 블록 제거(안전장치) */
.block-container > div:empty {
  display: none !important;
}

/* 4) 상단/중앙 여백 최소화(이미 넣어놨더라도 한번 더 확실히) */
.block-container{
  padding-top: 0 !important;
  padding-bottom: 0 !important;
  margin-top: 0 !important;
  margin-bottom: 0 !important;
}
.main-title{ margin: 8px 0 12px 0 !important; }
</style>
""", unsafe_allow_html=True)



# 데이터 URI 변환
before_b64 = pil_to_data_uri(before_img, fmt="JPEG", quality=90)
after_b64  = pil_to_data_uri(after_img,  fmt="JPEG", quality=90)

# ------------------------------
# [레이아웃] 좌(텍스트) / 우(미리보기)
# ------------------------------
with st.container():
    left_col, right_col = st.columns([0.9, 0.8])

    with left_col:
        # 로그인 성공 여부 확인
        if "kakao_profile" in st.session_state:
            # ===== 로그인 상태일 때: 버튼 감춤 =====
            st.markdown(
                '<div class="left-stack">'
                '<div class="hero-title">오래된 사진 복원 :<br> <span class="em">AI로 온라인 사진 복원</span></div>'
                '<div class="hero-sub">바랜 사진 속 미소가 다시 빛나고, 잊힌 장면들이 생생하게 살아납니다.</div>'
                '</div>',
                unsafe_allow_html=True
            )

            # ===== 사이드바 보이게 CSS 수정 =====
            st.markdown("""
            <style>
            /* 사이드바 폭 넓히기 */
            section[data-testid="stSidebar"] {
                width: 320px !important;
                background-color: #f9f9f9;  /* 옅은 배경 */
                padding-top: 20px;
            }

            /* 프로필 영역 중앙 정렬 */
            .sidebar-profile {
                text-align: center;
                margin-top: 10px;
                margin-bottom: 20px;
            }
            .sidebar-profile img {
                border-radius: 50%;
                margin-bottom: 12px;
                box-shadow: 0 2px 6px rgba(0,0,0,0.2);
            }
            .sidebar-profile h3 {
                font-size: 1.2rem;
                font-weight: 700;
                margin-bottom: 16px;
            }
            .sidebar-profile button {
                display: block;
                margin: 0 auto;
            }
            </style>
            """, unsafe_allow_html=True)

            # ===== 사이드바 열기 =====
            with st.sidebar:
                profile = st.session_state["kakao_profile"]
                nickname, img = extract_profile(profile)
                if img:
                    st.image(img, width=80)
                if nickname:
                    st.markdown(f"### {nickname}님 환영합니다 👋")

                if st.button("로그아웃"):
                    st.session_state.pop("kakao_token", None)
                    st.session_state.pop("kakao_profile", None)
                    st.rerun()

        else:
            # ===== 로그인 전: 버튼 보이기 =====
            st.markdown(
                f"""
                <div class="left-stack">
                    <div class="hero-title">오래된 사진 복원 :<br> <span class="em">AI로 온라인 사진 복원</span></div>
                    <div class="hero-sub">바랜 사진 속 미소가 다시 빛나고, 잊힌 장면들이 생생하게 살아납니다.</div>
                    <div class="btn-wrap">
                        <a href="{build_auth_url()}">
                          <button class="kakao-btn">카카오 계정으로 계속</button>
                        </a>
                        <button class="guest-btn">게스트 모드로 먼저 체험하기</button>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            # ===== 로그인 전엔 사이드바 숨김 =====
            st.markdown("""
            <style>
            [data-testid="stSidebar"]{ display:none !important; }
            [data-testid="collapsedControl"]{ display:none !important; }
            </style>
            """, unsafe_allow_html=True)

    with right_col:
        render_compare(before_b64, after_b64, start=50, height_px=hero_h)

