# app.py
# ============================================================
# Kakao OAuth for Streamlit (No-session CSRF using HMAC state)
# - 우상단 고정 네비바(화이트, 라운드, 그림자)
# - 사이드바 숨김
# - 로그인 전: "카카오 로그인" 노란 버튼
# - 로그인 후: "로그아웃" + 원형 프로필 아바타
# - CSRF state: 세션에 안 저장. HMAC 서명 토큰으로 검증 → 세션 갈려도 OK.
# ============================================================

import os, time, hmac, hashlib, requests, secrets
import streamlit as st

# ------------------------------[ 0) 페이지/레이아웃 ]---------------------------
st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
  /* 사이드바/토글 제거 */
  [data-testid="stSidebar"]{ display:none !important; }
  [data-testid="collapsedControl"]{ display:none !important; }

  /* 우상단 네비게이션 바 */
  .navbar {
    position: fixed;
    top: 100; left: 0; right: 0;
    height: 60px;
    padding: 0 18px;
    background: #ffffff;
    display: flex; align-items: center; justify-content: flex-end;
    box-shadow: 0 2px 6px rgba(0,0,0,0.06);
    z-index: 1000;
  }
  /* 본문 상단 패딩(네비바 높이만큼) */
  .block-container { padding-top: 78px; }

  /* 버튼/아바타 */
  .kakao-btn{
    display:inline-flex; align-items:center; gap:8px;
    padding:10px 14px; background:#FEE500; color:#000 !important;
    border:1px solid rgba(0,0,0,.08); border-radius:10px;
    font-weight:700; text-decoration:none !important;
    box-shadow:0 1px 2px rgba(0,0,0,.08); cursor:pointer;
  }
  .kakao-btn:hover{ filter:brightness(0.96); }

  .logout-btn{
    display:inline-flex; align-items:center;
    padding:9px 12px; margin-right:8px;
    background:#fff; color:#222 !important;
    border:1px solid #E5E7EB; border-radius:10px;
    font-weight:600; text-decoration:none !important; cursor:pointer;
  }
  .logout-btn:hover{ background:#F9FAFB; }

  .avatar{
    width:40px; height:40px; border-radius:50%; object-fit:cover;
    border:1px solid #E5E7EB; box-shadow:0 1px 2px rgba(0,0,0,0.05);
  }

  .nav-right{ display:flex; align-items:center; gap:10px; }
</style>
""", unsafe_allow_html=True)

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
    ts    = str(int(time.time()))
    nonce = secrets.token_urlsafe(8)  # 가변성 확보
    raw   = f"{ts}.{nonce}"
    sig   = _hmac_sha256(STATE_SECRET, raw)
    return f"{raw}.{sig}"

def verify_state(state: str) -> bool:
    """
    되돌아온 state 검증:
    - 구조: ts.nonce.sig
    - sig == HMAC(ts.nonce)
    - ts가 TTL 이내
    """
    if not state or state.count(".") != 2:
        return False
    ts, nonce, sig = state.split(".")
    # 1) 시그니처 검증
    expected = _hmac_sha256(STATE_SECRET, f"{ts}.{nonce}")
    if not hmac.compare_digest(sig, expected):
        return False
    # 2) 만료 검증
    try:
        ts_i = int(ts)
    except ValueError:
        return False
    if time.time() - ts_i > STATE_TTL_SEC:
        return False
    return True

def build_auth_url() -> str:
    """카카오 인가 페이지 URL 구성 (state = HMAC 서명 토큰)"""
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
        # "client_secret": os.getenv("KAKAO_CLIENT_SECRET")  # 사용 중이면 주석 해제
    }
    r = requests.post(TOKEN_URL, data=data, timeout=10)
    r.raise_for_status()
    return r.json()

def get_user_profile(access_token: str) -> dict:
    r = requests.get(USERME_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
    r.raise_for_status()
    return r.json()

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
    # ✅ 세션 기반 비교 X → HMAC 서명 토큰 검증
    if not verify_state(state):
        st.error("state 검증 실패(CSRF/만료). 다시 시도해주세요.")
    else:
        try:
            token_json = exchange_code_for_token(code)
            st.session_state.kakao_token   = token_json
            st.session_state.kakao_profile = get_user_profile(token_json["access_token"])
            # URL 정리 후 재렌더링
            if hasattr(st, "query_params"): st.query_params.clear()
            else: st.experimental_set_query_params()
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
st.write("")  # 네비바 여백
if "kakao_token" in st.session_state:
    st.success(f"로그인됨: {(nick or '카카오 사용자')}")
else:
    st.info("로그인이 필요합니다.")

st.write("여기에 본문 UI 넣기.")
