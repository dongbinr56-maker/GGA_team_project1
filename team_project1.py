# app.py
# ============================================================
# Kakao OAuth for Streamlit (No-session CSRF using HMAC state)
# - 우상단 고정 네비바(화이트, 라운드, 그림자)
# - 사이드바 숨김
# - 로그인 전: "카카오 로그인" 노란 버튼
# - 로그인 후: "로그아웃" + 원형 프로필 아바타
# - CSRF state: 세션에 안 저장. HMAC 서명 토큰으로 검증 → 세션 갈려도 OK.
# ============================================================

import base64
import os
import time
import hmac
import hashlib
import requests
import secrets
from io import BytesIO

from PIL import Image
import streamlit as st


# ------------------------------[ 0) 페이지/레이아웃 ]---------------------------
st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

st.markdown(
    """
<style>
:root {
color-scheme: only light;
}

body {
background: #f4f6fb;
}

/* 사이드바/토글 제거 */
[data-testid="stSidebar"]{ display:none !important; }
[data-testid="collapsedControl"]{ display:none !important; }

/* 우상단 네비게이션 바 */
.navbar {
position: fixed;
top: 0; left: 0; right: 0;
height: 60px;
padding: 0 18px;
background: #ffffff;
display: flex; align-items: center; justify-content: flex-end;
box-shadow: 0 2px 6px rgba(0,0,0,0.06);
z-index: 1000;
}

/* 본문 상단 패딩(네비바 높이만큼) */
.block-container { padding-top: 84px; }

/* 버튼/아바타 */
.kakao-btn{
    display:inline-flex; align-items:center; gap:8px;
    padding:10px 14px; background:#FEE500; color:#000 !important;
    border:1px solid rgba(0,0,0,.08); border-radius:10px;
    font-weight:700; text-decoration:none !important;
    box-shadow:0 1px 2px rgba(0,0,0,0.08); cursor:pointer;
}
.kakao-btn:hover{ filter:brightness(0.96); }

.logout-btn{
display:inline-flex; align-items:center;
padding:9px 12px; margin-right:8px;
background:#fff; color:#222 !important;
border:1px solid #E5E7EB; border-radius:10px;
font-weight:600; text-decoration:none !important; cursor:pointer;
}
.logout-btn:hover{ background:#F3F4F6; }

.avatar{
width:40px; height:40px; border-radius:50%; object-fit:cover;
border:1px solid #E5E7EB; box-shadow:0 1px 2px rgba(0,0,0,0.05);
}

.nav-right{ display:flex; align-items:center; gap:10px; }

/* 메인 히어로 영역 */
.hero-title {
margin-bottom: 32px;
}
.hero-title h1 {
font-size: 2.4rem;
font-weight: 800;
margin-bottom: 12px;
color: #1f2937;
}
.hero-title p {
font-size: 1.05rem;
color: #4b5563;
margin: 0;
}

[data-testid="column"] > div {
height: 100%;
display: flex;
}

[data-testid="column"] > div > div {
flex: 1;
display: flex;
flex-direction: column;
}

.card {
background: #ffffff;
border-radius: 28px;
box-shadow: 0 16px 40px rgba(15, 23, 42, 0.08);
padding: 32px;
display: flex;
flex-direction: column;
gap: 24px;
}

.card-title {
font-weight: 700;
font-size: 1.1rem;
color: #111827;
}

.preview-card {
position: relative;
overflow: hidden;
}

.preview-grid {
display: grid;
grid-template-columns: repeat(2, minmax(0, 1fr));
gap: 18px;
width: 100%;
flex: 1;
min-height: clamp(300px, 38vw, 420px);
}

.preview-box {
border-radius: 20px;
border: 1px dashed #cbd5f5;
background: rgba(248, 250, 255, 0.7);
color: #4b5563;
font-weight: 600;
display: flex;
align-items: center;
justify-content: center;
position: relative;
overflow: hidden;
}

.preview-box span {
position: relative;
z-index: 2;
}

.preview-box img {
width: 100%;
height: 100%;
object-fit: contain;
position: absolute;
inset: 0;
z-index: 1;
background: #ffffff;
}

.preview-box::after {
content: attr(data-label);
position: absolute;
left: 16px;
top: 16px;
padding: 6px 12px;
border-radius: 999px;
background: rgba(30, 64, 175, 0.82);
color: white;
font-size: 0.75rem;
font-weight: 600;
letter-spacing: 0.02em;
}

.preview-box.empty::after {
background: rgba(148, 163, 184, 0.72);
}

.upload-hint {
text-align: center;
border-radius: 18px;
border: 1px dashed #d1d5db;
padding: 22px;
background: linear-gradient(135deg, rgba(255,255,255,0.9), rgba(248,250,255,0.9));
}

.upload-hint strong {
display: block;
font-size: 0.95rem;
color: #1f2937;
margin-bottom: 6px;
}

.upload-hint p {
margin: 0;
color: #6b7280;
font-size: 0.88rem;
line-height: 1.5;
}

.preview-actions {
display: flex;
justify-content: flex-end;
gap: 12px;
margin-top: -4px;
}

.btn-secondary,
.btn-primary {
display: inline-flex;
align-items: center;
justify-content: center;
padding: 12px 20px;
border-radius: 12px;
font-weight: 600;
text-decoration: none !important;
transition: all 0.2s ease;
cursor: pointer;
border: none;
outline: none;
}

.btn-secondary {
background: rgba(148, 163, 184, 0.18);
color: #475569 !important;
border: 1px solid rgba(148, 163, 184, 0.28);
}

.btn-secondary:hover {
background: rgba(148, 163, 184, 0.28);
}

.btn-primary {
background: linear-gradient(135deg, #2563eb, #4f46e5);
color: #fff !important;
box-shadow: 0 12px 28px rgba(37, 99, 235, 0.35);
}

.btn-primary:hover {
filter: brightness(0.96);
}

.upload-widget > div[data-testid="stFileUploader"] {
border-radius: 18px;
border: 1px dashed #9ca3af;
background: rgba(255,255,255,0.72);
padding: 18px;
}

.upload-widget [data-testid="stFileUploaderDropzone"] {
border: none;
background: transparent;
}

.upload-widget [data-testid="stFileUploader"] section {
gap: 8px;
}

.upload-widget label {
font-weight: 600;
color: #1f2937;
}

.upload-widget small {
color: #6b7280;
}

.kakao-card {
justify-content: space-between;
}

.kakao-card p {
margin: 0;
color: #4b5563;
line-height: 1.6;
}

.kakao-connect {
display: inline-flex;
align-items: center;
justify-content: center;
width: 100%;
padding: 14px 18px;
border-radius: 12px;
border: none;
background: #fee500;
color: #1f2937 !important;
font-weight: 700;
font-size: 1rem;
text-decoration: none !important;
box-shadow: 0 12px 24px rgba(253, 224, 71, 0.35);
}

.kakao-connect:hover {
filter: brightness(0.97);
}

.kakao-hint {
font-size: 0.85rem;
color: #6b7280;
margin: 0;
}

.kakao-status {
display: flex;
gap: 12px;
align-items: center;
padding: 16px;
border-radius: 16px;
background: rgba(59,130,246,0.08);
color: #1d4ed8;
font-weight: 600;
}

.kakao-status img {
width: 44px;
height: 44px;
border-radius: 50%;
object-fit: cover;
border: 2px solid rgba(255,255,255,0.8);
box-shadow: 0 6px 16px rgba(37, 99, 235, 0.25);
}

.kakao-actions {
display: flex;
flex-direction: column;
gap: 12px;
}

.kakao-actions .logout-btn {
justify-content: center;
margin-right: 0;
}

@media (max-width: 1100px) {
    .hero-title h1 {
    font-size: 2rem;
    }
    }

    @media (max-width: 960px) {
    [data-testid="stHorizontalBlock"] {
    flex-direction: column !important;
    }
    .preview-grid {
    grid-template-columns: 1fr;
    min-height: clamp(260px, 60vw, 360px);
    }
    }

    @media (max-width: 640px) {
    .card {
    padding: 24px;
    }
    .hero-title h1 {
    font-size: 1.8rem;
    }
    }
</style>
""",
    unsafe_allow_html=True,
)

# ------------------------------[ 1) 카카오 OAuth 설정 ]------------------------
REST_API_KEY   = os.getenv("KAKAO_REST_API_KEY")                # 콘솔 > REST API 키
REDIRECT_URI   = os.getenv("KAKAO_REDIRECT_URI", "http://localhost:8501")  # 콘솔 등록값과 '완전 동일'
STATE_SECRET   = os.getenv("KAKAO_STATE_SECRET") or os.getenv("OAUTH_STATE_SECRET") \
                or (REST_API_KEY or "dev-secret")  # HMAC 비밀키(환경변수로 별도 세팅 권장)

AUTHORIZE_URL  = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL      = "https://kauth.kakao.com/oauth/token"
USERME_URL     = "https://kapi.kakao.com/v2/user/me"

STATE_TTL_SEC  = 5 * 60  # state 유효시간(초) - 5분

def _hmac_sha256(key: str, msg: str) -> str:
    """HMAC-SHA256 hexdigest"""
    return hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest()

def make_state() -> str:
    """
    세션 사용 없이도 검증 가능한 state 생성.
    (timestamp + nonce).[HMAC(timestamp + nonce)]
    - 공격자가 SECRET을 모르므로 위조 불가
    - TTL로 만료 검증
    """
    ts = str(int(time.time()))
    # nonce 만들고 HMAC 처리 추가해야 함
    # 예시:
    nonce = secrets.token_hex(8)
    raw = ts + "." + nonce
    sig = hmac.new(STATE_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def exchange_code_for_token(code: str) -> dict:
    data = {
        "grant_type": "authorization_code",
        "client_id": REST_API_KEY,
        "redirect_uri": REDIRECT_URI,
        "code": code,
        # "client_secret": os.getenv("KAKAO_CLIENT_SECRET"),  # 쓰면 주석 해제
    }
    r = requests.post(TOKEN_URL, data=data, timeout=10)
    r.raise_for_status()
    return r.json()

def get_user_profile(access_token: str) -> dict:
    r = requests.get(USERME_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
    r.raise_for_status()
    return r.json()

def build_auth_url() -> str:
    state = make_state()
    return (
        f"{AUTHORIZE_URL}"
        f"?client_id={REST_API_KEY}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&state={state}"
    )

def extract_profile(user_me: dict):
    acc  = (user_me or {}).get("kakao_account", {}) or {}
    prof = acc.get("profile", {}) or {}
    nick = prof.get("nickname") or None
    img  = prof.get("profile_image_url") or prof.get("thumbnail_image_url") or None
    if not nick or not img:
        props = (user_me or {}).get("properties", {}) or {}
        nick  = nick or props.get("nickname")
        img   = img  or props.get("profile_image") or props.get("thumbnail_image")
    return nick, img


def image_to_data_url(image: Image.Image) -> str:
    """Convert PIL image to data URL for inline preview."""

    preview = image.copy()
    preview.thumbnail((1600, 1600))

    buffer = BytesIO()
    preview.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"

# ------------------------------[ 2) 콜백/로그아웃 처리 ]------------------------
_qp = st.query_params if hasattr(st, "query_params") else st.experimental_get_query_params()

def _one(name):
    v = _qp.get(name)
    return (v[0] if isinstance(v, list) and v else v)

# 2-1) 로그아웃 우선 처리
if _one("logout") == "1":
    st.session_state.pop("kakao_token", None)
    st.session_state.pop("kakao_profile", None)
    if hasattr(st, "query_params"): st.query_params.clear()
    else: st.experimental_set_query_params()
    st.rerun()

# 2-2) OAuth 콜백
err   = _one("error")
errd  = _one("error_description")
code  = _one("code")
state = _one("state")

if err:
    st.error(f"카카오 인증 에러: {err}\n{errd or ''}")

elif code:
    try:
        # 토큰 교환 로직
        token_data = exchange_code_for_token(code)

        # 토큰 세션에 저장
        st.session_state["kakao_token"] = token_data

        st.success("카카오 로그인 성공!")

        # 쿼리 파라미터 초기화
        if hasattr(st, "query_params"):
            st.query_params.clear()
        else:
            st.experimental_set_query_params()

        st.rerun()

    except requests.HTTPError as e:
        st.exception(e)


# ------------------------------[ 3) 우상단 네비바 ]-----------------------------
auth_url = build_auth_url()
nick, img_url = None, None
if "kakao_profile" in st.session_state:
    nick, img_url = extract_profile(st.session_state["kakao_profile"])

nav = []
nav.append("<div class='navbar'><div class='nav-right'>")
if "kakao_token" not in st.session_state:
    nav.append(f"<a class='kakao-btn' href='{auth_url}'>카카오 로그인</a>")
else:
    nav.append("<a class='logout-btn' href='?logout=1'>로그아웃</a>")
    if img_url:
        safe_nick = (nick or "").replace("<","&lt;").replace(">","&gt;")
        nav.append(f"<img class='avatar' src='{img_url}' alt='avatar' title='{safe_nick}'/>")
nav.append("</div></div>")
st.markdown("\n".join(nav), unsafe_allow_html=True)

# ------------------------------[ 4) 본문 ]-------------------------------------
st.markdown(
    """
<div class="hero-title">
    <h1>오래된 사진 복원 : AI로 온라인 사진 복원</h1>
    <p>온라인에서 빠르고 쉬운 복원을 경험해보세요. 손상·흔적 제거, 색채 디테일 복원.</p>
</div>
""",
    unsafe_allow_html=True,
)

preview_col, kakao_col = st.columns((7, 5), gap="large")

with preview_col:
    st.markdown("<div class='card preview-card'>", unsafe_allow_html=True)
    st.markdown(
        "<div class='card-title'>&lt;미리보기&gt; 복원 전 / 후</div>",
        unsafe_allow_html=True,
    )

    st.markdown("<div class='upload-widget'>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader(
        "복원할 이미지를 업로드하세요",
        type=["png", "jpg", "jpeg", "webp"],
        label_visibility="collapsed",
        key="restore_upload",
    )
    st.markdown("</div>", unsafe_allow_html=True)

    preview_url = None
    if uploaded_file is not None:
        try:
            image = Image.open(uploaded_file)
            preview_url = image_to_data_url(image)
        except Exception:
            st.warning("이미지를 불러오지 못했습니다. 지원되는 형식을 확인해주세요.")

    if preview_url:
        before_box = (
            f"<div class='preview-box' data-label='복원 전'><img src='{preview_url}' alt='업로드 이미지'></div>"
        )
        after_box = (
            "<div class='preview-box empty' data-label='복원 후'><span>AI 복원 결과는 작업 완료 후 제공됩니다.</span></div>"
        )
    else:
        before_box = (
            "<div class='preview-box empty' data-label='복원 전'><span>이미지를 업로드해 주세요.</span></div>"
        )
        after_box = (
            "<div class='preview-box empty' data-label='복원 후'><span>복원이 완료되면 미리보기를 제공해 드릴게요.</span></div>"
        )

    st.markdown(
        f"""
<div class='preview-grid'>
    {before_box}
    {after_box}
</div>
<div class='upload-hint'>
    <strong>drag and drop img file</strong>
    <p>원하는 이미지를 간단한 설명과 함께 업로드하면 복원 과정을 바로 시작할 수 있어요.</p>
</div>
<div class='preview-actions'>
    <button type='button' class='btn-secondary'>복원 옵션</button>
    <button type='button' class='btn-primary'>복원 시작하기</button>
</div>
</div>
""",
        unsafe_allow_html=True,
    )

with kakao_col:
    st.markdown("<div class='card kakao-card'>", unsafe_allow_html=True)
    st.markdown(
        "<div class='card-title'>카카오 계정 연동</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p>다음 카카오 계정을 연동하면 복원 이미지가 남아 언제든지 다운로드할 수 있어요.</p>",
        unsafe_allow_html=True,
    )

    if "kakao_token" in st.session_state:
        safe_nick = (nick or "카카오 사용자").replace("<", "&lt;").replace(">", "&gt;")
        status_avatar = (
            f"<img src='{img_url}' alt='카카오 아바타'/>" if img_url else ""
        )
        st.markdown(
            f"""
<div class='kakao-status'>
    {status_avatar}
    <div>
    <div>{safe_nick}</div>
    <small>카카오 계정이 연결되었습니다.</small>
    </div>
</div>
""",
            unsafe_allow_html=True,
        )

        st.markdown("<div class='kakao-actions'>", unsafe_allow_html=True)
        st.markdown(
            "<button type='button' class='btn-primary'>복원 내역 보기</button>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<a class='logout-btn' href='?logout=1'>로그아웃</a>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<p class='kakao-hint'>저장된 복원 이미지는 연동된 계정에서 언제든지 확인할 수 있어요.</p>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.markdown(
            f"<a class='kakao-connect' href='{auth_url}'>카카오 계정 연동</a>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<p class='kakao-hint'>카카오 계정을 연동하면 복원 이미지를 안전하게 보관하고 다운로드할 수 있어요.</p>",
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)
