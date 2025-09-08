# Super Mario — Mini

A tiny platformer-style grid: ground/platforms, gravity, jump, coins, and a flag.  
Optional OpenAI controller returns `{"move":"left|right|jump|stay"}`.  
Template mirrors the Streamlit AI Trip Planner (remote `budget.py`, guardrails, sidebar):contentReference[oaicite:4]{index=4}.

## Features
- Gravity + simple vertical collision
- Left/right movement and jump
- Coins to collect and a flag to reach
- Offline policy heads toward the flag; OpenAI mode for JSON moves
- Budget/version panel and rate-limit guardrails

## Quickstart
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# optional:
mkdir -p .streamlit && printf 'OPENAI_API_KEY = "sk-..."\n' > .streamlit/secrets.toml
streamlit run app.py
