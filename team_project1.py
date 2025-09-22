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
AFTER_PATH = Path("after.png")  # 복원 후(컬러) 예시


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
    after = Image.open(AFTER_PATH).convert("RGB")

    # 폭 제한 - 비율 유지
    def shrink(im: Image.Image) -> Image.Image:
        if im.width > max_width:
            h = int(im.height * (max_width / im.width))
            return im.resize((max_width, h))
        return im

    before = shrink(before)
    after = shrink(after)

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
.hero-title{ font-size: 4.5rem; line-height: 1.15; font-weight: 800; letter-spacing: -0.02em; text-align: center;   /* 가운데 정렬 */}
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

  /* ⬇️ 언더라인 제거 + 버튼처럼 중앙 정렬 */
  text-decoration: none !important;
  display: inline-flex; align-items:center; justify-content:center;
}

/* 앵커 상태 전부 무조건 언더라인 제거 */
a.guest-btn:link,
a.guest-btn:visited,
a.guest-btn:hover,
a.guest-btn:active { text-decoration: none !important; }
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

<style>
/* === Sidebar behavior hardening === */
section[data-testid="stSidebar"][aria-expanded="true"] {
  width: 320px !important;            /* keep your custom width only when open */
  background-color: #f9f9f9;
  padding: 16px 14px 24px 14px;
  border-right: 1px solid rgba(0,0,0,0.06);
}
section[data-testid="stSidebar"][aria-expanded="false"] {
  width: 0 !important;                /* fully collapse width */
  min-width: 0 !important;
  padding-left: 0 !important;
  padding-right: 0 !important;
  overflow: hidden !important;
}
/* Make sure the toggle (chevron) is visible & clickable */
[data-testid="collapsedControl"]{
  display: block !important;
  opacity: 1 !important;
  pointer-events: auto !important;
}
</style>


""", unsafe_allow_html=True)

# --- Smooth scroll (global) ---
st.markdown("""
<style>
/* Global smooth scrolling for anchor jumps */
html, body, [data-testid="stAppViewContainer"], .main, .block-container { 
  scroll-behavior: smooth !important; 
}
#page-bottom { scroll-margin-top: 0; }
#restore-app { scroll-margin-top: 24px; }  /* If you ever scroll to restore section */
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
  font-size: 7rem;
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
.main-title span:nth-child(1){ animation-delay: 0.3s; }
.main-title span:nth-child(2){ animation-delay: 0.5s; }
.main-title span:nth-child(3){ animation-delay: 0.7s; }
.main-title span:nth-child(4){ animation-delay: 0.9s; }
.main-title span:nth-child(5){ animation-delay: 1.1s; }
.main-title span:nth-child(6){ animation-delay: 1.3s; }
.main-title span:nth-child(7){ animation-delay: 1.5s; }
.main-title span:nth-child(8){ animation-delay: 0.3s; }

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
  <span>"</span>
  <span>복</span>
  <span>원</span>
  <span>이</span>
  <span> </span>
  <span>되</span>
  <span>.</span>
  <span>"</span>
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
  <img class="hero-img after"  src="{after_b64}" style="clip-path: inset(0 {100 - start}% 0 0);" />
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
    components.html(html, height=height_px + 40)


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
after_b64 = pil_to_data_uri(after_img, fmt="JPEG", quality=90)

# ------------------------------
# [레이아웃] 좌(텍스트) / 우(미리보기)
# ------------------------------
with st.container():
    left_col, right_col = st.columns([0.9, 0.8])

    with left_col:
        # 로그인 성공 여부 확인
        if "kakao_profile" in st.session_state:
            # ===== 로그인됨: CTA 한 개(이미지 복원하러 가기!) =====
            st.markdown(
                '''
                <div class="left-stack">
                    <div class="hero-title">오래된 사진 복원 :<br> <span class="em">AI로 온라인 사진 복원</span></div>
                    <div class="hero-sub">바랜 사진 속 미소가 다시 빛나고, 잊힌 장면들이 생생하게 살아납니다.</div>
                    <div class="btn-wrap">
                        <a href="#c33b860f" class="guest-btn cta-btn" role="button" target="_self">이미지 복원하러 가기!</a>
                    </div>
                </div>
                ''',
                unsafe_allow_html=True
            )

            # (사이드바 프로필 영역은 기존 그대로 유지)
            with st.sidebar:
                profile = st.session_state["kakao_profile"]
                nickname, img = extract_profile(profile)

                # 사이드바 헤더 숨김(필요 시)
                st.markdown("""
                <style>
                  /* 기본 사이드바 헤더 영역 제거 */
                  div[data-testid="stSidebarHeader"] { display: none !important; }
                  section[data-testid="stSidebar"][aria-expanded="true"]{
                    width: 320px !important;
                    background-color: #f9f9f9;
                    padding: 16px 14px 24px 14px;
                    border-right: 1px solid rgba(0,0,0,0.06);
                  }
                  .sb-card{
                    background:#fff; border:1px solid #e5e7eb; border-radius:16px;
                    padding:16px; box-shadow:0 6px 18px -12px rgba(16,24,40,.2);
                    text-align:center;
                  }
                  .sb-avatar{
                    width:96px; height:96px; border-radius:999px; object-fit:cover;
                    border:3px solid #ffe4ef; display:block; margin:0 auto 10px auto;
                  }
                  .sb-name{ font-weight:800; font-size:1.05rem; margin:6px 0 2px; }
                  .sb-id{ color:#6b7280; font-size:.85rem; }
                  .sb-row{ display:flex; gap:8px; margin-top:14px; }
                  .sb-btn{
                    flex:1 1 0; padding:10px 12px; border-radius:10px; font-weight:700;
                    border:1.5px solid #f9a8d4; background:#fff; color:#ec4899; text-decoration:none !important;
                    display:inline-flex; align-items:center; justify-content:center; cursor:pointer;
                  }
                  .sb-btn:hover{ background:#fff5fa; }
                </style>
                """, unsafe_allow_html=True)

                # 안전한 기본값(닉네임/이미지 없을 때 대비)
                display_name = nickname or "카카오 사용자"
                avatar_url = img or "https://raw.githubusercontent.com/encharm/Font-Awesome-SVG-PNG/master/black/png/64/user.png"

                # 프로필 카드
                st.markdown(
                    f"""
                    <div class="sb-card">
                      <img class="sb-avatar" src="{avatar_url}" alt="profile"/>
                      <div class="sb-name">{display_name}</div>
                      <div class="sb-id">카카오 연동 완료</div>
                      <div class="sb-row">
                        <a class="sb-btn" href="?logout=1" target="_self">로그아웃</a>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

        else:
            # ===== 로그인 전: 카카오 + 게스트 두 버튼 =====
            login_url = build_auth_url()
            st.markdown(
                f'''
                <div class="left-stack">
                    <div class="hero-title">오래된 사진 복원 :<br> <span class="em">AI로 온라인 사진 복원</span></div>
                    <div class="hero-sub">바랜 사진 속 미소가 다시 빛나고, 잊힌 장면들이 생생하게 살아납니다.</div>
                    <div class="btn-wrap">
                        <a href="{login_url}" class="kakao-btn cta-btn" role="button" target="_self">카카오 계정으로 계속</a>
                        <a href="#c33b860f" class="guest-btn cta-btn" role="button" target="_self">게스트 모드로 먼저 체험하기</a>
                    </div>
                </div>
                ''',
                unsafe_allow_html=True
            )

            # 로그인 전엔 사이드바 숨김 (기존 유지)
            with right_col:
                render_compare(before_b64, after_b64, start=50, height_px=hero_h)
# --- 게스트 모드 버튼 클릭 시 복원 섹션으로 스무스 스크롤 ---
st.markdown("""
<script>
(function () {
  function scrollToRestore() {
    var t = document.getElementById('restore-app')
         || document.getElementById('restore-title');
    if (!t) { window.location.hash = '#restore-app'; return; }
    try { t.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
    catch (e) { window.location.hash = '#restore-app'; }
  }

  function bindGuestBtn() {
    var btns = document.querySelectorAll('button.guest-btn');
    btns.forEach(function (b) {
      if (b.dataset.bound === '1') return;
      b.dataset.bound = '1';
      b.addEventListener('click', function (e) {
        e.preventDefault();
        scrollToRestore();
      });
    });
  }

  // 초기 + 재렌더 대비
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindGuestBtn);
  } else {
    bindGuestBtn();
  }
  new MutationObserver(bindGuestBtn).observe(document.body, { childList: true, subtree: true });
})();
</script>
""", unsafe_allow_html=True)

# =====================[ 사진 복원 기능 + 워크플로우 (추가 블록) ]=====================
# ⚠️ 기존 team_project1.py 내용은 절대 수정하지 않고, 이 블록만 파일 맨 하단에 추가하세요.

# =====================[ 사진 복원 기능 + 워크플로우 (정돈본) ]====================
# ⚠ 기존 파일의 위쪽(Hero/로그인/비교 UI)은 절대 수정하지 말고,
#   맨 아래에 이 블록만 한 번 넣으세요.

from typing import Dict, Optional
from datetime import datetime
from PIL import Image, ImageFilter, ImageOps
import textwrap
import io
import hashlib
import base64
import streamlit as st

# ---------- 세션 상태 ----------
def ensure_restoration_state() -> Dict:
    if "restoration" not in st.session_state:
        st.session_state.restoration = {
            "upload_digest": None,
            "original_bytes": None,
            "photo_type": None,
            "description": "",
            "current_bytes": None,
            "counts": {"color": 0, "upscale": 0, "denoise": 0, "story": 0},
            "history": [],
            "story": None,
            "file_name": None,  # 업로드 파일명
        }
    return st.session_state.restoration

# ---------- 바이트 ↔ PIL ----------
def image_from_bytes(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image = ImageOps.exif_transpose(image)
    return image.convert("RGB")

def image_to_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()

# ---------- 복원 알고리즘(샘플 자리표시자) ----------
def colorize_image(image: Image.Image) -> Image.Image:
    gray = image.convert("L")
    return ImageOps.colorize(gray, black="#1e1e1e", white="#f8efe3", mid="#88a6c6").convert("RGB")

def upscale_image(image: Image.Image) -> Image.Image:
    w, h = image.size
    return image.resize((w * 2, h * 2), Image.LANCZOS)

def denoise_image(image: Image.Image) -> Image.Image:
    return image.filter(ImageFilter.MedianFilter(3)).filter(ImageFilter.SMOOTH_MORE)

# ---------- 상태/히스토리 ----------
def format_status(c: Dict[str, int]) -> str:
    return f"[컬러화 {'✔' if c['color'] else '✖'} / 해상도 {c['upscale']}회 / 노이즈 {c['denoise']}회]"

def add_history_entry(label: str, image_bytes: bytes, note: Optional[str] = None) -> None:
    r = ensure_restoration_state()
    entry = {
        "label": label,
        "bytes": image_bytes,
        "status": dict(r["counts"]),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "file_name": r.get("file_name"),
        "note": note,
    }
    r["history"].append(entry)
    r["current_bytes"] = image_bytes

def reset_restoration(upload_digest: str, original_bytes: bytes, photo_type: str, description: str, file_name: str) -> None:
    r = ensure_restoration_state()
    r.update({
        "upload_digest": upload_digest,
        "original_bytes": original_bytes,
        "photo_type": photo_type,
        "description": description,
        "current_bytes": original_bytes,
        "counts": {"color": 0, "upscale": 0, "denoise": 0, "story": 0},
        "history": [],
        "story": None,
        "file_name": file_name,
    })

# ---------- 스토리 ----------
def build_story(description: str, counts: Dict[str, int], photo_type: str) -> str:
    base = (description or "").strip() or "이 사진"
    lines = [f"{base}은(는) 조심스럽게 복원 과정을 거치고 있습니다."]
    if photo_type == "흑백":
        if counts["color"]:
            lines.append("흑백으로 남아 있던 순간에 색을 덧입히자 잊혔던 온기와 공기가 되살아났습니다.")
        else:
            lines.append("아직 색을 입히지 못한 채 시간 속에서 기다리고 있습니다.")
    if counts["upscale"]:
        lines.append(f"세부 묘사를 살리기 위해 해상도 보정을 {counts['upscale']}회 반복했습니다.")
    if counts["denoise"]:
        lines.append(f"잡음 정리 과정도 {counts['denoise']}회 진행되었습니다.")
    lines.append("복원된 이미지를 바라보는 지금, 사진 속 이야기가 현재의 우리에게 말을 건네는 듯합니다.")
    lines.append("이 장면이 전하고 싶은 메시지가 있다면, 그것은 기억을 계속 이어가자는 마음일지도 모릅니다.")
    return "\n\n".join(textwrap.fill(x, width=46) for x in lines)

def handle_auto_colorization(photo_type: str) -> None:
    r = ensure_restoration_state()
    if photo_type != "흑백" or r["counts"]["color"]:
        return
    img = image_from_bytes(r["current_bytes"])
    out = colorize_image(img)
    r["counts"]["color"] += 1
    add_history_entry("컬러 복원 (자동)", image_to_bytes(out), note="흑백 이미지를 기본 팔레트로 색보정했습니다.")
    r["story"] = None

def can_run_operation(op: str, allow_repeat: bool) -> bool:
    r = ensure_restoration_state()
    cnt = r["counts"].get(op, 0)
    return (cnt < 3) if allow_repeat else (cnt == 0)

# ---------- 버튼 액션(하드가드 포함: 고급옵션 OFF면 1회 제한) ----------
def run_upscale() -> None:
    allow_repeat = st.session_state.get("allow_repeat", False)
    if not can_run_operation("upscale", allow_repeat):
        return
    r = ensure_restoration_state()
    img = image_from_bytes(r["current_bytes"])
    out = upscale_image(img)
    r["counts"]["upscale"] += 1
    r["story"] = None
    add_history_entry("해상도 업", image_to_bytes(out), note="ESRGAN 대체 알고리즘(샘플)으로 2배 업스케일했습니다.")

def run_denoise() -> None:
    allow_repeat = st.session_state.get("allow_repeat", False)
    if not can_run_operation("denoise", allow_repeat):
        return
    r = ensure_restoration_state()
    img = image_from_bytes(r["current_bytes"])
    out = denoise_image(img)
    r["counts"]["denoise"] += 1
    r["story"] = None
    add_history_entry("노이즈 제거", image_to_bytes(out), note="NAFNet 대체 필터(샘플)로 노이즈를 완화했습니다.")

def run_story_generation() -> None:
    r = ensure_restoration_state()
    text = build_story(r["description"], r["counts"], r["photo_type"])
    r["counts"]["story"] += 1
    r["story"] = {
        "text": text,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": dict(r["counts"]),
    }
    # ✅ 생성 직후 페이지 하단(스토리 섹션)으로 스크롤 플래그
    st.session_state["scroll_to_story"] = True
# ---------- 섹션 CSS ----------
st.markdown(
    """
    <style>
    .col-title { text-align:center; margin:0 0 10px; }
    .img-cap { text-align:center; color:#6b7280; font-size:0.9rem; margin-top:6px; }
    .history-row { display:flex; gap:16px; overflow-x:auto; padding:4px 2px; }
    .history-card { flex:0 0 auto; width:280px; border:1px solid #e5e7eb; border-radius:12px; padding:8px; background:#fff; }
    .history-card img { width:100%; border-radius:8px; display:block; }
    .history-title { font-weight:700; font-size:0.95rem; margin:6px 0 2px; }
    .history-meta { color:#6b7280; font-size:0.8rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- 앵커 & 제목 ----------

# === Busy overlay & cursor (loading indicator) ===
_busy_ph = st.empty()  # overlay placeholder

st.markdown("""
<style>
body.busy, body.busy * { cursor: progress !important; }
#busy-mask {
  position: fixed; inset: 0;
  background: rgba(255,255,255,.65);
  backdrop-filter: saturate(1.1) blur(2px);
  display: flex; align-items: center; justify-content: center;
  z-index: 9999;
}
#busy-mask .box { display:flex; flex-direction:column; align-items:center; }
#busy-mask .ring {
  width: 56px; height: 56px; border-radius: 999px;
  border: 4px solid #f9a8d4; border-top-color:#ec4899;
  animation: busy-rot .9s linear infinite;
}
#busy-mask .msg { margin-top: 10px; font-weight: 700; color:#ec4899; }
@keyframes busy-rot { to { transform: rotate(360deg); } }
</style>
""", unsafe_allow_html=True)

def busy_on(msg: str = "처리 중…"):
    _busy_ph.markdown(
        f"""
        <div id="busy-mask">
          <div class="box">
            <div class="ring"></div>
            <div class="msg">{msg}</div>
          </div>
        </div>
        <script>document.body.classList.add('busy');</script>
        """,
        unsafe_allow_html=True,
    )

def busy_off():
    _busy_ph.empty()
    st.markdown("<script>document.body.classList.remove('busy');</script>", unsafe_allow_html=True)

st.markdown("<div id='restore-app'></div>", unsafe_allow_html=True)
st.markdown("<div style='height: 10rem'></div>", unsafe_allow_html=True)
st.markdown("<h1 id='restore-title'>📌 사진 복원 + 스토리 생성</h1>", unsafe_allow_html=True)

# ---------- 업로드 ----------
rstate = ensure_restoration_state()
with st.container():
    st.subheader("1. 사진 업로드")
    photo_type = st.radio("사진 유형", ["흑백", "컬러"], horizontal=True, key="photo_type_selector")
    description = st.text_input("사진에 대한 간단한 설명", key="photo_description", placeholder="예: 1970년대 외할아버지의 결혼식")
    uploaded_file = st.file_uploader("사진 파일 업로드", type=["png", "jpg", "jpeg", "bmp", "tiff"], key="photo_uploader")

    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        digest = hashlib.sha1(file_bytes).hexdigest()
        if rstate["upload_digest"] != digest:
            reset_restoration(digest, file_bytes, photo_type, description, uploaded_file.name)
            ensure_restoration_state()["current_bytes"] = file_bytes
            handle_auto_colorization(photo_type)
        else:
            rstate["description"] = description
            rstate["photo_type"] = photo_type

# ---------- 옵션 ----------
allow_repeat = st.checkbox("고급 옵션(실험적) - 동일 작업 반복 허용 (최대 3회)", key="allow_repeat")
if allow_repeat:
    st.warning("⚠ 동일 작업 반복은 처리 시간이 길어지거나 이미지 손상을 유발할 수 있습니다.")

if rstate["original_bytes"] is None:
    st.info("사진을 업로드하면 복원 옵션이 활성화됩니다.")
else:
    st.subheader("2. 복원 옵션")
    c1, c2, c3 = st.columns(3)
    with c1:
        can_up = can_run_operation("upscale", allow_repeat)
        if st.button("해상도 업", key="btn_upscale", use_container_width=True, disabled=not can_up):
            run_upscale()
    with c2:
        can_dn = can_run_operation("denoise", allow_repeat)
        if st.button("노이즈 제거", key="btn_denoise", use_container_width=True, disabled=not can_dn):
            run_denoise()
    with c3:
        if st.button("스토리 생성", key="btn_story", use_container_width=True):
            run_story_generation()

    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("<h3 class='col-title'>원본 이미지</h3>", unsafe_allow_html=True)
        st.image(rstate["original_bytes"], use_container_width=True)
        st.markdown(f"<div class='img-cap'>{format_status({'color':0,'upscale':0,'denoise':0})}</div>", unsafe_allow_html=True)

    with col_b:
        st.markdown("<h3 class='col-title'>복원 결과</h3>", unsafe_allow_html=True)
        if rstate["history"]:
            latest = rstate["history"][-1]
            st.image(latest["bytes"], use_container_width=True, caption=latest["label"])
            st.markdown(f"<div class='img-cap'>{format_status(latest['status'])}</div>", unsafe_allow_html=True)
            if latest.get("note"):
                st.markdown(f"*{latest['note']}*")
        else:
            st.info("아직 수행된 복원 작업이 없습니다.")

    # ---------- 전체 작업 히스토리: 파일명 기준 가로 나열 ----------
    if len(rstate["history"]) > 1:
        with st.expander("전체 작업 히스토리"):
            groups: Dict[str, list] = {}
            for e in rstate["history"]:
                fname = e.get("file_name") or rstate.get("file_name") or "현재 업로드"
                groups.setdefault(fname, []).append(e)

            for fname, entries in groups.items():
                st.markdown(f"**{fname}**")
                cards_html = []
                for e in entries:
                    b64 = base64.b64encode(e["bytes"]).decode("ascii")
                    uri = f"data:image/png;base64,{b64}"
                    title = e["label"]
                    meta = f"{e['timestamp']} · {format_status(e['status'])}"
                    card = ('<div class="history-card">'
                           f'<img src="{uri}" alt="{title}"/>'
                           f'<div class="history-title">{title}</div>'
                           f'<div class="history-meta">{meta}</div>'
                           '</div>')
                    cards_html.append(card)
                row_html = "<div class='history-row'>" + "".join(cards_html) + "</div>"
                st.markdown(row_html, unsafe_allow_html=True)

    # ---------- 스토리 ----------
    # ---------- 스토리 ----------
    if rstate.get("story"):
        st.subheader("스토리")
        info = rstate["story"]

        # 맨 아래 스크롤 앵커
        st.markdown('<div id="story-bottom"></div>', unsafe_allow_html=True)

        import base64, html

        orig_bytes = rstate["original_bytes"]
        last_bytes = (rstate["history"][-1]["bytes"] if rstate["history"] else rstate["current_bytes"] or orig_bytes)

        b64_orig = base64.b64encode(orig_bytes).decode("ascii")
        b64_last = base64.b64encode(last_bytes).decode("ascii")
        fname = (rstate.get("file_name") or "image").rsplit("/", 1)[-1]
        dn_orig = f"original_{fname}".replace(" ", "_")
        dn_last = f"restored_{fname}".replace(" ", "_")

        lane_html = f"""
        <style>
          .story-lane {{
            display:flex; gap:16px; align-items:flex-start; margin-top:8px;
            overflow-x:auto; padding:8px 2px;
          }}
          .story-card, .story-img {{
            border:1px solid #e5e7eb; border-radius:12px; background:#fff;
          }}
          .story-card {{
            flex: 1 1 50%; padding:14px; min-width: 320px; white-space:pre-wrap; line-height:1.6;
          }}
          .story-img {{
            flex: 0 0 340px; text-decoration:none; color:inherit; padding:10px; text-align:center;
          }}
          .story-img img {{ width:100%; border-radius:8px; display:block; }}
          .story-img .dl {{ margin-top:6px; font-size:.9rem; color:#6b7280; }}
        </style>
        <div class="story-lane">
          <div class="story-card">{html.escape(info["text"]).replace("\n", "<br>")}</div>
          <a class="story-img" href="data:image/png;base64,{b64_orig}" download="{dn_orig}">
            <img src="data:image/png;base64,{b64_orig}" alt="원본 이미지"/>
            <div class="dl">원본 다운로드</div>
          </a>
          <a class="story-img" href="data:image/png;base64,{b64_last}" download="{dn_last}">
            <img src="data:image/png;base64,{b64_last}" alt="복원 이미지"/>
            <div class="dl">복원본 다운로드</div>
          </a>
        </div>
        """
        st.markdown(lane_html, unsafe_allow_html=True)

if st.session_state.get("scroll_to_story"):
    st.markdown("""
    <script>
      const t = document.getElementById('story-bottom');
      if (t) t.scrollIntoView({behavior:'smooth', block:'start'});
    </script>
    """, unsafe_allow_html=True)
    st.session_state["scroll_to_story"] = False
st.markdown("---")
st.caption("*DeOldify, ESRGAN, NAFNet 등의 실제 모델 연동을 위한 자리 표시자입니다(현재는 샘플 필터).*")
st.markdown("<div style='height: 15rem'></div>", unsafe_allow_html=True)

# =====================[ 추가 블록 끝 ]====================
st.markdown("<div id='#c33b860f'></div>", unsafe_allow_html=True)
