# app.py — Super Mario (Mini) with Arrow Keys + Animated Canvas (embedded via components)
# Keeps your template: remote budget loader, usage guardrails, provider switch (still available for AI policies if you want),
# but the gameplay is handled in a 60 FPS JS canvas so controls feel like a real game.

import os, time, datetime as dt, types, urllib.request
import streamlit as st

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

st.set_page_config(page_title="Super Mario (Mini)", layout="wide")

# ======================= Runtime budget & limits (same skeleton) =======================
BUDGET_URL = os.getenv("BUDGET_URL", "https://raw.githubusercontent.com/RahulBhattacharya1/shared_config/main/budget.py")
DEF = {
    "COOLDOWN_SECONDS": 30,
    "DAILY_LIMIT": 40,
    "HOURLY_SHARED_CAP": 250,
    "DAILY_BUDGET": 1.00,
    "EST_COST_PER_GEN": 1.00,
    "VERSION": "fallback-local",
}

def _fetch_budget(u: str) -> dict:
    mod = types.ModuleType("budget_remote")
    with urllib.request.urlopen(u, timeout=5) as r:
        code = r.read().decode("utf-8")
    exec(compile(code, "budget_remote", "exec"), mod.__dict__)
    return {k: getattr(mod, k, DEF[k]) for k in DEF}

def _load_cfg(ttl=300):
    now = time.time()
    cache = st.session_state.get("_budget_cache")
    ts = st.session_state.get("_budget_cache_ts", 0)
    if cache and (now - ts) < ttl:
        return cache
    try:
        cfg = _fetch_budget(BUDGET_URL)
    except Exception:
        cfg = DEF.copy()
    cfg["DAILY_BUDGET"] = float(os.getenv("DAILY_BUDGET", cfg["DAILY_BUDGET"]))
    cfg["EST_COST_PER_GEN"] = float(os.getenv("EST_COST_PER_GEN", cfg["EST_COST_PER_GEN"]))
    st.session_state["_budget_cache"] = cfg
    st.session_state["_budget_cache_ts"] = now
    return cfg

_cfg = _load_cfg()
COOLDOWN_SECONDS  = int(_cfg["COOLDOWN_SECONDS"])
DAILY_LIMIT       = int(_cfg["DAILY_LIMIT"])
HOURLY_SHARED_CAP = int(_cfg["HOURLY_SHARED_CAP"])
DAILY_BUDGET      = float(_cfg["DAILY_BUDGET"])
EST_COST_PER_GEN  = float(_cfg["EST_COST_PER_GEN"])
CONFIG_VERSION    = str(_cfg["VERSION"])

def _hour_bucket(now=None):
    now = now or dt.datetime.utcnow()
    return now.strftime("%Y-%m-%d-%H")

@st.cache_resource
def _shared_hourly_counters():
    return {}

def _init_rate_limits():
    ss = st.session_state
    today = dt.date.today().isoformat()
    if ss.get("rl_date") != today:
        ss["rl_date"] = today
        ss["rl_calls_today"] = 0
        ss["rl_last_ts"] = 0.0
    ss.setdefault("rl_last_ts", 0.0)
    ss.setdefault("rl_calls_today", 0)

def _can_call_now():
    _init_rate_limits()
    ss = st.session_state
    now = time.time()
    remaining = int(max(0, ss["rl_last_ts"] + COOLDOWN_SECONDS - now))
    if remaining > 0:
        return False, f"Wait {remaining}s.", remaining
    if ss["rl_calls_today"] * EST_COST_PER_GEN >= DAILY_BUDGET:
        return False, f"Budget reached (${DAILY_BUDGET:.2f}).", 0
    if ss["rl_calls_today"] >= DAILY_LIMIT:
        return False, f"Daily limit {DAILY_LIMIT}.", 0
    if HOURLY_SHARED_CAP > 0:
        bucket = _hour_bucket()
        cnt = _shared_hourly_counters()
        if cnt.get(bucket, 0) >= HOURLY_SHARED_CAP:
            return False, "Hourly cap reached.", 0
    return True, "", 0

def _record_success():
    ss = st.session_state
    ss["rl_last_ts"] = time.time()
    ss["rl_calls_today"] += 1
    if HOURLY_SHARED_CAP > 0:
        bucket = _hour_bucket()
        cnt = _shared_hourly_counters()
        cnt[bucket] = cnt.get(bucket, 0) + 1

# ======================= Sidebar (unchanged style) =======================
st.title("Super Mario (Mini)")

with st.sidebar:
    st.subheader("Generator")
    provider = st.selectbox("Provider", ["OpenAI", "Offline (rule-based)"])
    model    = st.selectbox("Model (OpenAI)", ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"])
    temp     = st.slider("Creativity (OpenAI)", 0.0, 1.0, 0.4, 0.05)
    max_tok  = st.slider("Max tokens (OpenAI)", 256, 2048, 500, 32)

    _init_rate_limits()
    ss = st.session_state
    st.markdown("**Usage limits**")
    st.write(f"<span style='font-size:.9rem'>Today: {ss['rl_calls_today']} / {DAILY_LIMIT}</span>", unsafe_allow_html=True)
    if HOURLY_SHARED_CAP > 0:
        used = _shared_hourly_counters().get(_hour_bucket(), 0)
        st.write(f"<span style='font-size:.9rem'>Hour: {used} / {HOURLY_SHARED_CAP}</span>", unsafe_allow_html=True)
    est = ss['rl_calls_today'] * EST_COST_PER_GEN
    st.markdown(
        f"<span style='font-size:.9rem'>Budget: ${est:.2f} / ${DAILY_BUDGET:.2f}</span><br/>"
        f"<span style='font-size:.8rem; opacity:.8'>Version: {CONFIG_VERSION}</span>",
        unsafe_allow_html=True
    )

# ======================= Canvas Game (arrow keys + animation) =======================
from streamlit.components.v1 import html as st_html

GAME_HTML = """
<div id="wrap">
  <canvas id="game" width="960" height="480"></canvas>
  <div id="help">← → to run • ↑ / Space to jump • R to reset</div>
</div>

<style>
  #wrap{display:flex;flex-direction:column;align-items:center;gap:8px;}
  #game{background:#0b1220;border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,.35)}
  #help{font:14px/1.2 system-ui, -apple-system, Segoe UI, Roboto, sans-serif; opacity:.8}
</style>

<script>
(function(){
  const c = document.getElementById('game');
  const ctx = c.getContext('2d');

  const W = c.width, H = c.height, GRAV = 0.9, FRICTION = 0.8;
  const groundY = H - 64;

  // Simple sprite frames (colored rectangles to simulate animation)
  const mario = {
    x: 120, y: groundY - 48, w: 34, h: 48,
    vx: 0, vy: 0, dir: 1, onGround: true,
    runFrame: 0, runTimer: 0
  };

  // Platforms + coins + flag
  const platforms = [
    {x:0, y:groundY, w:W, h:64, color:'#8B5A2B'},                // ground
    {x:280, y:groundY-120, w:120, h:18, color:'#8B5A2B'},
    {x:540, y:groundY-120, w:120, h:18, color:'#8B5A2B'}
  ];
  const coins = [
    {x:320, y:groundY-150, r:10, taken:false},
    {x:580, y:groundY-150, r:10, taken:false}
  ];
  const flag = {x: W-120, y: groundY-160, w:12, h:160, color:'#2dd4bf'};

  const keys = {};
  window.addEventListener('keydown', (e)=>{ keys[e.key.toLowerCase()] = true; });
  window.addEventListener('keyup',   (e)=>{ keys[e.key.toLowerCase()] = false; });

  function reset(){
    mario.x = 120; mario.y = groundY - 48;
    mario.vx = 0; mario.vy = 0; mario.dir = 1;
    mario.onGround = true; mario.runFrame = 0; mario.runTimer = 0;
    coins.forEach(c => c.taken = false);
  }

  function aabb(ax,ay,aw,ah,bx,by,bw,bh){
    return ax < bx+bw && ax+aw > bx && ay < by+bh && ay+ah > by;
  }

  function step(){
    // input
    const left  = keys['arrowleft'] || keys['a'];
    const right = keys['arrowright']|| keys['d'];
    const jump  = keys['arrowup'] || keys['w'] || keys[' '];

    if (keys['r']) reset();

    let accel = 0.6;
    if (left)  { mario.vx -= accel; mario.dir = -1; }
    if (right) { mario.vx += accel; mario.dir =  1; }

    // jump
    if (jump && mario.onGround){
      mario.vy = -16;
      mario.onGround = false;
    }

    // physics
    mario.vy += GRAV;
    mario.x  += mario.vx;
    mario.y  += mario.vy;
    mario.vx *= FRICTION;

    // collisions with platforms
    mario.onGround = false;
    for (const p of platforms){
      if (aabb(mario.x, mario.y, mario.w, mario.h, p.x, p.y, p.w, p.h)){
        // simple resolution: from top
        if (mario.vy > 0 && mario.y + mario.h - p.y < 24){
          mario.y = p.y - mario.h;
          mario.vy = 0;
          mario.onGround = true;
        }else if (mario.vy < 0 && p.y + p.h - mario.y < 24){
          mario.y = p.y + p.h;
          mario.vy = 0.5;
        }else if (mario.vx > 0){
          mario.x = p.x - mario.w - 0.01;
          mario.vx = 0;
        }else if (mario.vx < 0){
          mario.x = p.x + p.w + 0.01;
          mario.vx = 0;
        }
      }
    }

    // coins
    for (const c of coins){
      if (!c.taken){
        const dx = (mario.x+mario.w/2) - c.x;
        const dy = (mario.y+mario.h/2) - c.y;
        if (dx*dx + dy*dy < (c.r+16)*(c.r+16)) c.taken = true;
      }
    }

    // flag reached -> gentle confetti glow
    const atFlag = (mario.x + mario.w) > flag.x - 4;

    // run animation
    if (Math.abs(mario.vx) > 0.5 && mario.onGround){
      mario.runTimer += 1;
      if (mario.runTimer % 6 === 0) mario.runFrame = (mario.runFrame + 1) % 4;
    }else{
      mario.runFrame = 0; mario.runTimer = 0;
    }

    // draw
    ctx.clearRect(0,0,W,H);

    // background parallax
    ctx.fillStyle = '#0b1220'; ctx.fillRect(0,0,W,H);
    ctx.fillStyle = '#0e1730'; ctx.fillRect(0,0,W, H*0.65);

    // platforms
    for (const p of platforms){
      ctx.fillStyle = p.color;
      ctx.fillRect(p.x, p.y, p.w, p.h);
    }

    // flag
    ctx.fillStyle = flag.color;
    ctx.fillRect(flag.x, flag.y, flag.w, flag.h);
    // small banner
    ctx.fillStyle = '#34d399';
    ctx.fillRect(flag.x+flag.w, flag.y, 24, 14);

    // coins
    for (const c of coins){
      if (c.taken) continue;
      const g = ctx.createRadialGradient(c.x, c.y, 2, c.x, c.y, c.r);
      g.addColorStop(0, '#fff0a3'); g.addColorStop(1, '#f2c94c');
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(c.x, c.y, c.r, 0, Math.PI*2); ctx.fill();
      ctx.strokeStyle = '#996515'; ctx.lineWidth = 2; ctx.stroke();
    }

    // mario sprite (simple animated rectangles + "face")
    // body
    const bodyColor = '#60a5fa';
    const faceColor = '#fde68a';
    const x = mario.x, y = mario.y, w = mario.w, h = mario.h;

    // legs animation (alternate rectangles)
    ctx.fillStyle = bodyColor;
    ctx.fillRect(x, y+h-14, w, 14); // base
    if (mario.onGround){
      if (mario.runFrame % 2 === 0){
        ctx.fillRect(x, y+h-14, 10, 14);
      }else{
        ctx.fillRect(x+w-10, y+h-14, 10, 14);
      }
    }

    // torso
    ctx.fillRect(x, y+12, w, h-26);

    // head
    ctx.fillStyle = faceColor;
    ctx.fillRect(x+6, y, 22, 18);

    // face details (eyes + direction)
    ctx.fillStyle = '#1f2937';
    const eyeDX = mario.dir === 1 ? 3 : -3;
    ctx.fillRect(x+12+eyeDX, y+6, 3, 3);
    ctx.fillRect(x+18+eyeDX, y+6, 3, 3);

    // jump squash & stretch hint
    if (!mario.onGround){
      ctx.globalAlpha = 0.25;
      ctx.fillStyle = '#60a5fa';
      ctx.fillRect(x, y+h, w, 6);
      ctx.globalAlpha = 1.0;
    }

    // victory glow
    if (atFlag){
      ctx.save();
      ctx.globalAlpha = 0.15;
      ctx.fillStyle = '#22d3ee';
      ctx.fillRect(flag.x-20, flag.y-20, 80, flag.h+40);
      ctx.restore();
    }

    requestAnimationFrame(step);
  }

  // start
  reset();
  requestAnimationFrame(step);
})();
</script>
"""

st_html(GAME_HTML, height=560, scrolling=False)
