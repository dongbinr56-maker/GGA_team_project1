# team_project1.py
# ============================================================================
# Streamlit + HTML(iframe) 하이브리드 UI
# - 카카오 OAuth: 무한 리다이렉트/화면 안에서 화면 이동 문제 해결
# - 쿼리 파라미터 API: st.query_params 만 사용 (experimental_* 전면 금지)
# - 로그인/로그아웃 이동: 항상 window.top 으로 보냄(iframe 탈출)
# - 상단 비교 미리보기: before.png / after.png 파일을 로컬에서 읽어 Data URI로 임베드
#   -> 사용자 입장에선 "파일명만 두면 됨", 컴포넌트(iframe) 입장에선 경로 문제 0%
# - 고급 옵션: 해상도 업·노이즈 제거만 반복 허용(각 3회), 스토리는 항상 1회
# - 페이지 배경/패딩: 호스트 레벨 CSS로 그라데이션 적용(앱 전체에 확실히 반영)
# ============================================================================

import os
import time
import hmac
import hashlib
import secrets
import base64
from pathlib import Path

import requests
import streamlit as st
import streamlit.components.v1 as components


# =============================
# 0) Kakao OAuth 설정
#    - 배포/로컬 환경 변수로 세팅 권장
# =============================
REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "YOUR_APP_KEY")        # 필수
REDIRECT_URI = os.getenv("KAKAO_REDIRECT_URI", "http://localhost:8501")  # 콘솔 등록값과 완전 일치해야 함(슬래시 포함)
AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL     = "https://kauth.kakao.com/oauth/token"
USERME_URL    = "https://kapi.kakao.com/v2/user/me"

# state 위변조/만료 검사용 비밀키(로컬 개발은 임의 문자열, 배포는 환경변수)
STATE_SECRET   = os.getenv("KAKAO_STATE_SECRET", "replace_with_random_secret")
STATE_TTL_SEC  = 5 * 60  # state 유효시간(초)

# 앱이 "클라이언트 시크릿 사용"으로 설정된 경우에만 사용
KAKAO_CLIENT_SECRET = os.getenv("KAKAO_CLIENT_SECRET", "")


# =============================
# 1) 유틸 함수들
# =============================
def _hmac_sha256(key: str, msg: str) -> str:
    """state 서명을 위한 HMAC-SHA256"""
    return hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest()


def make_state() -> str:
    """만료가능 + 위변조 검출 가능한 state 생성"""
    ts = str(int(time.time()))
    nonce = secrets.token_urlsafe(8)
    raw = f"{{ts}}.{{nonce}}"
    sig = _hmac_sha256(STATE_SECRET, raw)
    return f"{{raw}}.{{sig}}"


def verify_state(state: str) -> bool:
    """state 검증: 형태/서명/만료 모두 확인"""
    if not state or state.count(".") != 2:
        return False
    ts, nonce, sig = state.split(".")
    expected = _hmac_sha256(STATE_SECRET, f"{{ts}}.{{nonce}}")
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        ts_i = int(ts)
    except ValueError:
        return False
    return (time.time() - ts_i) <= STATE_TTL_SEC


def build_auth_url() -> str:
    """카카오 인가 URL 생성(반드시 state 포함)"""
    state = make_state()
    return (
        f"{{AUTHORIZE_URL}}?client_id={{REST_API_KEY}}"
        f"&redirect_uri={{REDIRECT_URI}}&response_type=code&state={{state}}"
    )


def exchange_code_for_token(code: str) -> dict:
    """인가코드 → 토큰 교환; 앱 설정에 따라 client_secret 포함"""
    data = {{
        "grant_type": "authorization_code",
        "client_id": REST_API_KEY,
        "redirect_uri": REDIRECT_URI,
        "code": code,
    }}
    if KAKAO_CLIENT_SECRET:  # 앱이 비밀키 사용 중일 때만 전송
        data["client_secret"] = KAKAO_CLIENT_SECRET
    r = requests.post(TOKEN_URL, data=data, timeout=10)
    r.raise_for_status()
    return r.json()


def get_user_profile(access_token: str) -> dict:
    """토큰으로 사용자 정보 조회"""
    r = requests.get(
        USERME_URL,
        headers={{"Authorization": f"Bearer {{access_token}}"}},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def extract_profile(user_me: dict):
    """응답에서 닉네임/프로필 이미지 추출(없으면 공백)"""
    account = (user_me or {}).get("kakao_account", {}) or {}
    profile = account.get("profile", {}) or {}
    nickname = profile.get("nickname") or ""
    img = profile.get("profile_image_url") or profile.get("thumbnail_image_url") or ""
    return nickname, img


def data_uri(filename: str) -> str:
    """
    파일명(상대경로)만 받아 Data URI로 변환.
    - Streamlit components.html은 iframe 이라 <img src="파일명"> 경로가 어긋날 수 있음.
    - Data URI로 임베드하면 경로 문제 없이 항상 표시됨.
    """
    p = Path(filename)
    if not p.exists():
        # 파일 없으면 플레이스홀더
        return "https://placehold.co/960x540/cccccc/000?text=Missing+Image"
    b64 = base64.b64encode(p.read_bytes()).decode()
    ext = p.suffix.lower()
    if ext in (".png", ".webp"):
        mime = f"image/{{ext[1:]}}"
    else:
        mime = "image/jpeg"
    return f"data:{{mime}};base64,{{b64}}"


# =============================
# 2) 앱 시작/글로벌 CSS(호스트 레벨)
# =============================
st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

# 호스트 컨테이너에 직접 배경/패딩을 적용해야 "페이지 전체"에 먹음
st.markdown(
    """
<style>
  :root{{ --page-side: 1rem; --page-top: 3rem; --page-bottom: 10rem; }}

  /* 전체 배경(그라데이션) — html/body/stAppViewContainer 모두 타깃 */
  html, body, [data-testid="stAppViewContainer"]{{
    background:
      radial-gradient(1200px 800px at 20% -10%, #ffe9f3, transparent 60%),
      radial-gradient(1200px 800px at 110% 10%, #eaf0ff, transparent 55%),
      linear-gradient(135deg, #fff5fb, #f3f7ff) !important;
  }}

  /* 메인 블록 컨테이너 패딩 */
  [data-testid="block-container"]{{
    padding: var(--page-top) var(--page-side) var(--page-bottom) !important;
    max-width: initial !important; min-width: auto !important;
  }}
</style>
""",
    unsafe_allow_html=True,
)

# 미리보기 이미지: "파일명만" 요구 → 내부적으로 Data URI로 변환해 iframe에서도 안전 표시
BEFORE_URI = data_uri("before.png")  # 왼쪽(흑백)
AFTER_URI  = data_uri("after.png")   # 오른쪽(컬러)


# =============================
# 3) 쿼리 파라미터 유틸(오직 st.query_params)
# =============================
def get_qp() -> dict:
    """Streamlit 새 API만 사용; 모든 값을 문자열 하나로 평탄화"""
    q = st.query_params
    out = {}
    for k, v in q.items():
        if isinstance(v, (list, tuple)):
            out[k] = v[0]
        elif v is None:
            out[k] = ""
        else:
            out[k] = str(v)
    return out


def clear_qp() -> None:
    """주소창의 쿼리파람 전체 제거"""
    st.query_params.clear()


qp = get_qp()


# =============================
# 4) 로그아웃 처리 (?logout=1)
# =============================
if qp.get("logout"):
    for k in ("kakao_token", "kakao_profile", "_kakao_code_handled"):
        st.session_state.pop(k, None)
    clear_qp()
    st.rerun()


# =============================
# 5) 카카오 콜백 처리 (무한 루프 방지)
# =============================
err_msg = ""
code  = qp.get("code")
state = qp.get("state")

# 같은 code를 두 번 이상 처리하지 않도록 세션 가드
if code and (st.session_state.get("_kakao_code_handled") != code):
    try:
        if not verify_state(state):
            err_msg = "상태 토큰 검증 실패(만료/위조 가능성). 다시 로그인 해주세요."
        else:
            tok = exchange_code_for_token(code)
            st.session_state["kakao_token"] = tok
            access = tok.get("access_token")
            user_me = get_user_profile(access) if access else {}
            nickname, img = extract_profile(user_me)
            st.session_state["kakao_profile"] = {{"nickname": nickname, "img": img}}
    except requests.HTTPError as e:
        err_msg = f"카카오 인증 에러: {{e}}"
    finally:
        # 처리한 code 기록 + URL 정리 → rerun 한 번만
        st.session_state["_kakao_code_handled"] = code
        clear_qp()
        st.rerun()


# =============================
# 6) 세션 스냅샷/상수
# =============================
logged_in = "kakao_token" in st.session_state
nickname = (st.session_state.get("kakao_profile") or {}).get("nickname") or ""
avatar   = (st.session_state.get("kakao_profile") or {}).get("img") or ""

AUTH_URL = build_auth_url()  # 로그인 URL(HTML에도 주입)


if err_msg:
    st.warning(err_msg)


# =============================
# 7) HTML 앱(컴포넌트). 로그인/로그아웃은 항상 window.top 으로!
# =============================
html_code = f"""
<!DOCTYPE html>
<html lang="ko" class="pre-animate">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <!-- 로그인/로그아웃 이동을 무조건 상위 창으로 보내기 -->
  <base target="_top">
  <title>사진 복원 + 스토리 생성 (Kakao OAuth)</title>
  <style>
    :root{{{{
      --pink:#ec4899; --text-strong:#111827; --text-muted:#4b5563; --card:#ffffff;
      --shadow:0 24px 60px -34px rgba(15,23,42,0.35); --radius:28px; --ease:cubic-bezier(.2,.8,.2,1);
    }}}}
    *{{{{box-sizing:border-box}}}}
    body{{{{ margin:0; font-family: ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Apple Color Emoji,Segoe UI Emoji; background:transparent; }}}}
    a{{{{color:inherit;text-decoration:none}}}} button{{{{font-family:inherit}}}}

    .navbar{{{{ position:fixed; top:0; left:0; right:0; height:60px; display:flex; align-items:center; justify-content:space-between;
             padding:0 18px; background:#fff; box-shadow:0 2px 6px rgba(0,0,0,0.08); z-index:1000; }}}}
    .brand{{{{ font-weight:800; letter-spacing:0.1px; }}}}

    .hero-wrap{{{{ margin-top:80px; }}}}
    .hero-card{{{{ background: linear-gradient(135deg, rgba(255, 220, 237, 0.65), rgba(255,255,255,0.96) 65%);
                border:1px solid rgba(255,255,255,0.7); border-radius:var(--radius); box-shadow:var(--shadow);
                padding:32px; max-width:1280px; margin:0 auto; position:relative; }}}}
    .hero-inner{{{{ display:grid; grid-template-columns: minmax(0,1.05fr) minmax(0,1fr); gap:52px; align-items:center; }}}}
    @media (max-width: 1100px){{{{ .hero-inner{{{{ grid-template-columns: 1fr; }}}} }}}}

    .hero-title{{{{ font-size:2.8rem; font-weight:800; color:var(--text-strong); margin:0 0 14px 0; }}}}
    .hero-title span{{{{ color:var(--pink); }}}}
    .hero-sub{{{{ color:var(--text-muted); line-height:1.65; font-size:1.08rem; margin:0 0 22px 0; }}}}
    .cta-row{{{{ display:flex; gap:12px; flex-wrap:wrap; }}}}
    .btn{{{{ display:inline-flex; align-items:center; justify-content:center; gap:8px; height:48px; padding:0 22px; border-radius:12px; border:1px solid transparent;
           font-weight:800; cursor:pointer; transition:transform .06s ease; user-select:none; min-width:220px; }}}}
    .btn:active{{{{ transform:translateY(1px); }}}}
    .btn-kakao{{{{ background:#FEE500; color:#000; border-color:rgba(0,0,0,.08); }}}}
    .btn-ghost{{{{ background:#fff; color:var(--pink); border-color:var(--pink); }}}}

    .compare-wrap{{{{ position:relative; width:100%; max-width:720px; margin:0 auto;
                    background: linear-gradient(145deg, rgba(255, 228, 240, 0.50), rgba(255,255,255,0.92) 70%);
                    border-radius:18px; border:1px solid rgba(255,255,255,0.85);
                    box-shadow:0 16px 40px -24px rgba(15,23,42,0.4); padding:18px; touch-action:none; }}}}
    .canvas{{{{ position:relative; width:100%; padding-top:56.25%; overflow:hidden; border-radius:12px; background:#fff; cursor:ew-resize; }}}}
    .canvas img{{{{ position:absolute; top:0; left:0; width:100%; height:100%; object-fit:cover; pointer-events:none; image-rendering:auto; }}}}
    .img-overlay{{{{ clip-path: inset(0 50% 0 0); will-change: clip-path; }}}}
    .divider{{{{ position:absolute; top:0; bottom:0; left:0; width:3px; background:#fff; pointer-events:none; transform: translateX(50%); will-change: transform; }}}}
    .badge{{{{ position:absolute; top:8px; padding:6px 10px; border-radius:999px; font-weight:800; font-size:.85rem; color:#111827;
             background:rgba(255,255,255,.9); border:1px solid rgba(0,0,0,.06); pointer-events:none; user-select:none; }}}}
    .badge-left{{{{ left:8px; }}}} .badge-right{{{{ right:8px; }}}}

    .section{{{{ max-width:1100px; margin:36px auto; padding:0; }}}}
    .muted{{{{ color:#475569; }}}}
    .panel{{{{ background:var(--card); border-radius:16px; border:1px solid rgba(0,0,0,0.06); box-shadow:0 10px 24px -16px rgba(15,23,42,0.25); padding:18px; margin-top:18px; }}}}
    .row{{{{ display:flex; gap:14px; flex-wrap:wrap; align-items:center; }}}} .row label{{{{ font-weight:700; }}}} .sep{{{{ height:1px; background:rgba(0,0,0,0.06); margin:14px 0; }}}}

    .btn-op{{{{ background:#111827; color:#fff; border:1px solid #111827; padding:10px 16px; border-radius:10px; font-weight:700; cursor:pointer; }}}}
    .btn-op[disabled]{{{{ opacity:0.4; cursor:not-allowed; }}}}

    .drawer-toggle{{{{ position:fixed; top:96px; left:12px; display:none; padding:10px 12px; background:#fff; border:1px solid rgba(0,0,0,0.08);
                     border-radius:999px; box-shadow:0 8px 20px -12px rgba(15,23,42,0.4); z-index:1201; cursor:pointer; font-weight:800; }}}}
    .drawer{{{{ position:fixed; top:0; left:0; bottom:0; width:320px; background:#ffffff; box-shadow:12px 0 30px -18px rgba(15,23,42,0.35);
              transform: translateX(-100%); transition: transform .2s ease; z-index:1202; display:flex; flex-direction:column; }}}}
    .drawer.open{{{{ transform: translateX(0%); }}}}
    .drawer-head{{{{ padding:18px; border-bottom:1px solid rgba(0,0,0,0.06); display:flex; align-items:center; gap:12px; }}}}
    .avatar{{{{ width:44px; height:44px; border-radius:999px; background:#eee; overflow:hidden; }}}}
    .avatar img{{{{ width:100%; height:100%; object-fit:cover; display:block; }}}}
    .name{{{{ font-weight:800; }}}}
    .logout{{{{ margin-left:auto; background:#fff; border:1px solid rgba(0,0,0,0.12); border-radius:999px; padding:8px 12px; cursor:pointer; font-weight:700; }}}}
    .drawer-body{{{{ padding:18px; overflow:auto; }}}}

    .backdrop{{{{ position:fixed; inset:0; background:rgba(0,0,0,0.28); opacity:0; pointer-events:none; transition:opacity .15s ease; z-index:1200;
                backdrop-filter:saturate(120%) blur(1.5px); }}}}
    .backdrop.show{{{{ opacity:1; pointer-events:auto; }}}}

    .toast{{{{ position:fixed; left:50%; bottom:24px; transform:translateX(-50%); background:#111827; color:#fff; padding:10px 14px; border-radius:10px;
             opacity:0; transition:opacity .2s ease; pointer-events:none; z-index:1300; }}}}
    .toast.show{{{{ opacity:0.95; }}}}

    /* 입장 애니메이션 */
    .will-animate{{{{ opacity:0; }}}}
    @keyframes slideL {{{{ from{{{{opacity:0; transform:translateX(-24px)}}}} to{{{{opacity:1; transform:translateX(0)}}}} }}}}
    @keyframes slideR {{{{ from{{{{opacity:0; transform:translateX(24px)}}}} to{{{{opacity:1; transform:translateX(0)}}}} }}}}
    @keyframes slideDown {{{{ from{{{{opacity:0; transform:translateY(-12px)}}}} to{{{{opacity:1; transform:translateY(0)}}}} }}}}
    @keyframes fadeUp {{{{ from{{{{opacity:0; transform:translateY(12px)}}}} to{{{{opacity:1; transform:translateY(0)}}}} }}}}
    .animate .reveal-l{{{{ animation: slideL .6s var(--ease) .05s both; }}}}
    .animate .reveal-r{{{{ animation: slideR .6s var(--ease) .10s both; }}}}
    .animate .reveal-down{{{{ animation: slideDown .5s var(--ease) .02s both; }}}}
    .animate .reveal-up{{{{ animation: fadeUp .6s var(--ease) .18s both; }}}}
    @media (prefers-reduced-motion: reduce){{{{ .will-animate{{{{ opacity:1 !important; }}}} .animate .reveal-l, .animate .reveal-r, .animate .reveal-down, .animate .reveal-up{{{{ animation:none !important; }}}} }}}}
  </style>
</head>
<body>
  <div class="navbar will-animate reveal-down">
    <div class="brand">My Restoration Service</div>
    <div style="font-size:.9rem;color:#6b7280;">HTML-only prototype</div>
  </div>

  <div class="hero-wrap">
    <div class="hero-card">
      <div class="hero-inner">
        <div class="hero-left will-animate reveal-l">
          <h1 class="hero-title">오래된 사진 복원 : <span>AI로 온라인 사진 복원</span></h1>
          <p class="hero-sub">흑백은 왼쪽, 컬러는 오른쪽. 캔버스를 드래그해서 비교하세요.</p>
          <div class="cta-row will-animate reveal-up">
            <!-- a 태그 자체에도 target=_top / JS에서도 window.top으로 강제 -->
            <a class="btn btn-kakao" id="btnLogin" href="{{AUTH_URL}}" target="_top" rel="noopener">카카오 계정으로 계속</a>
            <a class="btn btn-ghost" href="#" id="btnGuest">게스트 모드로 먼저 체험하기</a>
          </div>
        </div>
        <div class="hero-right will-animate reveal-r">
          <div class="compare-wrap">
            <div class="canvas" id="canvas">
              <!-- 오른쪽: 컬러(After), 왼쪽: 흑백(Before) -->
              <img src="{{AFTER_URI}}"  alt="After"  class="img-bottom">
              <img src="{{BEFORE_URI}}" alt="Before" class="img-overlay" id="overlayImg">
              <div class="divider" id="divider"></div>
              <div class="badge badge-left">Before</div>
              <div class="badge badge-right">After</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="section" id="restore-app">
    <h2>AI 복원 워크플로우</h2>
    <p class="muted">UI 데모 / 실제 처리는 추후 연동</p>
    <div class="panel will-animate reveal-up">
      <div class="row">
        <label>사진 업로드</label>
        <input type="file" id="fileInput" accept="image/*">
        <span class="muted" style="font-size:.9rem">(상단 미리보기는 고정 샘플을 사용합니다)</span>
      </div>
      <div class="sep"></div>
      <div class="row">
        <label>사진 유형</label>
        <label><input type="radio" name="ptype" value="흑백" checked> 흑백</label>
        <label><input type="radio" name="ptype" value="컬러"> 컬러</label>
      </div>
      <div class="row" style="margin-top:8px">
        <label style="display:flex;align-items:center;gap:8px">
          <input type="checkbox" id="chkAdvanced">
          <span>고급 옵션 (해상도 업/노이즈 제거만 반복 허용, 각 최대 3회)</span>
        </label>
      </div>
      <div class="sep"></div>
      <div class="row">
        <button class="btn-op" id="btnUpscale">해상도 업</button>
        <button class="btn-op" id="btnDenoise">노이즈 제거</button>
        <button class="btn-op" id="btnStory">스토리 생성</button>
      </div>
    </div>
  </div>

  <div class="backdrop" id="backdrop"></div>
  <button class="drawer-toggle" id="drawerToggle">프로필</button>
  <aside class="drawer" id="drawer">
    <div class="drawer-head">
      <div class="avatar" id="avatarSlot"></div>
      <div class="name"   id="nameSlot">Kakao User</div>
      <button class="logout" id="btnLogout">로그아웃</button>
    </div>
    <div class="drawer-body">
      <p class="muted">로그인 후 노출되는 사이드 슬라이드입니다. 상단에 프로필/이름/로그아웃.</p>
      <div style="height:600px"></div>
    </div>
  </aside>

  <div class="toast" id="toast"></div>

  <script>
    // 0) 초기 진입 애니메이션
    window.addEventListener('load', () => {{
      document.documentElement.classList.remove('pre-animate');
      document.documentElement.classList.add('animate');
    }});

    // 1) 로그인은 항상 최상위 창으로 이동(iframe 탈출)
    const AUTH_URL = {{repr(AUTH_URL)}};
    document.getElementById('btnLogin').addEventListener('click', (e) => {{
      e.preventDefault();
      window.top.location.href = AUTH_URL;
    }});

    // 2) 게스트는 아래 워크플로우로 스크롤만
    document.getElementById('btnGuest').addEventListener('click', (e) => {{
      e.preventDefault();
      document.querySelector('#restore-app').scrollIntoView({{behavior:'smooth', block:'start'}});
    }});

    // 3) 캔버스 슬라이더: rAF로 부드럽게
    const canvas = document.getElementById('canvas');
    const overlay = document.getElementById('overlayImg');
    const divider = document.getElementById('divider');
    let dragging=false, scheduled=false, last=50;

    function applySplit(pct){{
      pct = Math.max(0, Math.min(100, pct));
      overlay.style.clipPath = 'inset(0 ' + (100-pct) + '% 0 0)';
      const rect = canvas.getBoundingClientRect();
      divider.style.transform = 'translateX(' + (rect.width * (pct/100)) + 'px)';
    }}
    function schedule(pct){{ last=pct; if(scheduled) return; scheduled=true; requestAnimationFrame(()=>{{ applySplit(last); scheduled=false; }}); }}
    function posToPercent(evt){{ const r=canvas.getBoundingClientRect(); const x=(evt.clientX ?? (evt.touches&&evt.touches[0].clientX) ?? 0)-r.left; return (x/r.width)*100; }}

    canvas.addEventListener('pointerdown', e=>{{ dragging=true; schedule(posToPercent(e)); }});
    canvas.addEventListener('pointermove', e=>{{ if(dragging) schedule(posToPercent(e)); }});
    window.addEventListener('pointerup', ()=> dragging=false);
    canvas.addEventListener('pointerleave', ()=> dragging=false);
    applySplit(50);

    // 4) 작업 제한: 고급 ON이면 해상도/노이즈 3회, 스토리는 항상 1회
    const LIMITS_BASIC = {{ upsc:1, deno:1, story:1 }};
    const LIMITS_ADV   = {{ upsc:3, deno:3, story:1 }};
    const state = {{ advanced:false, counts:{{upsc:0, deno:0, story:0}} }};

    const $ = s => document.querySelector(s);
    function getMax(k){{ return state.advanced ? LIMITS_ADV[k] : LIMITS_BASIC[k]; }}
    function disableIfLimit(btn, key){{ btn.disabled = state.counts[key] >= getMax(key); }}
    function refreshOps(){{ disableIfLimit($('#btnUpscale'),'upsc'); disableIfLimit($('#btnDenoise'),'deno'); disableIfLimit($('#btnStory'),'story'); }}
    function toast(msg){{ const t=document.getElementById('toast'); t.textContent=msg; t.classList.add('show'); setTimeout(()=>t.classList.remove('show'),1200); }}

    document.getElementById('chkAdvanced').addEventListener('change', e=>{{
      state.advanced = !!e.target.checked; refreshOps();
      toast(state.advanced ? "고급 옵션: 해상도/노이즈만 최대 3회" : "기본 모드: 모든 작업 1회");
    }});

    document.getElementById('btnUpscale').addEventListener('click', ()=>{{
      if(state.counts.upsc >= getMax('upsc')) return;
      state.counts.upsc++;
      document.querySelector('.img-bottom').style.filter = "contrast(1.03) saturate(1.02)";
      refreshOps();
    }});
    document.getElementById('btnDenoise').addEventListener('click', ()=>{{
      if(state.counts.deno >= getMax('deno')) return;
      state.counts.deno++;
      const img=document.querySelector('.img-bottom'); const cur=getComputedStyle(img).filter;
      img.style.filter = "blur(0.3px) " + (cur && cur!=='none' ? cur : "");
      refreshOps();
    }});
    document.getElementById('btnStory').addEventListener('click', ()=>{{
      if(state.counts.story >= getMax('story')) return;
      state.counts.story++;
      alert("스토리 생성은 데모입니다. 실제 모델은 추후 연동됩니다.");
      refreshOps();
    }});

    // 5) 드로어(로그인 후 노출되는 사이드 슬라이드)
    function openDrawer(){{ $('#drawer').classList.add('open'); $('#backdrop').classList.add('show'); }}
    function closeDrawer(){{ $('#drawer').classList.remove('open'); $('#backdrop').classList.remove('show'); }}
    document.getElementById('drawerToggle').addEventListener('click', openDrawer);
    document.getElementById('backdrop').addEventListener('click', closeDrawer);
    window.addEventListener('keydown', e=>{{ if(e.key==='Escape') closeDrawer(); }});

    // 6) 로그아웃도 최상위로(iframe 탈출)
    document.getElementById('btnLogout').addEventListener('click', ()=>{{
      const url = new URL(window.top.location.href);
      url.search = '?logout=1';
      window.top.location.replace(url.toString());
    }});

    // 7) 업로드 안내(미리보기는 고정 샘플)
    document.getElementById('fileInput').addEventListener('change', ()=>{{
      toast("업로드 파일은 상단 미리보기를 변경하지 않습니다.");
    }});
  </script>
</body>
</html>
"""

# HTML을 스트림릿에 삽입(컴포넌트 높이는 필요 시 조절)
components.html(html_code, height=1100, scrolling=True)
