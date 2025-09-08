# app.py — Super Mario (mini grid) — same template and guardrails:contentReference[oaicite:4]{index=4}
import os, time, json, random, datetime as dt, types, urllib.request
import streamlit as st
try:
    from openai import OpenAI
except Exception:
    OpenAI=None

st.set_page_config(page_title="Super Mario (Mini)", layout="wide")

BUDGET_URL=os.getenv("BUDGET_URL","https://raw.githubusercontent.com/RahulBhattacharya1/shared_config/main/budget.py")
DEF={"COOLDOWN_SECONDS":30,"DAILY_LIMIT":40,"HOURLY_SHARED_CAP":250,"DAILY_BUDGET":1.00,"EST_COST_PER_GEN":1.00,"VERSION":"fallback-local"}
def _fetch(u): m=types.ModuleType("b"); 
with urllib.request.urlopen(u,timeout=5) as r: code=r.read().decode()
exec(compile(code,"b","exec"),m.__dict__); 
return {k:getattr(m,k,DEF[k]) for k in DEF}
def _cfg(ttl=300):
    now=time.time(); c=st.session_state.get("_b"); ts=st.session_state.get("_bts",0)
    if c and (now-ts)<ttl: return c
    try: cfg=_fetch(BUDGET_URL)
    except Exception: cfg=DEF.copy()
    cfg["DAILY_BUDGET"]=float(os.getenv("DAILY_BUDGET",cfg["DAILY_BUDGET"]))
    cfg["EST_COST_PER_GEN"]=float(os.getenv("EST_COST_PER_GEN",cfg["EST_COST_PER_GEN"]))
    st.session_state["_b"]=cfg; st.session_state["_bts"]=now; return cfg
_cfg=_cfg(); COOLDOWN_SECONDS=int(_cfg["COOLDOWN_SECONDS"]); DAILY_LIMIT=int(_cfg["DAILY_LIMIT"])
HOURLY_SHARED_CAP=int(_cfg["HOURLY_SHARED_CAP"]); DAILY_BUDGET=float(_cfg["DAILY_BUDGET"])
EST_COST_PER_GEN=float(_cfg["EST_COST_PER_GEN"]); CONFIG_VERSION=str(_cfg["VERSION"])
def _hour(): return dt.datetime.utcnow().strftime("%Y-%m-%d-%H")
@st.cache_resource
def _counters(): return {}
def _init():
    ss=st.session_state; today=dt.date.today().isoformat()
    if ss.get("rl_date")!=today: ss["rl_date"]=today; ss["rl_calls_today"]=0; ss["rl_last_ts"]=0.0
    ss.setdefault("rl_last_ts",0.0); ss.setdefault("rl_calls_today",0)
def _can():
    _init(); ss=st.session_state; now=time.time()
    rem=int(max(0, ss["rl_last_ts"]+COOLDOWN_SECONDS-now))
    if rem>0: return False,f"Wait {rem}s.",rem
    if ss["rl_calls_today"]*EST_COST_PER_GEN>=DAILY_BUDGET: return False,f"Budget reached (${DAILY_BUDGET:.2f}).",0
    if ss["rl_calls_today"]>=DAILY_LIMIT: return False,f"Daily limit {DAILY_LIMIT}.",0
    if HOURLY_SHARED_CAP>0:
        b=_hour(); c=_counters()
        if c.get(b,0)>=HOURLY_SHARED_CAP: return False,"Hourly cap reached.",0
    return True,"",0
def _rec():
    ss=st.session_state; ss["rl_last_ts"]=time.time(); ss["rl_calls_today"]+=1
    if HOURLY_SHARED_CAP>0:
        b=_hour(); c=_counters(); c[b]=c.get(b,0)+1

W,H=12,6
def new_level():
    grid=[[" "]*W for _ in range(H)]
    # ground
    for x in range(W): grid[H-1][x]="_"
    # platforms
    for x in range(2,10,3): grid[H-3][x]="_"
    # coins
    coins={(H-2,5),(H-3,2),(H-3,8)}
    return grid, (H-2,1), coins, (H-2,W-2)  # mario, coins, flag

def render(grid, mario, coins, flag, brand):
    s=[]
    for r in range(H):
        row=[]
        for c in range(W):
            ch=grid[r][c]
            if (r,c)==mario: ch="M"
            elif (r,c)==flag: ch="F"
            elif (r,c) in coins: ch="o"
            row.append(ch)
        s.append("".join(row))
    st.markdown(f"<pre style='font-size:14px;color:{brand}'>{chr(10).join(s)}</pre>", unsafe_allow_html=True)

def solid(grid, r, c):
    return not (0<=r<H and 0<=c<W) or grid[r][c]=="_"

def step_physics(grid, mario, vy):
    r,c=mario
    # gravity
    vy += 1
    nr = r + (1 if vy>0 else -1)
    # vertical collision simple
    if solid(grid, nr, c):
        vy = 0
    else:
        r = nr
    return (r,c), vy

def move_lr(grid, mario, dx):
    r,c=mario
    nc=c+dx
    if not solid(grid, r, nc): c=nc
    return (r,c)

def offline_policy(mario, flag):
    mr,mc=mario; fr,fc=flag
    if fc>mc: return "right"
    if fc<mc: return "left"
    return "jump" if random.random()<0.2 else "stay"

def call_openai(model, state, temp, max_tok)->str:
    key=st.secrets.get("OPENAI_API_KEY","")
    if not key: raise RuntimeError("OPENAI_API_KEY missing")
    if OpenAI is None: raise RuntimeError("openai package not available")
    client=OpenAI(api_key=key)
    sys="You are a Mario controller. Return JSON only: {\"move\":\"left|right|jump|stay\"}."
    usr=json.dumps(state)
    r=client.chat.completions.create(model=model,temperature=float(temp),max_tokens=int(max_tok),
        messages=[{"role":"system","content":sys},{"role":"user","content":usr}])
    t=r.choices[0].message.content.strip()
    if t.startswith("```"): t=t.strip("`").split("\n",1)[-1].strip()
    mv=str(json.loads(t).get("move","stay")).lower()
    return mv if mv in {"left","right","jump","stay"} else "stay"

def card(t,sub=""):
    st.markdown(f"<div style='border:1px solid #e5e7eb;padding:.6rem .9rem;border-radius:10px;margin:.6rem 0'><b>{t}</b><div>{sub}</div></div>", unsafe_allow_html=True)

st.title("Super Mario (Mini)")
with st.sidebar:
    st.subheader("Generator")
    provider=st.selectbox("Provider",["OpenAI","Offline (rule-based)"])
    model=st.selectbox("Model (OpenAI)",["gpt-4o-mini","gpt-4o","gpt-4.1-mini"])
    brand="#0F62FE"
    temp=st.slider("Creativity (OpenAI)",0.0,1.0,0.4,0.05)
    max_tok=st.slider("Max tokens (OpenAI)",256,2048,500,32)
    _init(); ss=st.session_state
    st.markdown("**Usage limits**")
    st.write(f"<span style='font-size:.9rem'>Today: {ss['rl_calls_today']} / {DAILY_LIMIT}</span>", unsafe_allow_html=True)
    if HOURLY_SHARED_CAP>0:
        used=_counters().get(_hour(),0)
        st.write(f"<span style='font-size:.9rem'>Hour: {used} / {HOURLY_SHARED_CAP}</span>", unsafe_allow_html=True)
    est=ss['rl_calls_today']*EST_COST_PER_GEN
    st.markdown(f"<span style='font-size:.9rem'>Budget: ${est:.2f} / ${DAILY_BUDGET:.2f}</span><br/>"
                f"<span style='font-size:.8rem;opacity:.8'>Version: {CONFIG_VERSION}</span>", unsafe_allow_html=True)

if "mario" not in st.session_state:
    g,m,coins,flag=new_level()
    st.session_state.mario={"grid":g,"mario":m,"vy":0,"coins":coins,"flag":flag,"score":0}
S=st.session_state.mario
render(S["grid"], S["mario"], S["coins"], S["flag"], brand)

c1,c2,c3,c4=st.columns(4)
mv=None
with c1:
    if st.button("Left"): mv="left"
with c2:
    if st.button("Right"): mv="right"
with c3:
    if st.button("Jump"): mv="jump"
with c4:
    if st.button("Reset"): g,m,coins,flag=new_level(); S.update({"grid":g,"mario":m,"vy":0,"coins":coins,"flag":flag,"score":0})

if mv is None:
    ok,msg,_=_can()
    try:
        if provider=="OpenAI" and ok:
            state={"mario":S["mario"],"vy":S["vy"],"coins":list(map(list,S["coins"])),"flag":S["flag"]}
            mv=call_openai(model,state,temp,max_tok); _rec()
        else:
            if provider=="OpenAI" and not ok: st.warning(msg)
            mv=offline_policy(S["mario"], S["flag"])
    except Exception as e:
        st.error(f"AI policy error: {e}. Using offline.")
        mv=offline_policy(S["mario"], S["flag"])

# apply input
if mv=="left":  S["mario"]=move_lr(S["grid"], S["mario"], -1)
elif mv=="right": S["mario"]=move_lr(S["grid"], S["mario"], 1)
elif mv=="jump" and S["vy"]==0: S["vy"]=-2

# physics tick
S["mario"], S["vy"] = step_physics(S["grid"], S["mario"], S["vy"])

# coin pickup
if S["mario"] in S["coins"]:
    S["coins"].remove(S["mario"]); S["score"]+=1

render(S["grid"], S["mario"], S["coins"], S["flag"], brand)
msg = "Flag reached!" if S["mario"]==S["flag"] else f"Coins: {S['score']}"
card("Status", msg)
