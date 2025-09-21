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
            # ===== Hero 영역 (로그인 시 버튼 감춤) =====
            st.markdown(
                '<div class="left-stack">'
                '<div class="hero-title">오래된 사진 복원 :<br> <span class="em">AI로 온라인 사진 복원</span></div>'
                '<div class="hero-sub">바랜 사진 속 미소가 다시 빛나고, 잊힌 장면들이 생생하게 살아납니다.</div>'
                '</div>',
                unsafe_allow_html=True
            )

            with st.sidebar:
                profile = st.session_state["kakao_profile"]
                nickname, img = extract_profile(profile)

                st.markdown(f"""
                <style>
                
                section[data-testid="stSidebar"] {{
                    width: 320px !important;
                    background-color: #f9f9f9;
                    padding: 1px 3px 15px 15px; /* 위쪽 패딩 줄임 */
                }}
                .sidebar-row {{
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    margin-top: 0;   /* 위쪽 여백 제거 */
                }}
                .sidebar-row img {{
                    border-radius: 50%;
                    width: 40px;
                    height: 40px;
                    object-fit: cover;
                }}
                .sidebar-row span {{
                    font-size: 1rem;
                    font-weight: 600;
                }}
                .sidebar-row button {{
                    margin-left: auto;
                    padding: 2px 8px;      /* 버튼 패딩 줄임 */
                    font-size: 0.8rem;     /* 글자 크기 줄임 */
                    border: 1px solid #ccc;
                    border-radius: 4px;    /* 둥근 모서리 작게 */
                    background-color: white;
                    cursor: pointer;
                }}
                </style>

                <div class="sidebar-row">
                    <img src="{img}" alt="profile"/>
                    <span>{nickname}</span>
                    <form action="?logout=1" method="get">
                        <button type="submit">로그아웃</button>
                    </form>
                </div>
                """, unsafe_allow_html=True)

                # 쿼리 파라미터 확인해서 로그아웃 처리
                query_params = st.query_params
                if "logout" in query_params:
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

# =====================[ 사진 복원 기능 + 워크플로우 (추가 블록) ]=====================
# ⚠️ 기존 team_project1.py 내용은 절대 수정하지 않고, 이 블록만 파일 맨 하단에 추가하세요.

# --- 추가 임포트(중복 무관) ---
from typing import Dict, Optional
from datetime import datetime
from PIL import ImageFilter, ImageOps
import textwrap
import io
import hashlib

# --- 세션 상태 생성/유지: 복원 컨텍스트 ---
def ensure_restoration_state() -> Dict:
    """
    복원 작업 전반을 추적하는 세션 상태를 초기화/반환합니다.
    - upload_digest: 업로드 파일의 SHA1(업로드 변경 감지)
    - original_bytes: 원본 이미지 바이트
    - current_bytes: 현재 단계 결과 이미지 바이트
    - counts: 각 작업의 실행 횟수(반복 허용시 3회까지)
    - history: 단계별 결과 스냅샷 목록
    - story: 스토리 텍스트/메타
    """
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
        }
    return st.session_state.restoration

# --- 바이트<->PIL 변환 유틸 ---
def image_from_bytes(data: bytes) -> Image.Image:
    """업로드 바이트 → PIL.Image (EXIF 회전 교정 + RGB)"""
    image = Image.open(io.BytesIO(data))
    image = ImageOps.exif_transpose(image)
    return image.convert("RGB")

def image_to_bytes(image: Image.Image) -> bytes:
    """PIL.Image → PNG 바이트"""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()

# --- 복원 알고리즘(샘플 자리표시자) ---
def colorize_image(image: Image.Image) -> Image.Image:
    """
    흑백 이미지를 간단 팔레트로 컬러라이즈(샘플).
    실제 모델(DeOldify 등)로 교체 예정인 자리표시자.
    """
    gray = image.convert("L")
    colorized = ImageOps.colorize(gray, black="#1e1e1e", white="#f8efe3", mid="#88a6c6")
    return colorized.convert("RGB")

def upscale_image(image: Image.Image) -> Image.Image:
    """해상도 2배 업스케일(ESRGAN 대체 샘플)"""
    w, h = image.size
    return image.resize((w * 2, h * 2), Image.LANCZOS)

def denoise_image(image: Image.Image) -> Image.Image:
    """노이즈 제거(NAFNet 대체 샘플: MedianFilter + SMOOTH_MORE)"""
    smoothed = image.filter(ImageFilter.MedianFilter(size=3))
    return smoothed.filter(ImageFilter.SMOOTH_MORE)

# --- 상태/히스토리 도우미 ---
def format_status(counts: Dict[str, int]) -> str:
    return (
        f"[컬러화 {'✔' if counts['color'] else '✖'} / "
        f"해상도 {counts['upscale']}회 / 노이즈 {counts['denoise']}회]"
    )

def add_history_entry(label: str, image_bytes: bytes, note: Optional[str] = None):
    r = ensure_restoration_state()
    entry = {
        "label": label,
        "bytes": image_bytes,
        "status": dict(r["counts"]),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "note": note,
    }
    r["history"].append(entry)
    r["current_bytes"] = image_bytes

def reset_restoration(upload_digest: str, original_bytes: bytes, photo_type: str, description: str):
    r = ensure_restoration_state()
    r.update(
        {
            "upload_digest": upload_digest,
            "original_bytes": original_bytes,
            "photo_type": photo_type,
            "description": description,
            "current_bytes": original_bytes,
            "counts": {"color": 0, "upscale": 0, "denoise": 0, "story": 0},
            "history": [],
            "story": None,
        }
    )

# --- 스토리 생성(샘플) ---
def build_story(description: str, counts: Dict[str, int], photo_type: str) -> str:
    base = description.strip() or "이 사진"
    lines = []
    lines.append(f"{base}은(는) 조심스럽게 복원 과정을 거치고 있습니다.")
    if photo_type == "흑백":
        if counts["color"]:
            lines.append("흑백으로 남아 있던 순간에 색을 덧입히자 잊혔던 온기와 공기가 되살아났습니다.")
        else:
            lines.append("아직 색을 입히지 못한 채 시간 속에서 기다리고 있습니다.")
    if counts["upscale"]:
        lines.append(f"세부 묘사를 살리기 위해 해상도 보정을 {counts['upscale']}회 반복하며 윤곽을 또렷하게 다듬었습니다.")
    if counts["denoise"]:
        lines.append(f"잡음 정리도 {counts['denoise']}회 진행되어 표정과 배경이 한층 차분해졌습니다.")
    lines.append("복원된 이미지를 바라보는 지금, 사진 속 이야기가 현재의 우리에게 말을 건네는 듯합니다.")
    lines.append("이 장면이 전하고 싶은 메시지가 있다면, 그것은 기억을 계속 이어가자는 마음일지도 모릅니다.")
    return "\n\n".join(textwrap.fill(x, width=46) for x in lines)

# --- 자동 컬러화(흑백 업로드 시 1회 자동) ---
def handle_auto_colorization(photo_type: str):
    r = ensure_restoration_state()
    if photo_type != "흑백" or r["counts"]["color"]:
        return
    original = image_from_bytes(r["current_bytes"])
    colorized = colorize_image(original)
    r["counts"]["color"] += 1
    bytes_data = image_to_bytes(colorized)
    r["story"] = None
    add_history_entry("컬러 복원 (자동)", bytes_data, note="흑백 이미지를 기본 팔레트로 색보정했습니다.")

# --- 실행 가능한지 체크(반복 허용시 최대 3회) ---
def can_run_operation(operation: str, allow_repeat: bool) -> bool:
    r = ensure_restoration_state()
    cnt = r["counts"].get(operation, 0)
    return (cnt < 3) if allow_repeat else (cnt == 0)

# --- 버튼 액션 ---
def run_upscale():
    r = ensure_restoration_state()
    img = image_from_bytes(r["current_bytes"])
    out = upscale_image(img)
    r["counts"]["upscale"] += 1
    r["story"] = None
    add_history_entry("해상도 업", image_to_bytes(out), note="ESRGAN 대체 알고리즘(샘플)으로 2배 업스케일했습니다.")

def run_denoise():
    r = ensure_restoration_state()
    img = image_from_bytes(r["current_bytes"])
    out = denoise_image(img)
    r["counts"]["denoise"] += 1
    r["story"] = None
    add_history_entry("노이즈 제거", image_to_bytes(out), note="NAFNet 대체 필터(샘플)로 노이즈를 완화했습니다.")

def run_story_generation():
    r = ensure_restoration_state()
    text = build_story(r["description"], r["counts"], r["photo_type"])
    r["counts"]["story"] += 1
    r["story"] = {
        "text": text,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": dict(r["counts"]),
    }

# --- (선택) 섹션용 CSS: 타이틀/리드문 스타일만 최소 추가 ---
st.markdown("""
<style>
.section-title{ font-size:1.85rem; font-weight:800; color:#111827; margin:28px 0 8px; }
.section-lead{ font-size:1rem; color:#4b5563; margin-bottom:18px; }
.stButton button{
  border-radius:12px; padding:10px 16px; font-weight:700; border:none;
  background:linear-gradient(120deg, #ec4899, #f97316); color:#fff;
}
</style>
""", unsafe_allow_html=True)

# --- 앵커(히어로 버튼이 여기로 스크롤) ---
# (그대로 유지) 앵커
st.markdown("<div id='restore-app'></div>", unsafe_allow_html=True)

# 1) CSS: 이 블록을 앵커 다음에 넣기
st.markdown("""
<style>
/* 이 제목만 확실히 잡아 패딩 크게 */
#restore-title { padding: 10rem 0 10px !important; margin-top: 0 !important; }
</style>
""", unsafe_allow_html=True)
_nick = None
if "kakao_profile" in st.session_state:
    try:
        _nick, _ = extract_profile(st.session_state["kakao_profile"])
    except Exception:
        _nick = None
st.markdown("<div style='height: 10rem'></div>", unsafe_allow_html=True)
# 2) 제목 렌더링: st.title 대신 아래 한 줄로 교체
st.markdown("<h1 id='restore-title'>📌 사진 복원 + 스토리 생성</h1>", unsafe_allow_html=True)

st.markdown("<h2 class='section-title'>AI 복원 워크플로우</h2>", unsafe_allow_html=True)
st.markdown("<p class='section-lead'>업로드 → 복원 옵션 실행 → 스토리 생성까지 한 번에.</p>", unsafe_allow_html=True)

if "kakao_token" in st.session_state:
    st.success(f"로그인됨: {(_nick or '카카오 사용자')}")
else:
    st.info("카카오 로그인을 진행하면 복원 내역이 세션에 보존됩니다. (게스트 모드도 체험 가능)")

rstate = ensure_restoration_state()

with st.container():
    st.subheader("1. 사진 업로드")
    photo_type = st.radio("사진 유형", ["흑백", "컬러"], horizontal=True, key="photo_type_selector")
    description = st.text_input("사진에 대한 간단한 설명", key="photo_description", placeholder="예: 1970년대 외할아버지의 결혼식")
    uploaded_file = st.file_uploader("사진 파일 업로드", type=["png","jpg","jpeg","bmp","tiff"], key="photo_uploader")

    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        digest = hashlib.sha1(file_bytes).hexdigest()
        if rstate["upload_digest"] != digest:
            reset_restoration(digest, file_bytes, photo_type, description)
            # 업로드 즉시 current_bytes를 원본으로 설정
            ensure_restoration_state()["current_bytes"] = file_bytes
            # 흑백이면 1회 자동 컬러화
            handle_auto_colorization(photo_type)
        else:
            rstate["description"] = description
            rstate["photo_type"] = photo_type

allow_repeat = st.checkbox("고급 옵션(실험적) - 동일 작업 반복 허용 (최대 3회)")
if allow_repeat:
    st.warning("⚠ 동일 작업 반복은 처리 시간이 길어지거나 이미지 손상을 유발할 수 있습니다.")

if rstate["original_bytes"] is None:
    st.info("사진을 업로드하면 복원 옵션이 활성화됩니다.")
else:
    st.subheader("2. 복원 옵션")
    c1, c2, c3 = st.columns(3)
    with c1:
        can_up = can_run_operation("upscale", allow_repeat)
        if st.button("해상도 업", use_container_width=True, disabled=not can_up):
            run_upscale()
    with c2:
        can_dn = can_run_operation("denoise", allow_repeat)
        if st.button("노이즈 제거", use_container_width=True, disabled=not can_dn):
            run_denoise()
    with c3:
        can_st = can_run_operation("story", allow_repeat)
        if st.button("스토리 생성", use_container_width=True, disabled=not can_st):
            run_story_generation()

    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("원본 이미지")
        st.image(rstate["original_bytes"], use_container_width=True)
        st.caption(format_status({"color": 0, "upscale": 0, "denoise": 0}))

    with col_b:
        st.subheader("복원 결과")
        if rstate["history"]:
            latest = rstate["history"][-1]
            st.image(latest["bytes"], use_container_width=True, caption=latest["label"])
            st.caption(format_status(latest["status"]))
            if latest.get("note"):
                st.markdown(f"*{latest['note']}*")
        else:
            st.info("아직 수행된 복원 작업이 없습니다.")

    if len(rstate["history"]) > 1:
        with st.expander("전체 작업 히스토리"):
            for idx, entry in enumerate(rstate["history"], 1):
                st.markdown(f"**{idx}. {entry['label']}** ({entry['timestamp']})")
                st.image(entry["bytes"], use_container_width=True)
                st.caption(format_status(entry["status"]))
                if entry.get("note"):
                    st.write(entry["note"])
                st.markdown("---")

    if rstate.get("story"):
        st.subheader("스토리")
        info = rstate["story"]
        st.markdown(info["text"])
        st.caption(f"생성 시각: {info['timestamp']} / {format_status(info['status'])}")

st.markdown("---")
st.caption("*DeOldify, ESRGAN, NAFNet 등의 실제 모델 연동을 위한 자리 표시자입니다(현재는 샘플 필터).*")
# ====================[ 추가 블록 끝 ]====================
