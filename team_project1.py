# ============================================================
# "오래된 사진 복원 : AI로 온라인 사진 복원" + 복원 워크플로우 전체
# ============================================================

from typing import Tuple, Dict, Optional
import base64
import io
import os
import time
import hmac
import hashlib
import secrets
from pathlib import Path
import textwrap
from datetime import datetime

import requests
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageFilter, ImageOps

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

# ------------------------------
# [설정] 페이지 레이아웃
# ------------------------------
st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

# ================================
# Kakao OAuth 설정
# ================================
REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "caf4fd09d45864146cb6e75f70c713a1")
REDIRECT_URI = os.getenv("KAKAO_REDIRECT_URI", "https://hackteam32.streamlit.app")
STATE_SECRET = os.getenv("KAKAO_STATE_SECRET", "UzdfMyaTkcNsJ2eVnRoKjUIOvWbeAy5E")

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

# ------------------------------[ 콜백/로그아웃 처리 ]------------------------
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

# ------------------------------
# Hero 섹션 Before/After 비교
# ------------------------------
BEFORE_PATH = Path("before.png")
AFTER_PATH  = Path("after.png")

def pil_to_data_uri(img: Image.Image, fmt: str = "JPEG", quality: int = 90) -> str:
    buf = io.BytesIO()
    img.save(buf, format=fmt, quality=quality)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    mime = "image/png" if fmt.upper() == "PNG" else "image/jpeg"
    return f"data:{mime};base64,{b64}"

def load_examples(max_width: int = 300):
    if not BEFORE_PATH.exists() or not AFTER_PATH.exists():
        st.error("예시 이미지가 없습니다. before.png, after.png 를 넣어주세요.")
        st.stop()
    before = Image.open(BEFORE_PATH).convert("RGB")
    after  = Image.open(AFTER_PATH).convert("RGB")
    def shrink(im: Image.Image) -> Image.Image:
        if im.width > max_width:
            h = int(im.height * (max_width / im.width))
            return im.resize((max_width, h))
        return im
    before = shrink(before)
    after  = shrink(after)
    est_h = int(after.height * min(1.0, 800 / max(after.width, 1)))
    est_h = max(300, min(est_h, 520))
    return before, after, est_h

before_img, after_img, hero_h = load_examples(max_width=750)
before_b64 = pil_to_data_uri(before_img, fmt="JPEG", quality=90)
after_b64  = pil_to_data_uri(after_img,  fmt="JPEG", quality=90)

def render_compare(before_b64: str, after_b64: str, start: int = 50, height_px: int = 400):
    html = f"""
    <div style="position:relative;width:100%;height:{height_px}px;overflow:hidden;">
      <span style="position:absolute;top:12px;left:12px;background:#fff;padding:4px 8px;border-radius:6px;font-weight:700;">Before</span>
      <span style="position:absolute;top:12px;right:12px;background:#fff;padding:4px 8px;border-radius:6px;font-weight:700;">After</span>
      <img style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;" src="{before_b64}" />
      <img class="hero-img after" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;clip-path:inset(0 {100-start}% 0 0);" src="{after_b64}" />
      <div id="divider" style="position:absolute;top:0;bottom:0;width:3px;background:#fff;left:{start}%;"></div>
    </div>
    """
    components.html(html, height=height_px+40)

with st.container():
    left_col, right_col = st.columns([0.9, 0.8])
    with left_col:
        if "kakao_profile" in st.session_state:
            st.markdown(
                '<div class="left-stack">'
                '<div class="hero-title">오래된 사진 복원 :<br> <span class="em">AI로 온라인 사진 복원</span></div>'
                '<div class="hero-sub">바랜 사진 속 미소가 다시 빛나고, 잊힌 장면들이 생생하게 살아납니다.</div>'
                '</div>',
                unsafe_allow_html=True
            )
        else:
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
    with right_col:
        render_compare(before_b64, after_b64, start=50, height_px=hero_h)

# ======================================================================
# 📌 여기서부터 back.py의 복원 워크플로우 통째로 합침
# ======================================================================

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
    return image.resize((width * 2, height * 2), Image.LANCZOS)

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
            story_lines.append("흑백으로 남아 있던 순간에 색을 덧입히자 잊혔던 온기와 공기가 되살아났습니다.")
        else:
            story_lines.append("아직 색을 입히지 못한 채 시간 속에서 기다리고 있습니다.")
    if counts["upscale"]:
        story_lines.append(f"세부 묘사를 살리기 위해 해상도 보정을 {counts['upscale']}회 반복했습니다.")
    if counts["denoise"]:
        story_lines.append(f"잡음을 정리하는 과정도 {counts['denoise']}회 진행되었습니다.")
    climax = "복원된 이미지를 바라보는 지금, 사진 속 이야기가 현재의 우리에게 말을 건네는 듯합니다."
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

# ------------------------------[ 복원 UI ]------------------------------
st.title("📌 사진 복원 + 스토리 생성")
restoration_state = ensure_restoration_state()

with st.container():
    st.subheader("1. 사진 업로드")
    photo_type = st.radio("사진 유형", ["흑백", "컬러"], horizontal=True, key="photo_type_selector")
    description = st.text_input("사진에 대한 간단한 설명", key="photo_description", placeholder="예: 1970년대 외할아버지의 결혼식")
    uploaded_file = st.file_uploader("사진 파일 업로드", type=["png","jpg","jpeg","bmp","tiff"], key="photo_uploader")
    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        digest = hashlib.sha1(file_bytes).hexdigest()
        if restoration_state["upload_digest"] != digest:
            reset_restoration(digest, file_bytes, photo_type, description)
            handle_auto_colorization(photo_type)
        else:
            restoration_state["description"] = description
            restoration_state["photo_type"] = photo_type

allow_repeat = st.checkbox("고급 옵션 - 동일 작업 반복 허용 (최대 3회)")
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
        if st.button("노이즈 제거", use_container_width=True, disabled=not can_upscale):
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
        st.caption(
            f"생성 시각: {story_info['timestamp']} / {format_status(story_info['status'])}"
        )

        st.markdown("---")
        st.caption(
            "*DeOldify, ESRGAN, NAFNet 등의 실제 모델 연동을 위한 자리 표시자로, 현재는 샘플 필터를 사용합니다.*"
        )
