# app.py — Super Mario (Mini) — colored tiles renderer (no emojis), same template & guardrails

import os
import time
import json
import random
import datetime as dt
import types
import urllib.request

import streamlit as st

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

# ======================= App Config =======================
st.set_page_config(page_title="Super Mario (Mini)", layout="wide")

# ======================= Runtime budget & limits (matches your template) =======================
BUDGET_URL = os.getenv(
    "BUDGET_URL",
    "https://raw.githubusercontent.com/RahulBhattacharya1/shared_config/main/budget.py",
)

DEF = {
    "COOLDOWN_SECONDS": 30,
    "DAILY_LIMIT": 40,
    "HOURLY_SHARED_CAP": 250,
    "DAILY_BUDGET": 1.00,
    "EST_COST_PER_GEN": 1.00,
    "VERSION": "fallback-local",
}

def _fetch(u: str) -> dict:
    """Fetch remote budget.py and extract expected keys with fallbacks."""
    mod = types.ModuleType("budget_remote")
    with urllib.request.urlopen(u, timeout=5) as r:
        code = r.read().decode()
    exec(compile(code, "budget_remote", "exec"), mod.__dict__)
    return {k: getattr(mod, k, DEF[k]) for k in DEF}

def _load_cfg(ttl: int = 300) -> dict:
    now = time.time()
    cache = st.session_state.get("_budget_cache")
    ts = st.session_state.get("_budget_cache_ts", 0)
    if cache and (now - ts) < ttl:
        return cache
    try:
        cfg = _fetch(BUDGET_URL)
    except Exception:
        cfg = DEF.copy()
    # Env overrides for per-deploy tuning
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

# ======================= Mini “platformer” world =======================
W, H = 12, 6  # width, height

# Tile keys
AIR = " "
GROUND = "_"
COIN = "o"
FLAG = "F"

# Colored tile renderer (no emojis)
TILE_PX = 28  # size of each square
PALETTE = {
    AIR:   "#0b1220",  # dark background (sky)
    GROUND:"#8B5A2B",  # brown
    COIN:  "#f2c94c",  # gold
    FLAG:  "#2dd4bf",  # teal flag tile
    "M":   "#60a5fa",  # player
}

def new_level():
    grid = [[AIR]*W for _ in range(H)]
    # ground
    for x in range(W):
        grid[H-1][x] = GROUND
    # simple platforms
    for x in range(2, 10, 3):
        grid[H-3][x] = GROUND
    # coins and flag
    coins = {(H-2, 5), (H-3, 2), (H-3, 8)}
    mario_start = (H-2, 1)
    flag = (H-2, W-2)
    return grid, mario_start, coins, flag

def render(grid, mario, coins, flag):
    # Build a tiny CSS grid using inline HTML for crisp colored squares.
    rows_html = []
    for r in range(H):
        cells = []
        for c in range(W):
            key = grid[r][c]
            # overlay order: Mario > Flag > Coin > Ground/Air
            if (r, c) == mario:
                color = PALETTE["M"]
            elif (r, c) == flag:
                color = PALETTE[FLAG]
            elif (r, c) in coins:
                color = PALETTE[COIN]
            else:
                color = PALETTE[key]
            cells.append(
                f"<span class='cell' style='background:{color}'></span>"
            )
        rows_html.append("<div class='row'>" + "".join(cells) + "</div>")

    html = f"""
<div class="board">
  {''.join(rows_html)}
</div>
<style>
.board {{
  display: inline-flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px;
  background: #0a0f1a;
  border-radius: 12px;
  box-shadow: 0 6px 24px rgba(0,0,0,.35);
}}
.board .row {{
  display: inline-flex;
  gap: 4px;
}}
.board .cell {{
  display: inline-block;
  width: {TILE_PX}px;
  height: {TILE_PX}px;
  border-radius: 6px;
}}
/* Light outline to separate ground from sky slightly */
.board .cell[style*="{PALETTE[GROUND]}"] {{
  box-shadow: inset 0 0 0 1px rgba(0,0,0,.25);
}}
</style>
"""
    st.markdown(html, unsafe_allow_html=True)

def solid(grid, r, c):
    return not (0 <= r < H and 0 <= c < W) or grid[r][c] == GROUND

def step_physics(grid, mario, vy):
    r, c = mario
    # gravity
    vy += 1
    target_r = r + (1 if vy > 0 else -1)
    if solid(grid, target_r, c):
        vy = 0
    else:
        r = target_r
    return (r, c), vy

def move_lr(grid, mario, dx):
    r, c = mario
    nc = c + dx
    if not solid(grid, r, nc):
        c = nc
    return (r, c)

def offline_policy(mario, flag):
    # Simple greedy policy: move toward flag; occasionally jump
    mr, mc = mario
    fr, fc = flag
    if fc > mc:
        return "right"
    if fc < mc:
        return "left"
    return "jump" if random.random() < 0.2 else "stay"

def call_openai(model, state, temp, max_tok) -> str:
    key = st.secrets.get("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OPENAI_API_KEY missing")
    if OpenAI is None:
        raise RuntimeError("openai package not available")
    client = OpenAI(api_key=key)
    sys = 'You are a Mario controller. Return JSON only: {"move":"left|right|jump|stay"}.'
    usr = json.dumps(state)
    resp = client.chat.completions.create(
        model=model,
        temperature=float(temp),
        max_tokens=int(max_tok),
        messages=[{"role":"system","content":sys},{"role":"user","content":usr}]
    )
    text = resp.choices[0].message.content.strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1].strip()
    mv = str(json.loads(text).get("move", "stay")).lower()
    return mv if mv in {"left","right","jump","stay"} else "stay"

def card(title, subtitle=""):
    st.markdown(
        f"<div style='border:1px solid #e5e7eb; padding:.6rem .9rem; border-radius:10px; margin:.6rem 0'>"
        f"<b>{title}</b><div>{subtitle}</div></div>",
        unsafe_allow_html=True
    )

# ======================= UI =======================
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

# ======================= State =======================
if "mario" not in st.session_state:
    g, m, coins, flag = new_level()
    st.session_state.mario = {"grid": g, "mario": m, "vy": 0, "coins": coins, "flag": flag, "score": 0}

S = st.session_state.mario

# Render current board
render(S["grid"], S["mario"], S["coins"], S["flag"])

# Controls
c1, c2, c3, c4 = st.columns(4)
mv = None
with c1:
    if st.button("Left"):
        mv = "left"
with c2:
    if st.button("Right"):
        mv = "right"
with c3:
    if st.button("Jump"):
        mv = "jump"
with c4:
    if st.button("Reset"):
        g, m, coins, flag = new_level()
        S.update({"grid": g, "mario": m, "vy": 0, "coins": coins, "flag": flag, "score": 0})

# If no manual button, let the AI policy act
if mv is None:
    allowed, msg, _ = _can_call_now()
    try:
        if provider == "OpenAI" and allowed:
            state = {"mario": S["mario"], "vy": S["vy"], "coins": list(map(list, S["coins"])), "flag": S["flag"]}
            mv = call_openai(model, state, temp, max_tok)
            _record_success()
        else:
            if provider == "OpenAI" and not allowed:
                st.warning(msg)
            mv = offline_policy(S["mario"], S["flag"])
    except Exception as e:
        st.error(f"AI policy error: {e}. Using offline.")
        mv = offline_policy(S["mario"], S["flag"])

# Apply movement inputs
if mv == "left":
    S["mario"] = move_lr(S["grid"], S["mario"], -1)
elif mv == "right":
    S["mario"] = move_lr(S["grid"], S["mario"], 1)
elif mv == "jump" and S["vy"] == 0:
    S["vy"] = -2

# Physics tick
S["mario"], S["vy"] = step_physics(S["grid"], S["mario"], S["vy"])

# Coin pickup
if S["mario"] in S["coins"]:
    S["coins"].remove(S["mario"])
    S["score"] += 1

# Re-render updated world
render(S["grid"], S["mario"], S["coins"], S["flag"])
card("Status", f"Coins: {S['score']}" if S["mario"] != S["flag"] else "Flag reached!")
