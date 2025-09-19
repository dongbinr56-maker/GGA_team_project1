# ============================================================
# Streamlit App: Kakao OAuth + Hero Compare Slider + Photo Restoration Demo
# ------------------------------------------------------------
# - 팝업 로그인 → 부모창에 postMessage → 부모창만 새로고침 (팝업 자동 닫힘)
# - Hero 섹션은 components.html(iframe)로 렌더 → JS 정상 실행
# - 비교 슬라이더(세로, 분홍 포커스) 완전 동작
# - 이미지 표시 use_container_width 사용 (deprecated 경고 없음)
# - 코드 블록마다 주석 과잉 수준으로 설명
# ============================================================

import base64
import io
import os
import time
import hmac
import hashlib
import secrets
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import requests
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageFilter, ImageOps
import textwrap
import warnings

# (경고 숨김: Streamlit 내부 Deprecation 등 잡음 제거)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# ------------------------------[ 0) 페이지/레이아웃 ]---------------------------
st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

# 최소 UI 스타일 (네비/버튼 등). 히어로는 iframe 내부에서 자체 스타일 사용.
st.markdown(
    """
<style>
/* 사이드바/토글 숨김 */
[data-testid="stSidebar"]{ display:none !important; }
[data-testid="collapsedControl"]{ display:none !important; }

/* 상단 고정 네비 */
.navbar{
  position: fixed; top:0; left:0; right:0; height:60px;
  padding: 0 18px; background:#ffffff;
  display:flex; align-items:center; justify-content:flex-end;
  box-shadow:0 2px 6px rgba(0,0,0,.06); z-index:1000;
}
.block-container{ padding-top:78px; }

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
  display:inline-flex; align-items:center; padding:9px 12px; margin-right:8px;
  background:#fff; color:#222 !important; border:1px solid #E5E7EB; border-radius:10px;
  font-weight:600; text-decoration:none !important; cursor:pointer;
}
.logout-btn:hover{ background:#F9FAFB; }
.avatar{
  width:40px; height:40px; border-radius:50%; object-fit:cover;
  border:1px solid #E5E7EB; box-shadow:0 1px 2px rgba(0,0,0,0.05);
}
.nav-right{ display:flex; align-items:center; gap:10px; }

/* 본문 공통 */
.section-title{ font-size:1.85rem; font-weight:800; color:#111827; margin-bottom:10px; }
.section-lead{ font-size:1rem; color:#4b5563; margin-bottom:26px; }
.stButton button{
  border-radius:14px; padding:12px 18px; font-weight:700; border:none;
  background:linear-gradient(120deg, #ec4899, #f97316); color:#fff;
  box-shadow:0 15px 40px -24px rgba(236,72,153,0.9);
}
.stButton button:disabled{ background:#e5e7eb; color:#9ca3af; box-shadow:none; }
</style>
""",
    unsafe_allow_html=True,
)

# ------------------------------[ 1) 카카오 OAuth 설정 ]------------------------
# (환경변수 없을 때 기본값은 데모용. 실제 배포 시 꼭 환경변수로 교체)
REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "caf4fd09d45864146cb6e75f70c713a1")
REDIRECT_URI = os.getenv("KAKAO_REDIRECT_URI", "https://hackteam32.streamlit.app")
STATE_SECRET = os.getenv("KAKAO_STATE_SECRET", "UzdfMyaTkcNsJ2eVnRoKjUIOvWbeAy5E")

AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL     = "https://kauth.kakao.com/oauth/token"
USERME_URL    = "https://kapi.kakao.com/v2/user/me"

# CSRF 방지용 state(서버 세션 없이 HMAC으로 검증) – 만료 5분
STATE_TTL_SEC = 5 * 60

def _hmac_sha256(key: str, msg: str) -> str:
    """문자열 key/msg에 대해 sha256 HMAC(hex)를 생성"""
    return hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest()

def make_state() -> str:
    """시각+난수 기반 raw 에 HMAC서명 붙인 state 토큰 생성 (세션 불필요)"""
    ts = str(int(time.time()))
    nonce = secrets.token_urlsafe(8)
    raw = f"{ts}.{nonce}"
    sig = _hmac_sha256(STATE_SECRET, raw)
    return f"{raw}.{sig}"

def verify_state(state: str) -> bool:
    """state 서명/만료 검증"""
    if not state or state.count(".") != 2:  # ts.nonce.sig
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
    """카카오 인증 URL (팝업/새창에서 열 것)"""
    state = make_state()
    return (
        f"{AUTHORIZE_URL}"
        f"?client_id={REST_API_KEY}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&state={state}"
    )

def exchange_code_for_token(code: str) -> dict:
    """인가 코드 → 액세스 토큰 교환"""
    data = {
        "grant_type": "authorization_code",
        "client_id": REST_API_KEY,
        "redirect_uri": REDIRECT_URI,
        "code": code,
        "client_secret": STATE_SECRET,  # (선택) 보안 강화
    }
    response = requests.post(TOKEN_URL, data=data, timeout=10)
    response.raise_for_status()
    return response.json()

def get_user_profile(access_token: str) -> dict:
    """액세스 토큰으로 사용자 프로필 조회"""
    response = requests.get(
        USERME_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()

def extract_profile(user_me: dict):
    """카카오 응답에서 닉네임/이미지 안전하게 뽑기"""
    account = (user_me or {}).get("kakao_account", {}) or {}
    profile = account.get("profile", {}) or {}
    nickname = profile.get("nickname") or None
    img = profile.get("profile_image_url") or profile.get("thumbnail_image_url") or None
    if not nickname or not img:
        props = (user_me or {}).get("properties", {}) or {}
        nickname = nickname or props.get("nickname")
        img = img or props.get("profile_image") or props.get("thumbnail_image")
    return nickname, img

# ------------------------------[ 2) 콜백/로그아웃/토큰 파라미터 처리 ]---------
# Streamlit 1.31+ : st.query_params 권장, 이전버전 호환용 fallback
_query_params = st.query_params if hasattr(st, "query_params") else st.experimental_get_query_params()

def _first_param(name: str):
    value = _query_params.get(name)
    return value[0] if isinstance(value, list) and value else value

# 로그아웃 요청
if _first_param("logout") == "1":
    st.session_state.pop("kakao_token", None)
    st.session_state.pop("kakao_profile", None)
    if hasattr(st, "query_params"):
        st.query_params.clear()
    else:
        st.experimental_set_query_params()
    st.rerun()

# 팝업이 부모창으로 보낸 access_token 처리(부모창에서만 사용)
token_param = _first_param("token")
if token_param and "kakao_token" not in st.session_state:
    st.session_state.kakao_token = {"access_token": token_param}
    try:
        st.session_state.kakao_profile = get_user_profile(token_param)
    except Exception:
        pass  # 토큰 만료 등은 조용히 무시
    # 파라미터 정리하고 새로고침
    if hasattr(st, "query_params"):
        st.query_params.clear()
    else:
        st.experimental_set_query_params()
    st.rerun()

# 카카오 에러/코드 처리(팝업 창에서 실행되는 분기)
error = _first_param("error")
error_description = _first_param("error_description")
code = _first_param("code")
state = _first_param("state")

if error:
    st.error(f"카카오 인증 에러: {error}\n{error_description or ''}")
elif code:
    # 팝업/동일창 모두 커버. 팝업인 경우 JS로 부모창에게 토큰 넘기고 닫기.
    if not verify_state(state):
        st.error("state 검증 실패(CSRF/만료). 다시 시도해주세요.")
    else:
        try:
            token_json = exchange_code_for_token(code)
            st.session_state.kakao_token = token_json
            st.session_state.kakao_profile = get_user_profile(token_json["access_token"])
            # 팝업이면 부모창으로 토큰 전달 → 팝업 닫기
            st.markdown(
                f"""
<script>
if (window.opener) {{
  window.opener.postMessage({{"kakao_token":"{token_json['access_token']}" }}, "*");
  window.close();
}} else {{
  // 동일창 플로우일 때는 루트로 이동
  window.location.href = "/";
}}
</script>
""",
                unsafe_allow_html=True,
            )
            # ⚠️ 여기서 st.rerun() 호출하면 팝업이 리프레시되며 JS 미실행 → 닫힘 실패
        except requests.HTTPError as exc:
            st.exception(exc)

# ------------------------------[ 3) 우상단 네비바 ]-----------------------------
auth_url = build_auth_url()
nickname, img_url = None, None
if "kakao_profile" in st.session_state:
    nickname, img_url = extract_profile(st.session_state["kakao_profile"])

nav_bits = ["<div class='navbar'><div class='nav-right'>"]
if "kakao_token" not in st.session_state:
    # 팝업으로 로그인: target="_blank"
    nav_bits.append(f"<a class='kakao-btn' href='{auth_url}' target='_blank'>카카오 로그인</a>")
else:
    nav_bits.append("<a class='logout-btn' href='?logout=1'>로그아웃</a>")
    if img_url:
        safe_nick = (nickname or "").replace("<", "&lt;").replace(">", "&gt;")
        nav_bits.append(f"<img class='avatar' src='{img_url}' alt='avatar' title='{safe_nick}'/>")
nav_bits.append("</div></div>")
st.markdown("".join(nav_bits), unsafe_allow_html=True)

# 부모창이 팝업에서 보낸 토큰을 수신하는 리스너(부모창에서만 동작)
components.html(
    """
<script>
window.addEventListener("message", function (event) {
  if (event && event.data && event.data.kakao_token) {
    // 토큰을 쿼리파라미터로 붙여 새로고침 → 서버 세션에 저장
    window.location.href = "/?token=" + encodeURIComponent(event.data.kakao_token);
  }
}, false);
</script>
""",
    height=0,
)

# ------------------------------[ 3-1) 히어로 섹션 ]----------------------------
@st.cache_data(show_spinner=False)
def load_demo_compare_images() -> Dict[str, Optional[str]]:
    """
    Hero 비교 미리보기에 사용할 before/after 샘플 이미지를 base64로 읽어온다.
    - 앱 파일과 같은 폴더의 before.png / after.png 를 사용 (없으면 None)
    - 반환 딕셔너리 키: 'before', 'after'
    """
    base_dir = Path(__file__).resolve().parent

    def _read(path: Path) -> Optional[str]:
        if not path.exists():
            return None
        return base64.b64encode(path.read_bytes()).decode("utf-8")

    before_path = base_dir / "before.png"
    after_path  = base_dir / "after.png"

    return {"before": _read(before_path), "after": _read(after_path)}

def render_hero_section(auth_url: str, is_logged_in: bool) -> None:
    """
    Hero 영역을 components.html(iframe)로 렌더.
    - iframe 내부에 CSS/JS를 포함하므로 Streamlit의 스크립트 제한 영향 없음
    - 비교 슬라이더: input[type=range] 값 → after 이미지 clip-path 갱신
    """
    images = load_demo_compare_images()
    before_b64 = images.get("before")
    after_b64  = images.get("after")

    primary_label = "복원 작업 시작하기" if is_logged_in else "카카오 계정으로 계속"
    primary_href  = "#restore-app" if is_logged_in else auth_url
    caption = ("로그인 상태입니다. 바로 복원을 시작해보세요."
               if is_logged_in else "카카오 로그인 시 복원 기록이 세션에 보존됩니다.")

    # ⚠️ f-string 안에서 JS/CSS의 중괄호는 전부 {{ }} 로 이스케이프해야 함
    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  body {{ margin:0; font-family: ui-sans-serif,system-ui,-apple-system; }}
  .hero-wrap {{
    padding:32px 36px;
    background:linear-gradient(135deg, rgba(255,240,247,0.9), rgba(236,233,255,0.85));
    border-radius:28px; border:1px solid rgba(255,255,255,0.6);
    box-shadow:0 24px 60px -34px rgba(15,23,42,0.4);
  }}
  .grid {{ display:grid; grid-template-columns:minmax(0,1.1fr) minmax(0,0.9fr); gap:48px; align-items:center; }}
  .hero-badge{{ display:inline-flex; gap:6px; padding:6px 14px; border-radius:999px; background:#fff; color:#ec4899; font-weight:700; margin-bottom:14px; }}
  .hero-title{{ font-size:2.8rem; font-weight:800; line-height:1.2; color:#111827; margin:0 0 14px; }}
  .hero-title span{{ color:#ec4899; }}
  .hero-subtext{{ color:#4b5563; line-height:1.7; margin:0 0 22px; max-width:520px; }}
  .hero-buttons{{ display:flex; gap:12px; align-items:center; margin-bottom:8px; }}
  .cta{{ display:inline-flex; align-items:center; justify-content:center; padding:12px 20px; border-radius:999px; font-weight:800; text-decoration:none }}
  .cta.primary{{ background:linear-gradient(120deg,#ec4899,#fb7185); color:#fff; }}
  .cta.secondary{{ background:rgba(255,255,255,0.9); color:#ec4899; border:1px solid rgba(236,72,153,0.3); }}
  .caption{{ color:#6b7280; font-size:.9rem; }}

  /* 비교 뷰 */
  .hero-compare{{ position:relative; width:100%; height:520px; border-radius:26px; overflow:hidden; background:#111827;
                  box-shadow:0 34px 60px -30px rgba(15,23,42,0.55); }}
  .hero-compare img{{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover; z-index:1; pointer-events:none; }}
  .hero-compare img.after{{ clip-path:inset(0 0 0 52%); }}
  .hero-divider{{ position:absolute; top:0; bottom:0; left:52%; width:3px; background:rgba(255,255,255,0.92);
                  box-shadow:0 0 0 1px rgba(15,23,42,0.1); pointer-events:none; z-index:4; }}
  .hero-label{{ position:absolute; top:14px; padding:7px 14px; border-radius:999px; font-size:.78rem; font-weight:700; letter-spacing:.05em; z-index:5; pointer-events:none; }}
  .hero-label.before{{ left:14px; background:rgba(15,23,42,0.75); color:#f9fafb; }}
  .hero-label.after{{ right:14px; background:rgba(236,72,153,0.85); color:#fff; }}

  /* 슬라이더를 최상단으로 올려 드래그 먹게 */
  .compare-slider{{ position:absolute; inset:0; width:100%; height:100%; opacity:0; z-index:10; cursor:ew-resize;
                    -webkit-appearance:none; appearance:none; background:transparent; outline:none; }}

  @media (max-width:1100px) {{
    .grid{{ grid-template-columns:1fr; }}
    .hero-compare{{ height:420px; }}
  }}
</style>
</head>
<body>
  <section class="hero-wrap">
    <div class="grid">
      <div>
        <div class="hero-badge">AI Photo Revival</div>
        <h1 class="hero-title">오래된 사진 복원 : <span>AI로 온라인 사진 복원</span></h1>
        <p class="hero-subtext">흑백의 시간을 되살리고, 선명한 디테일까지 복원하는 프리미엄 AI 파이프라인. 업로드만 하면 자동 색보정, 노이즈 제거, 해상도 업스케일까지 한 번에 경험할 수 있습니다.</p>
        <div class="hero-buttons">
          <a class="cta primary" href="{primary_href}">{primary_label}</a>
          <a class="cta secondary" href="#restore-app">게스트 모드로 먼저 체험하기</a>
        </div>
        <div class="caption">{caption}</div>
      </div>

      <div>
        {"" if not (before_b64 and after_b64) else f"""
        <div class='hero-compare compare-ready' data-start='48'>
          <img src='data:image/png;base64,{before_b64}' alt='복원 전' class='hero-img before'/>
          <img src='data:image/png;base64,{after_b64}' alt='복원 후' class='hero-img after'/>
          <div class='hero-divider'></div>
          <span class='hero-label before'>BEFORE</span>
          <span class='hero-label after'>AFTER</span>
          <input type='range' min='0' max='100' value='48' class='compare-slider' aria-label='Before After slider'/>
        </div>
        """}
      </div>
    </div>
  </section>

  <script>
  (function(){{
    function apply(container){{
      if(!container || container.dataset.bound==='1') return;
      container.dataset.bound='1';
      var slider  = container.querySelector('.compare-slider');
      var afterImg= container.querySelector('.hero-img.after');
      var divider = container.querySelector('.hero-divider');
      if(!slider || !afterImg) return;

      function setValue(v){{
        var pct   = Math.min(100, Math.max(0, Number(v)));
        var inset = 'inset(0 0 0 ' + (100 - pct) + '%)';
        afterImg.style.clipPath       = inset;   // 표준
        afterImg.style.webkitClipPath = inset;   // 웹킷 대응
        if(divider) divider.style.left = pct + '%';
      }}
      var start = container.dataset.start || slider.value || 50;
      slider.value = start; setValue(start);
      var handler = function(e){{ setValue(e.target.value); }};
      slider.addEventListener('input', handler);
      slider.addEventListener('change', handler);
    }}

    function init(){{ document.querySelectorAll('.hero-compare.compare-ready').forEach(apply); }}
    if (document.readyState==='loading') document.addEventListener('DOMContentLoaded', init); else init();

    // 동적 리렌더(스트림릿 rerun 등)에도 안전하게 다시 바인딩
    new MutationObserver(init).observe(document.body, {{ childList:true, subtree:true }});
  }})();
  </script>
</body>
</html>
    """

    # iframe 렌더 (스크립트 실행 허용)
    components.html(html, height=620, scrolling=False)

# 히어로 렌더 + 아래로 간격 스페이서
render_hero_section(auth_url, "kakao_token" in st.session_state)
st.markdown("<div style='height: 48px'></div>", unsafe_allow_html=True)

# ------------------------------[ 4) 복원 유틸 함수 ]---------------------------
def ensure_restoration_state() -> Dict:
    """세션에 복원 상태 컨테이너 초기화/획득"""
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

def image_from_bytes(data: bytes) -> Image.Image:
    """bytes → PIL.Image (EXIF 회전 보정 + RGB 변환)"""
    image = Image.open(io.BytesIO(data))
    image = ImageOps.exif_transpose(image)
    return image.convert("RGB")

def image_to_bytes(image: Image.Image) -> bytes:
    """PIL.Image → PNG bytes"""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()

def colorize_image(image: Image.Image) -> Image.Image:
    """샘플 컬러라이즈(데모)"""
    gray = image.convert("L")
    colorized = ImageOps.colorize(gray, black="#1e1e1e", white="#f8efe3", mid="#88a6c6")
    return colorized.convert("RGB")

def upscale_image(image: Image.Image) -> Image.Image:
    """샘플 업스케일(2x)"""
    width, height = image.size
    return image.resize((width * 2, height * 2), Image.LANCZOS)

def denoise_image(image: Image.Image) -> Image.Image:
    """샘플 디노이즈"""
    smoothed = image.filter(ImageFilter.MedianFilter(size=3))
    return smoothed.filter(ImageFilter.SMOOTH_MORE)

def format_status(counts: Dict[str, int]) -> str:
    """상태 캡션 텍스트"""
    return (
        f"[컬러화 {'✔' if counts['color'] else '✖'} / "
        f"해상도 {counts['upscale']}회 / 노이즈 {counts['denoise']}회]"
    )

def add_history_entry(label: str, image_bytes: bytes, note: Optional[str] = None):
    """히스토리에 단계 저장"""
    restoration = ensure_restoration_state()
    entry = {
        "label": label,
        "bytes": image_bytes,
        "status": dict(restoration["counts"]),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "note": note,
    }
    restoration["history"].append(entry)
    restoration["current_bytes"] = image_bytes

def reset_restoration(upload_digest: str, original_bytes: bytes, photo_type: str, description: str):
    """새 업로드 시 세션 상태 초기화"""
    restoration = ensure_restoration_state()
    restoration.update(
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

def build_story(description: str, counts: Dict[str, int], photo_type: str) -> str:
    """스토리 텍스트 생성(샘플)"""
    base = description.strip() or "이 사진"
    story_lines = []
    story_lines.append(f"{base}은(는) 조심스럽게 복원 과정을 거치고 있습니다.")
    if photo_type == "흑백":
        if counts["color"]:
            story_lines.append("흑백으로 남아 있던 순간에 색을 덧입히자 잊혔던 온기와 공기가 되살아났습니다.")
        else:
            story_lines.append("아직 색을 입히지 못한 채 시간 속에서 기다리고 있습니다.")
    if counts["upscale"]:
        story_lines.append(f"세부 묘사를 살리기 위해 해상도 보정을 {counts['upscale']}회 반복하며 흐릿했던 윤곽을 또렷하게 다듬었습니다.")
    if counts["denoise"]:
        story_lines.append(f"잡음을 정리하는 과정도 {counts['denoise']}회 진행되어 사진 속 인물의 표정과 배경이 한층 차분해졌습니다.")
    if not counts["upscale"] and not counts["denoise"] and counts["color"]:
        story_lines.append("색만 더했을 뿐인데도 장면의 감정이 살아 움직이는 듯합니다.")
    story_lines.append("복원된 이미지를 바라보는 지금, 사진 속 이야기가 현재의 우리에게 말을 건네는 듯합니다.")
    story_lines.append("이 장면이 전하고 싶은 메시지가 있다면, 그것은 기억을 계속 이어가자는 마음일지도 모릅니다.")
    wrapped = [textwrap.fill(line, width=46) for line in story_lines]
    return "\n\n".join(wrapped)

def handle_auto_colorization(photo_type: str):
    """흑백 선택 시 1회 자동 컬러화(데모)"""
    restoration = ensure_restoration_state()
    if photo_type != "흑백" or restoration["counts"]["color"]:
        return
    original = image_from_bytes(restoration["current_bytes"])
    colorized = colorize_image(original)
    restoration["counts"]["color"] += 1
    bytes_data = image_to_bytes(colorized)
    restoration["story"] = None
    add_history_entry("컬러 복원 (자동)", bytes_data, note="흑백 이미지를 기본 팔레트로 색보정했습니다.")

def can_run_operation(operation: str, allow_repeat: bool) -> bool:
    """버튼 활성화 규칙(반복 허용 시 최대 3회)"""
    restoration = ensure_restoration_state()
    count = restoration["counts"].get(operation, 0)
    return (count < 3) if allow_repeat else (count == 0)

def run_upscale():
    restoration = ensure_restoration_state()
    image = image_from_bytes(restoration["current_bytes"])
    upscaled = upscale_image(image)
    restoration["counts"]["upscale"] += 1
    bytes_data = image_to_bytes(upscaled)
    restoration["story"] = None
    add_history_entry("해상도 업", bytes_data, note="ESRGAN 대체 알고리즘(샘플)으로 2배 업스케일했습니다.")

def run_denoise():
    restoration = ensure_restoration_state()
    image = image_from_bytes(restoration["current_bytes"])
    denoised = denoise_image(image)
    restoration["counts"]["denoise"] += 1
    bytes_data = image_to_bytes(denoised)
    restoration["story"] = None
    add_history_entry("노이즈 제거", bytes_data, note="NAFNet 대체 필터(샘플)로 노이즈를 완화했습니다.")

def run_story_generation():
    restoration = ensure_restoration_state()
    text = build_story(restoration["description"], restoration["counts"], restoration["photo_type"])
    restoration["counts"]["story"] += 1
    restoration["story"] = {
        "text": text,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": dict(restoration["counts"]),
    }

# ------------------------------[ 5) 본문 UI ]----------------------------------
st.title("📌 사진 복원 + 스토리 생성")
st.markdown("<div id='restore-app'></div>", unsafe_allow_html=True)
st.markdown("<h2 class='section-title'>AI 복원 워크플로우</h2>", unsafe_allow_html=True)
st.markdown("<p class='section-lead'>업로드 → 복원 옵션 실행 → 스토리 생성까지 한눈에 진행할 수 있는 단계별 워크플로우입니다.</p>", unsafe_allow_html=True)

if "kakao_token" in st.session_state:
    st.success(f"로그인됨: {(nickname or '카카오 사용자')}")
    st.success(f"{(nickname or '카카오 사용자')}님, 로그인 상태입니다. 복원 작업이 히스토리에 저장됩니다.")
else:
    st.info("카카오 로그인을 진행하면 복원 내역이 세션에 보존됩니다.")
    st.info("카카오 로그인 시 복원 내역이 세션에 보존되며, 게스트 모드에서도 체험해볼 수 있습니다.")

restoration_state = ensure_restoration_state()

with st.container():
    st.subheader("1. 사진 업로드")
    photo_type = st.radio("사진 유형", ["흑백", "컬러"], horizontal=True, key="photo_type_selector")
    description = st.text_input("사진에 대한 간단한 설명", key="photo_description", placeholder="예: 1970년대 외할아버지의 결혼식")
    uploaded_file = st.file_uploader("사진 파일 업로드", type=["png", "jpg", "jpeg", "bmp", "tiff"], key="photo_uploader")

    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        digest = hashlib.sha1(file_bytes).hexdigest()
        if restoration_state["upload_digest"] != digest:
            reset_restoration(digest, file_bytes, photo_type, description)
            handle_auto_colorization(photo_type)
        else:
            restoration_state["description"] = description
            restoration_state["photo_type"] = photo_type

allow_repeat = st.checkbox("고급 옵션(실험적) - 동일 작업 반복 허용 (최대 3회)")
if allow_repeat:
    st.warning("⚠ 동일 작업 반복은 처리 시간이 길어지거나 이미지 손상을 유발할 수 있습니다.")

if restoration_state["original_bytes"] is None:
    st.info("사진을 업로드하면 복원 옵션이 활성화됩니다.")
else:
    st.subheader("2. 복원 옵션")
    cols = st.columns(3)
    with cols[0]:
        can_upscale = can_run_operation("upscale", allow_repeat)
        if st.button("해상도 업", use_container_width=True, disabled=not can_upscale):
            run_upscale()
    with cols[1]:
        can_denoise = can_run_operation("denoise", allow_repeat)
        if st.button("노이즈 제거", use_container_width=True, disabled=not can_denoise):
            run_denoise()
    with cols[2]:
        can_story = can_run_operation("story", allow_repeat)
        if st.button("스토리 생성", use_container_width=True, disabled=not can_story):
            run_story_generation()

    st.divider()
    col_original, col_result = st.columns(2)

    with col_original:
        st.subheader("원본 이미지")
        st.image(restoration_state["original_bytes"], use_container_width=True)
        st.caption(format_status({"color": 0, "upscale": 0, "denoise": 0}))

    with col_result:
        st.subheader("복원 결과")
        if restoration_state["history"]:
            latest = restoration_state["history"][-1]
            st.image(latest["bytes"], use_container_width=True, caption=latest["label"])
            st.caption(format_status(latest["status"]))
            if latest.get("note"):
                st.markdown(f"*{latest['note']}*")
        else:
            st.info("아직 수행된 복원 작업이 없습니다.")

    if len(restoration_state["history"]) > 1:
        with st.expander("전체 작업 히스토리"):
            for idx, entry in enumerate(restoration_state["history"], 1):
                st.markdown(f"**{idx}. {entry['label']}** ({entry['timestamp']})")
                st.image(entry["bytes"], use_container_width=True)
                st.caption(format_status(entry["status"]))
                if entry.get("note"):
                    st.write(entry["note"])
                st.markdown("---")

    if restoration_state.get("story"):
        st.subheader("스토리")
        story_info = restoration_state["story"]
        st.markdown(story_info["text"])
        st.caption(f"생성 시각: {story_info['timestamp']} / {format_status(story_info['status'])}")

st.markdown("---")
st.caption("*DeOldify, ESRGAN, NAFNet 등의 실제 모델 연동을 위한 자리 표시자로, 현재는 샘플 필터를 사용합니다.*")
