
import os, time, hmac, hashlib, secrets, requests, base64
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

# =============================
# Kakao OAuth settings
# =============================
REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "caf4fd09d45864146cb6e75f70c713a1")
REDIRECT_URI = os.getenv("KAKAO_REDIRECT_URI", "https://hackteam32.streamlit.app")
STATE_SECRET = os.getenv("KAKAO_STATE_SECRET", "UzdfMyaTkcNsJ2eVnRoKjUIOvWbeAy5E")
AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL     = "https://kauth.kakao.com/oauth/token"
USERME_URL    = "https://kapi.kakao.com/v2/user/me"
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
    return (time.time() - ts_i) <= STATE_TTL_SEC

def build_auth_url() -> str:
    state = make_state()
    return (
        f"{AUTHORIZE_URL}?client_id={REST_API_KEY}"
        f"&redirect_uri={REDIRECT_URI}&response_type=code&state={state}"
    )

def exchange_code_for_token(code: str) -> dict:
    data = {
        "grant_type": "authorization_code",
        "client_id": REST_API_KEY,
        "redirect_uri": REDIRECT_URI,
        "code": code,
        "client_secret": STATE_SECRET,
    }
    r = requests.post(TOKEN_URL, data=data, timeout=10)
    r.raise_for_status()
    return r.json()

def get_user_profile(access_token: str) -> dict:
    r = requests.get(USERME_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
    r.raise_for_status()
    return r.json()

def extract_profile(user_me: dict):
    account = (user_me or {}).get("kakao_account", {}) or {}
    profile = account.get("profile", {}) or {}
    nickname = profile.get("nickname") or None
    img = profile.get("profile_image_url") or profile.get("thumbnail_image_url") or None
    return nickname, img

def data_uri(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return "https://placehold.co/960x540/cccccc/000?text=Missing+Image"
    b64 = base64.b64encode(p.read_bytes()).decode()
    mime = "image/png" if p.suffix.lower()==".png" else "image/jpeg"
    return f"data:{mime};base64,{b64}"

# =============================
# App start
# =============================
st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

BEFORE_URI = data_uri("before.png")
AFTER_URI  = data_uri("after.png")

# Handle logout via ?logout=1
try:
    qp = dict(st.query_params)
except Exception:
    qp = st.experimental_get_query_params()
if qp.get("logout"):
    for k in ["kakao_token", "kakao_profile"]:
        if k in st.session_state:
            del st.session_state[k]
    try:
        st.query_params.clear()
    except Exception:
        st.experimental_set_query_params()
    st.rerun()

# Handle Kakao callback
err_msg = ""
code = qp.get("code")
state = qp.get("state")
if code:
    try:
        if not verify_state(state):
            err_msg = "상태 토큰 검증 실패(만료/위조 가능성). 다시 로그인 해주세요."
        else:
            tok = exchange_code_for_token(code)
            st.session_state["kakao_token"] = tok
            access = tok.get("access_token")
            user_me = get_user_profile(access) if access else {}
            nickname, img = extract_profile(user_me)
            st.session_state["kakao_profile"] = {"nickname": nickname, "img": img}
            try:
                st.query_params.clear()
            except Exception:
                st.experimental_set_query_params()
            st.rerun()
    except requests.HTTPError as e:
        err_msg = f"카카오 인증 에러: {e}"

logged_in = "kakao_token" in st.session_state
nickname = (st.session_state.get("kakao_profile") or {}).get("nickname") or ""
avatar = (st.session_state.get("kakao_profile") or {}).get("img") or ""
AUTH_URL = build_auth_url()

if err_msg:
    st.warning(err_msg)

html_code = f"""
<!DOCTYPE html>
<html lang='ko' class='pre-animate'>
<head>
<meta charset='utf-8'/>
<meta name='viewport' content='width=device-width, initial-scale=1'/>
<title>사진 복원 + 스토리 생성 (Kakao OAuth)</title>
<style>
  :root{{
    --pink:#ec4899; --bg-grad-1:#fff7fb; --bg-grad-2:#eff6ff;
    --text-strong:#111827; --text-muted:#4b5563; --card:#ffffff;
    --shadow:0 24px 60px -34px rgba(15,23,42,0.35);
    --radius:28px; --ease:cubic-bezier(.2,.8,.2,1);
  }}
  *{{box-sizing:border-box}}
  body{{
    margin:0; font-family: ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Apple Color Emoji,Segoe UI Emoji;
    background:radial-gradient(1200px 800px at 20% -10%, var(--bg-grad-1), transparent 60%),
               radial-gradient(1200px 800px at 110% 10%, var(--bg-grad-2), transparent 55%),
               linear-gradient(135deg, #fff, #fafbff);
  }}
  a{{color:inherit;text-decoration:none}} button{{font-family:inherit}}

  /* Page padding */
  .page{{ width:100%; padding:3rem 1rem 10rem; max-width:initial; min-width:auto; }}
  @media (min-width: calc(736px + 1rem)){{ .page{{ padding-left:4rem; padding-right:4rem; }} }}

  .navbar{{ position:fixed; top:0; left:0; right:0; height:60px; display:flex; align-items:center; justify-content:space-between;
           padding:0 18px; background:#fff; box-shadow:0 2px 6px rgba(0,0,0,0.08); z-index:1000; }}
  .brand{{ font-weight:800; letter-spacing:0.1px; }}

  .hero-wrap{{ margin-top:80px; padding:0; }}
  /* Soft pink -> white gradient surface */
  .hero-card{{
    background: linear-gradient(135deg, rgba(255, 220, 237, 0.65), rgba(255,255,255,0.96) 65%);
    border:1px solid rgba(255,255,255,0.7);
    border-radius:var(--radius);
    box-shadow:var(--shadow);
    padding:32px; max-width:1280px; margin:0 auto; position:relative;
  }}

  .hero-inner{{ display:grid; grid-template-columns: minmax(0,1.05fr) minmax(0,1fr); gap:52px; align-items:center; }}
  @media (max-width: 1100px){{ .hero-inner{{ grid-template-columns: 1fr; }} }}

  .hero-title{{ font-size:2.8rem; font-weight:800; color:var(--text-strong); margin:0 0 14px 0; }}
  .hero-title span{{ color:var(--pink); }}
  .hero-sub{{ color:var(--text-muted); line-height:1.65; font-size:1.08rem; margin:0 0 22px 0; }}
  .cta-row{{ display:flex; gap:12px; flex-wrap:wrap; }}
  .btn{{ display:inline-flex; align-items:center; justify-content:center; gap:8px; height:48px; padding:0 22px; border-radius:12px; border:1px solid transparent;
         font-weight:800; cursor:pointer; transition:transform .06s ease; user-select:none; min-width:220px; }}
  .btn:active{{ transform:translateY(1px); }} .btn-kakao{{ background:#FEE500; color:#000; border-color:rgba(0,0,0,.08); }}
  .btn-ghost{{ background:#fff; color:var(--pink); border-color:var(--pink); }}

  /* Compare surface with gentle pink->white gradient */
  .compare-wrap{{
    position:relative; width:100%; max-width:720px; margin:0 auto;
    background: linear-gradient(145deg, rgba(255, 228, 240, 0.50), rgba(255,255,255,0.92) 70%);
    border-radius:18px; border:1px solid rgba(255,255,255,0.85);
    box-shadow:0 16px 40px -24px rgba(15,23,42,0.4);
    padding:18px; touch-action:none;
  }}
  .canvas{{ position:relative; width:100%; padding-top:56.25%; overflow:hidden; border-radius:12px; background:#fff; cursor:ew-resize; }}
  .canvas img{{ position:absolute; top:0; left:0; width:100%; height:100%; object-fit:cover; pointer-events:none; image-rendering:auto; }}
  .img-overlay{{ clip-path: inset(0 50% 0 0); will-change: clip-path; }}
  .divider{{ position:absolute; top:0; bottom:0; left:0; width:3px; background:#fff; pointer-events:none; transform: translateX(50%); will-change: transform; }}
  .badge{{ position:absolute; top:8px; padding:6px 10px; border-radius:999px; font-weight:800; font-size:.85rem; color:#111827; background:rgba(255,255,255,.9); border:1px solid rgba(0,0,0,.06); pointer-events:none; user-select:none; }}
  .badge-left{{ left:8px; }} .badge-right{{ right:8px; }}

  .section{{ max-width:1100px; margin:36px auto; padding:0; }} .muted{{ color:#475569; }}
  .panel{{ background:var(--card); border-radius:16px; border:1px solid rgba(0,0,0,0.06); box-shadow:0 10px 24px -16px rgba(15,23,42,0.25); padding:18px; margin-top:18px; }}
  .row{{ display:flex; gap:14px; flex-wrap:wrap; align-items:center; }} .row label{{ font-weight:700; }} .sep{{ height:1px; background:rgba(0,0,0,0.06); margin:14px 0; }}
  .btn-op{{ background:#111827; color:#fff; border:1px solid #111827; padding:10px 16px; border-radius:10px; font-weight:700; cursor:pointer; }} .btn-op[disabled]{{ opacity:0.4; cursor:not-allowed; }}

  /* Drawer + backdrop (unchanged) */
  .drawer-toggle{{ position:fixed; top:96px; left:12px; display:none; padding:10px 12px; background:#fff; border:1px solid rgba(0,0,0,0.08); border-radius:999px; box-shadow:0 8px 20px -12px rgba(15,23,42,0.4); z-index:1201; cursor:pointer; font-weight:800; }}
  .drawer{{ position:fixed; top:0; left:0; bottom:0; width:320px; background:#ffffff; box-shadow:12px 0 30px -18px rgba(15,23,42,0.35); transform: translateX(-100%); transition: transform .2s ease; z-index:1202; display:flex; flex-direction:column; }}
  .drawer.open{{ transform: translateX(0%); }} .drawer-head{{ padding:18px; border-bottom:1px solid rgba(0,0,0,0.06); display:flex; align-items:center; gap:12px; }}
  .avatar{{ width:44px; height:44px; border-radius:999px; background:#eee; overflow:hidden; }} .avatar img{{ width:100%; height:100%; object-fit:cover; display:block; }}
  .name{{ font-weight:800; }} .logout{{ margin-left:auto; background:#fff; border:1px solid rgba(0,0,0,0.12); border-radius:999px; padding:8px 12px; cursor:pointer; font-weight:700; }}
  .drawer-body{{ padding:18px; overflow:auto; }}
  .backdrop{{ position:fixed; inset:0; background:rgba(0,0,0,0.28); opacity:0; pointer-events:none; transition:opacity .15s ease; z-index:1200; backdrop-filter:saturate(120%) blur(1.5px); }}
  .backdrop.show{{ opacity:1; pointer-events:auto; }}
  .toast{{ position:fixed; left:50%; bottom:24px; transform:translateX(-50%); background:#111827; color:#fff; padding:10px 14px; border-radius:10px; opacity:0; transition:opacity .2s ease; pointer-events:none; z-index:1300; }}
  .toast.show{{ opacity:0.95; }}

  /* ================= Animations ================= */
  .will-animate{{ opacity:0; }}
  @keyframes slideL {{ from{{opacity:0; transform:translateX(-24px)}} to{{opacity:1; transform:translateX(0)}} }}
  @keyframes slideR {{ from{{opacity:0; transform:translateX(24px)}} to{{opacity:1; transform:translateX(0)}} }}
  @keyframes slideDown {{ from{{opacity:0; transform:translateY(-12px)}} to{{opacity:1; transform:translateY(0)}} }}
  @keyframes fadeUp {{ from{{opacity:0; transform:translateY(12px)}} to{{opacity:1; transform:translateY(0)}} }}

  .animate .reveal-l{{ animation: slideL .6s var(--ease) .10s both; }}
  .animate .reveal-r{{ animation: slideR .6s var(--ease) .10s both; }}
  .animate .reveal-down{{ animation: slideDown .5s var(--ease) .30s both; }}
  .animate .reveal-up{{ animation: fadeUp .6s var(--ease) .30s both; }}

  @media (prefers-reduced-motion: reduce){{
    .will-animate{{ opacity:1 !important; }}
    .animate .reveal-l, .animate .reveal-r, .animate .reveal-down, .animate .reveal-up{{ animation:none !important; }}
  }}
</style>
</head>
<body>
  <div class='page'>
    <div class='navbar will-animate reveal-down'>
      <div class='brand'>My Restoration Service</div>
      <div style='font-size:.9rem;color:#6b7280;'>HTML-only prototype</div>
    </div>

    <div class='hero-wrap'>
      <div class='hero-card'>
        <div class='hero-inner'>
          <div class='hero-left will-animate reveal-l'>
            <h1 class='hero-title'>오래된 사진 복원 : <span>AI로 온라인 사진 복원</span></h1>
            <p class='hero-sub'>흑백은 왼쪽, 컬러는 오른쪽. 캔버스를 드래그해서 비교하세요.</p>
            <div class='cta-row will-animate reveal-up'>
              <a class='btn btn-kakao' id='btnLogin' href='{AUTH_URL}'>카카오 계정으로 계속</a>
              <a class='btn btn-ghost' href='#' id='btnGuest'>게스트 모드로 먼저 체험하기</a>
            </div>
          </div>
          <div class='hero-right will-animate reveal-r'>
            <div class='compare-wrap'>
              <div class='canvas' id='canvas'>
                <img src='{AFTER_URI}' alt='After' class='img-bottom'>
                <img src='{BEFORE_URI}' alt='Before' class='img-overlay' id='overlayImg'>
                <div class='divider' id='divider'></div>
                <div class='badge badge-left'>Before</div>
                <div class='badge badge-right'>After</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class='section' id='restore-app'>
      <h2>AI 복원 워크플로우</h2>
      <p class='muted'>UI 데모 / 실제 처리는 추후 연동</p>
      <div class='panel will-animate reveal-up'>
        <div class='row'>
          <label>사진 업로드</label>
          <input type='file' id='fileInput' accept='image/*'>
          <span class='muted' style='font-size:.9rem'>(상단 미리보기는 고정 샘플을 사용합니다)</span>
        </div>
        <div class='sep'></div>
        <div class='row'>
          <label>사진 유형</label>
          <label><input type='radio' name='ptype' value='흑백' checked> 흑백</label>
          <label><input type='radio' name='ptype' value='컬러'> 컬러</label>
        </div>
        <div class='row' style='margin-top:8px'>
          <label style='display:flex;align-items:center;gap:8px'>
            <input type='checkbox' id='chkAdvanced'>
            <span>고급 옵션 (동일 작업 반복 허용, 최대 3회)</span>
          </label>
        </div>
        <div class='sep'></div>
        <div class='row'>
          <button class='btn-op' id='btnUpscale'>해상도 업</button>
          <button class='btn-op' id='btnDenoise'>노이즈 제거</button>
          <button class='btn-op' id='btnStory'>스토리 생성</button>
        </div>
      </div>
    </div>

    <div class='backdrop' id='backdrop'></div>
    <button class='drawer-toggle' id='drawerToggle'>프로필</button>
    <aside class='drawer' id='drawer'>
      <div class='drawer-head'>
        <div class='avatar' id='avatarSlot'></div>
        <div class='name' id='nameSlot'>Kakao User</div>
        <button class='logout' id='btnLogout'>로그아웃</button>
      </div>
      <div class='drawer-body'>
        <p class='muted'>로그인 후 노출되는 사이드 슬라이드입니다. 상단에 프로필/이름/로그아웃.</p>
        <div style='height:600px'></div>
      </div>
    </aside>

    <div class='toast' id='toast'></div>
  </div>

  <script>
    // Start entrance animations
    window.addEventListener('load', () => {{
      document.documentElement.classList.remove('pre-animate');
      document.documentElement.classList.add('animate');
    }});

    const INITIAL_LOGGED_IN = {str(logged_in).lower()};
    const INITIAL_NAME = {repr(nickname)};
    const INITIAL_AVATAR = {repr(avatar)};

    const state = {{
      advanced:false, limits:{{maxBasic:1, maxAdv:3}}, counts:{{upscale:0, denoise:0, story:0}},
      loggedIn:INITIAL_LOGGED_IN, profile:{{ name: INITIAL_NAME || "카카오 사용자", avatar: INITIAL_AVATAR || "" }}
    }};

    const $ = sel => document.querySelector(sel);
    function toast(msg){{ const t=$("#toast"); t.textContent=msg; t.classList.add("show"); setTimeout(()=>t.classList.remove("show"),1200); }}
    function applySplit(percent){{ percent=Math.max(0,Math.min(100,percent)); $("#overlayImg").style.clipPath='inset(0 '+(100-percent)+'% 0 0)'; const rect=$("#canvas").getBoundingClientRect(); const x=rect.width*(percent/100); $("#divider").style.transform='translateX('+x+'px)'; }}
    function disableIfLimit(btn,key){{ const max=state.advanced?state.limits.maxAdv:state.limits.maxBasic; btn.disabled=state.counts[key]>=max; }}
    function refreshOps(){{ disableIfLimit($("#btnUpscale"),'upscale'); disableIfLimit($("#btnDenoise"),'denoise'); disableIfLimit($("#btnStory"),'story'); }}
    function openDrawer(){{ $("#drawer").classList.add('open'); $("#backdrop").classList.add('show'); }}
    function closeDrawer(){{ $("#drawer").classList.remove('open'); $("#backdrop").classList.remove('show'); }}
    function applyLoggedInUI(){{ $("#drawerToggle").style.display="flex"; $("#btnLogin").style.display="none"; $("#btnGuest").style.display="none"; const av=$("#avatarSlot"); av.innerHTML=""; if(state.profile.avatar){{ const img=document.createElement('img'); img.src=state.profile.avatar; img.alt='avatar'; av.appendChild(img); }} else {{ av.style.background="#e5e7eb"; }} $("#nameSlot").textContent=state.profile.name || "카카오 사용자"; }}
    if (state.loggedIn) {{ applyLoggedInUI(); }}

    // In-canvas drag with rAF
    const canvas=$("#canvas"); let dragging=false,scheduled=false,last=50;
    function schedule(p){{ last=p; if(scheduled) return; scheduled=true; requestAnimationFrame(()=>{{ applySplit(last); scheduled=false; }}); }}
    function posToPercent(evt){{ const rect=canvas.getBoundingClientRect(); const clientX=evt.clientX ?? (evt.touches && evt.touches[0].clientX) ?? 0; const x=clientX-rect.left; return (x/rect.width)*100; }}
    canvas.addEventListener('pointerdown',e=>{{ dragging=true; schedule(posToPercent(e)); }});
    canvas.addEventListener('pointermove',e=>{{ if(dragging) schedule(posToPercent(e)); }});
    window.addEventListener('pointerup',()=>dragging=false);
    canvas.addEventListener('pointerleave',()=>dragging=false);
    applySplit(50); refreshOps();

    $("#chkAdvanced").addEventListener('change',e=>{{ state.advanced=!!e.target.checked; refreshOps(); toast(state.advanced?"고급 옵션: 각 작업 최대 3회":"기본 모드: 각 작업 1회"); }});
    $("#btnUpscale").addEventListener('click',()=>{{ const max=state.advanced?state.limits.maxAdv:state.limits.maxBasic; if(state.counts.upscale>=max) return; state.counts.upscale++; document.querySelector('.img-bottom').style.filter="contrast(1.03) saturate(1.02)"; refreshOps(); }});
    $("#btnDenoise").addEventListener('click',()=>{{ const max=state.advanced?state.limits.maxAdv:state.limits.maxBasic; if(state.counts.denoise>=max) return; state.counts.denoise++; const img=document.querySelector('.img-bottom'); const cur=getComputedStyle(img).filter; img.style.filter="blur(0.3px) "+(cur&&cur!=="none"?cur:""); refreshOps(); }});
    $("#btnStory").addEventListener('click',()=>{{ const max=state.advanced?state.limits.maxAdv:state.limits.maxBasic; if(state.counts.story>=max) return; state.counts.story++; alert("스토리 생성은 데모입니다. 실제 모델은 추후 연동됩니다."); refreshOps(); }});
    $("#fileInput").addEventListener('change',()=>{{ toast("업로드 파일은 상단 미리보기를 변경하지 않습니다."); }});
    $("#btnGuest").addEventListener('click',(e)=>{{ e.preventDefault(); document.querySelector('#restore-app').scrollIntoView({{behavior:'smooth', block:'start'}}); }});

    $("#drawerToggle").addEventListener('click', openDrawer);
    $("#backdrop").addEventListener('click', closeDrawer);
    $("#btnLogout").addEventListener('click', ()=>{{ window.location.href = window.location.pathname + "?logout=1"; }});
    window.addEventListener('keydown', (e)=>{{ if(e.key==='Escape') closeDrawer(); }});
  </script>
</body>
</html>
"""

components.html(html_code, height=1100, scrolling=True)
