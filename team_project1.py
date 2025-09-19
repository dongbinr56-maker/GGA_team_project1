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
from PIL import Image, ImageFilter, ImageOps
import textwrap
# ============================================================
# Kakao OAuth for Streamlit (No-session CSRF using HMAC state)
# - 우상단 고정 네비바(화이트, 라운드, 그림자)
# - 사이드바 숨김
# - 로그인 전: "카카오 로그인" 노란 버튼
# - 로그인 후: "로그아웃" + 원형 프로필 아바타
# - CSRF state: 세션에 안 저장. HMAC 서명 토큰으로 검증 → 세션 갈려도 OK.
# ============================================================
# ------------------------------[ 0) 페이지/레이아웃 ]---------------------------
st.set_page_config(layout="wide", initial_sidebar_state="collapsed")
st.markdown(
    """
<style>
 [data-testid="stSidebar"]{ display:none !important; }
    [data-testid="collapsedControl"]{ display:none !important; }
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
    .block-container { padding-top: 78px; }
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

    body{ background:#f8fafc; }

    .hero-section{
    margin-top:32px;
    padding:32px 36px;
    border-radius:28px;
    background:linear-gradient(135deg, rgba(255,240,247,0.9), rgba(236,233,255,0.85));
    border:1px solid rgba(255,255,255,0.6);
    box-shadow:0 24px 60px -34px rgba(15,23,42,0.4);
    display:grid;
    grid-template-columns:minmax(0,1.1fr) minmax(0,0.9fr);
    gap:48px;
    align-items:center;
    position:relative;
    overflow:hidden;
    }

    .hero-section::after{
    content:"";
    position:absolute;
    inset:0;
    background:radial-gradient(circle at 20% -10%, rgba(244,114,182,0.35), transparent 55%),
              radial-gradient(circle at 80% 120%, rgba(129,140,248,0.35), transparent 60%);
    z-index:0;
    }

    .hero-text, .hero-visual{ position:relative; z-index:1; }

    .hero-badge{
    display:inline-flex;
    align-items:center;
    gap:6px;
    padding:6px 14px;
    border-radius:999px;
    background:rgba(255,255,255,0.85);
    color:#ec4899;
    font-size:0.82rem;
    font-weight:600;
    letter-spacing:0.04em;
    text-transform:uppercase;
    box-shadow:0 8px 20px -12px rgba(236,72,153,0.8);
    margin-bottom:18px;
    }

    .hero-title{
    font-size:2.8rem;
    font-weight:800;
    line-height:1.2;
    color:#111827;
    margin-bottom:18px;
    }

    .hero-title span{ color:#ec4899; }

    .hero-subtext{
    font-size:1.05rem;
    color:#4b5563;
    line-height:1.7;
    margin-bottom:28px;
    max-width:520px;
    }

    .hero-buttons{ display:flex; flex-wrap:wrap; gap:14px; align-items:center; }

    .hero-buttons a{
    display:inline-flex;
    align-items:center;
    justify-content:center;
    gap:8px;
    padding:14px 22px;
    border-radius:999px;
    font-weight:700;
    text-decoration:none !important;
    transition:transform 0.25s ease, box-shadow 0.25s ease;
    box-shadow:0 10px 30px -15px rgba(236,72,153,0.75);
    }

    .cta-primary{
    background:linear-gradient(120deg, #ec4899, #fb7185);
    color:#fff !important;
    }

    .cta-primary:hover{ transform:translateY(-2px); box-shadow:0 20px 35px -20px rgba(236,72,153,0.9); }

    .cta-secondary{
    background:rgba(255,255,255,0.9);
    color:#ec4899 !important;
    border:1px solid rgba(236,72,153,0.3);
    box-shadow:0 12px 24px -18px rgba(236,72,153,0.5);
    }

    .cta-secondary:hover{ transform:translateY(-2px); }

    .cta-caption{
    display:block;
    margin-top:10px;
    color:#6b7280;
    font-size:0.9rem;
    }

    .hero-compare{
    position:relative;
    width:100%;
    aspect-ratio:4/3;
    border-radius:26px;
    overflow:hidden;
    background:#111827;
    box-shadow:0 34px 60px -30px rgba(15,23,42,0.55);
    }

    .hero-compare img{
    position:absolute;
    inset:0;
    width:100%;
    height:100%;
    object-fit:cover;
    }

    .hero-compare img.after{ clip-path:inset(0 0 0 52%); }

    .hero-compare::after{
    content:"";
    position:absolute;
    top:0; bottom:0; left:52%;
    width:3px;
    background:rgba(255,255,255,0.92);
    box-shadow:0 0 0 1px rgba(15,23,42,0.1);
    }

    .hero-label{
    position:absolute;
    top:18px;
    padding:7px 14px;
    border-radius:999px;
    font-size:0.78rem;
    font-weight:600;
    letter-spacing:0.05em;
    text-transform:uppercase;
    }

    .hero-label.before{ left:18px; background:rgba(15,23,42,0.75); color:#f9fafb; }
    .hero-label.after{ right:18px; background:rgba(236,72,153,0.85); color:#fff; }

    .section-title{
    font-size:1.85rem;
    font-weight:800;
    color:#111827;
    margin-bottom:10px;
    }

    .section-lead{
    font-size:1rem;
    color:#4b5563;
    margin-bottom:26px;
    }

    .stButton button{
    border-radius:14px;
    padding:12px 18px;
    font-weight:700;
    border:none;
    background:linear-gradient(120deg, #ec4899, #f97316);
    color:#fff;
    box-shadow:0 15px 40px -24px rgba(236,72,153,0.9);
    }

    .stButton button:hover{
    filter:brightness(0.98);
    }

    .stButton button:disabled{
    background:#e5e7eb;
    color:#9ca3af;
    box-shadow:none;
    }

    .stRadio > div{ display:flex; gap:16px; }
    .stRadio label{ font-weight:600; color:#374151; }

    @media (max-width: 1100px){
    .hero-section{ grid-template-columns:1fr; padding:26px 24px; }
    .hero-title{ font-size:2.3rem; }
    .hero-subtext{ max-width:none; }
    }

    @media (max-width: 640px){
    .hero-buttons{ flex-direction:column; align-items:flex-start; }
    .hero-compare{ aspect-ratio:3/4; }
    }
</style>
""",
    unsafe_allow_html=True,
)
# ------------------------------[ 1) 카카오 OAuth 설정 ]------------------------
REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "caf4fd09d45864146cb6e75f70c713a1")
REDIRECT_URI = os.getenv("KAKAO_REDIRECT_URI", "https://hackteam32.streamlit.app")
STATE_SECRET = os.getenv("KAKAO_STATE_SECRET", "UzdfMyaTkcNsJ2eVnRoKjUIOvWbeAy5E")
    #or os.getenv("OAUTH_STATE_SECRET")
    #or (REST_API_KEY or "dev-secret")

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
        "client_secret":STATE_SECRET
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
            if hasattr(st, "query_params"):
                st.query_params.clear()
            else:
                st.experimental_set_query_params()
            st.rerun()
        except requests.HTTPError as exc:
            st.exception(exc)
# ------------------------------[ 3) 우상단 네비바 ]-----------------------------
auth_url = build_auth_url()
nickname, img_url = None, None
if "kakao_profile" in st.session_state:
    nickname, img_url = extract_profile(st.session_state["kakao_profile"])
nav_parts = ["<div class='navbar'><div class='nav-right'>"]
if "kakao_token" not in st.session_state:
    nav_parts.append(f"<a class='kakao-btn' href='{auth_url}'>카카오 로그인</a>")
else:
    nav_parts.append("<a class='logout-btn' href='?logout=1'>로그아웃</a>")
    if img_url:
        safe_nick = (nickname or "").replace("<", "&lt;").replace(">", "&gt;")
        nav_parts.append(
            f"<img class='avatar' src='{img_url}' alt='avatar' title='{safe_nick}'/>"
        )
nav_parts.append("</div></div>")
st.markdown("\n".join(nav_parts), unsafe_allow_html=True)

# ------------------------------[ 3-1) 히어로 섹션 ]----------------------------
@st.cache_data(show_spinner=False)
def load_demo_compare_images() -> Dict[str, Optional[str]]:
    """Load demo before/after images as base64 strings for the hero preview."""

    base_dir = Path(__file__).resolve().parent

    def _read(path: Path) -> Optional[str]:
        if not path.exists():
            return None
        return base64.b64encode(path.read_bytes()).decode("utf-8")

    before_path = base_dir / "before.png"
    after_path = base_dir / "after.png"

    before_encoded = _read(before_path)
    after_encoded = _read(after_path)

    return {
        "before": before_encoded,
        "after": after_encoded,
        str(before_path): before_encoded,
        str(after_path): after_encoded,
    }


def render_hero_section(auth_url: str, is_logged_in: bool) -> None:
    images = load_demo_compare_images()

    base_dir = Path(__file__).resolve().parent

    before_b64 = (
        images.get("before")
        or images.get("before.png")
        or images.get(str(base_dir / "before.png"))
    )
    after_b64 = (
        images.get("after")
        or images.get("after.png")
        or images.get(str(base_dir / "after.png"))
    )

    compare_script = """
    <script>
    (function(){
        var guardKey = 'heroCompareInit';
        if (window[guardKey]) {
            return;}
        window[guardKey] = true;
        function applyCompare(container){
            if (!container || container.dataset.bound === '1') {
                return;
            }
            container.dataset.bound = '1';

            var slider = container.querySelector('.compare-slider');
            var afterImg = container.querySelector('.hero-img.after');
            var divider = container.querySelector('.hero-divider');
            if (!slider || !afterImg) {
                return;
            }

            function setValue(value){
                var numeric = Math.min(100, Math.max(0, Number(value)));
                afterImg.style.clipPath = 'inset(0 0 0 ' + (100 - numeric) + '%)';
                if (divider) {
                    divider.style.left = numeric + '%';
                }
            }

            var start = container.dataset.start || slider.value || 50;
            slider.value = start;
            setValue(start);

            slider.addEventListener('input', function(evt){
                setValue(evt.target.value);
            });
        }

        function init(){
            document.querySelectorAll('.hero-compare.compare-ready').forEach(applyCompare);
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', init);
        } else {
            init();
        }

        var observer = new MutationObserver(function(){ init(); });
        observer.observe(document.body, { childList: true, subtree: true });
    })();
    </script>
    """

    if before_b64 and after_b64:
        compare_html = f"""
        <div class='hero-compare compare-ready' data-start='48'>
            <img src='data:image/png;base64,{before_b64}' alt='복원 전' class='hero-img before'/>
            <img src='data:image/png;base64,{after_b64}' alt='복원 후' class='hero-img after'/>
            <div class='hero-divider'></div>
            <span class='hero-label before'>Before</span>
            <span class='hero-label after'>After</span>
            <input type='range' min='0' max='100' value='48' class='compare-slider' aria-label='Before After slider'/>
        </div>
        {compare_script}
        """
    else:
        compare_html = """
        <div class='hero-compare' style='display:flex;align-items:center;justify-content:center;background:#f1f5f9;'>
            <span style='color:#94a3b8;font-weight:600;'>샘플 이미지를 불러오지 못했습니다.</span>
        </div>
        """

    primary_label = "복원 작업 시작하기" if is_logged_in else "카카오 계정으로 계속"
    primary_href = "#restore-app" if is_logged_in else auth_url
    caption = (
        "로그인 상태입니다. 바로 복원을 시작해보세요."
        if is_logged_in
        else "카카오 로그인 시 복원 기록이 세션에 보존됩니다."
    )

    hero_html = f"""
    <section class='hero-section'>
        <div class='hero-text'>
            <div class='hero-badge'>AI Photo Revival</div>
            <h1 class='hero-title'>오래된 사진 복원 : <span>AI로 온라인 사진 복원</span></h1>
            <p class='hero-subtext'>흑백의 시간을 되살리고, 선명한 디테일까지 복원하는 프리미엄 AI 파이프라인. 업로드만 하면 자동 색보정, 노이즈 제거, 해상도 업스케일까지 한 번에 경험할 수 있습니다.</p>
            <div class='hero-buttons'>
                <a class='cta-primary' href='{primary_href}'>
                    {primary_label}
                </a>
                <a class='cta-secondary' href='#restore-app'>게스트 모드로 먼저 체험하기</a>
            </div>
            <small class='cta-caption'>{caption}</small>
        </div>
        <div class='hero-visual'>
            <div class='hero-compare compare-ready' data-start='48'>
                <img src='data:image/png;base64,{before_b64}' alt='복원 전' class='hero-img before'/>
                <img src='data:image/png;base64,{after_b64}' alt='복원 후' class='hero-img after'/>
                <div class='hero-divider'></div>
                <span class='hero-label before'>Before</span>
                <span class='hero-label after'>After</span>
            <input type='range' min='0' max='100' value='48' class='compare-slider' aria-label='Before After slider'/>
            </div>
        </div>
    </section>
    """

    st.markdown(hero_html, unsafe_allow_html=True)


# 히어로 섹션 렌더링
render_hero_section(auth_url, "kakao_token" in st.session_state)
# ------------------------------[ 4) 복원 유틸 함수 ]---------------------------
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
        }
    return st.session_state.restoration
def image_from_bytes(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image = ImageOps.exif_transpose(image)
    return image.convert("RGB")
def image_to_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
def colorize_image(image: Image.Image) -> Image.Image:
    gray = image.convert("L")
    colorized = ImageOps.colorize(gray, black="#1e1e1e", white="#f8efe3", mid="#88a6c6")
    return colorized.convert("RGB")
def upscale_image(image: Image.Image) -> Image.Image:
    width, height = image.size
    factor = 2
    return image.resize((width * factor, height * factor), Image.LANCZOS)
def denoise_image(image: Image.Image) -> Image.Image:
    smoothed = image.filter(ImageFilter.MedianFilter(size=3))
    return smoothed.filter(ImageFilter.SMOOTH_MORE)
def format_status(counts: Dict[str, int]) -> str:
    return (
        f"[컬러화 {'✔' if counts['color'] else '✖'} / "
        f"해상도 {counts['upscale']}회 / 노이즈 {counts['denoise']}회]"
    )
def add_history_entry(label: str, image_bytes: bytes, note: Optional[str] = None):
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
    base = description.strip() or "이 사진"
    story_lines = []
    intro = f"{base}은(는) 조심스럽게 복원 과정을 거치고 있습니다."
    story_lines.append(intro)
    if photo_type == "흑백":
        if counts["color"]:
            story_lines.append(
                "흑백으로 남아 있던 순간에 색을 덧입히자 잊혔던 온기와 공기가 되살아났습니다."
            )
        else:
            story_lines.append("아직 색을 입히지 못한 채 시간 속에서 기다리고 있습니다.")
    if counts["upscale"]:
        story_lines.append(
            f"세부 묘사를 살리기 위해 해상도 보정을 {counts['upscale']}회 반복하며 흐릿했던 윤곽을 또렷하게 다듬었습니다."
        )
    if counts["denoise"]:
        story_lines.append(
            f"잡음을 정리하는 과정도 {counts['denoise']}회 진행되어 사진 속 인물의 표정과 배경이 한층 차분해졌습니다."
        )
    if not counts["upscale"] and not counts["denoise"] and counts["color"]:
        story_lines.append("색만 더했을 뿐인데도 장면의 감정이 살아 움직이는 듯합니다.")
    climax = (
        "복원된 이미지를 바라보는 지금, 사진 속 이야기가 현재의 우리에게 말을 건네는 듯합니다."
    )
    story_lines.append(climax)
    outro = "이 장면이 전하고 싶은 메시지가 있다면, 그것은 기억을 계속 이어가자는 마음일지도 모릅니다."
    story_lines.append(outro)
    wrapped = [textwrap.fill(line, width=46) for line in story_lines]
    return "\n\n".join(wrapped)
def handle_auto_colorization(photo_type: str):
    restoration = ensure_restoration_state()
    if photo_type != "흑백":
        return
    if restoration["counts"]["color"]:
        return
    original = image_from_bytes(restoration["current_bytes"])
    colorized = colorize_image(original)
    restoration["counts"]["color"] += 1
    bytes_data = image_to_bytes(colorized)
    restoration["story"] = None
    add_history_entry("컬러 복원 (자동)", bytes_data, note="흑백 이미지를 기본 팔레트로 색보정했습니다.")
def can_run_operation(operation: str, allow_repeat: bool) -> bool:
    restoration = ensure_restoration_state()
    count = restoration["counts"].get(operation, 0)
    if allow_repeat:
        return count < 3
    return count == 0
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
st.markdown(
    "<h2 class='section-title'>AI 복원 워크플로우</h2>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p class='section-lead'>업로드 → 복원 옵션 실행 → 스토리 생성까지 한눈에 진행할 수 있는 단계별 워크플로우입니다.</p>",
    unsafe_allow_html=True,
)

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
        upscale_clicked = st.button("해상도 업", use_container_width=True, disabled=not can_upscale)
        if upscale_clicked:
            run_upscale()
    with cols[1]:
        can_denoise = can_run_operation("denoise", allow_repeat)
        denoise_clicked = st.button("노이즈 제거", use_container_width=True, disabled=not can_denoise)
        if denoise_clicked:
            run_denoise()
    with cols[2]:
        can_story = can_run_operation("story", allow_repeat)
        story_clicked = st.button("스토리 생성", use_container_width=True, disabled=not can_story)
        if story_clicked:
            run_story_generation()
    st.divider()
    col_original, col_result = st.columns(2)
    with col_original:
        st.subheader("원본 이미지")
        st.image(restoration_state["original_bytes"], use_column_width=True)
        st.caption(format_status({"color": 0, "upscale": 0, "denoise": 0}))
    with col_result:
        st.subheader("복원 결과")
        if restoration_state["history"]:
            latest = restoration_state["history"][-1]
            st.image(latest["bytes"], use_column_width=True, caption=latest["label"])
            st.caption(format_status(latest["status"]))
            if latest.get("note"):
                st.markdown(f"*{latest['note']}*")
        else:
            st.info("아직 수행된 복원 작업이 없습니다.")
    if len(restoration_state["history"]) > 1:
        with st.expander("전체 작업 히스토리"):
            for idx, entry in enumerate(restoration_state["history"], 1):
                st.markdown(f"**{idx}. {entry['label']}** ({entry['timestamp']})")
                st.image(entry["bytes"], use_column_width=True)
                st.caption(format_status(entry["status"]))
                if entry.get("note"):
                    st.write(entry["note"])
                st.markdown("---")
    if restoration_state.get("story"):
        st.subheader("스토리")
        story_info = restoration_state["story"]
        st.markdown(story_info["text"])
        st.caption(
            f"생성 시각: {story_info['timestamp']} / {format_status(story_info['status'])}"
        )
st.markdown("---")
st.caption(
    "*DeOldify, ESRGAN, NAFNet 등의 실제 모델 연동을 위한 자리 표시자로, 현재는 샘플 필터를 사용합니다.*"
)
