import hashlib
import json
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

CACHE_PATH = ROOT / "data" / "llm_cache.db"

# Both providers accept the same request format, so one client class serves both.
# Model names change often: override them in .env with GROQ_MODEL / GEMINI_MODEL.
PROVIDERS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_env": "GEMINI_API_KEY",
        "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    },
}


def _cache_conn() -> sqlite3.Connection:
    CACHE_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(CACHE_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    return conn


def _cache_key(provider: str, model: str, messages: list, temperature: float) -> str:
    raw = json.dumps([provider, model, messages, temperature], sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def chat(messages, provider=None, model=None, temperature=0.0, use_cache=True) -> dict:
    provider = provider or os.getenv("LLM_PROVIDER", "groq")
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider '{provider}'. Use one of: {list(PROVIDERS)}")
    cfg = PROVIDERS[provider]
    model = model or cfg["model"]

    key = _cache_key(provider, model, messages, temperature)
    conn = _cache_conn()
    if use_cache:
        row = conn.execute("SELECT value FROM cache WHERE key = ?", (key,)).fetchone()
        if row:
            conn.close()
            result = json.loads(row[0])
            result["cached"] = True
            return result

    api_key = os.getenv(cfg["key_env"])
    if not api_key:
        conn.close()
        raise RuntimeError(f"{cfg['key_env']} is missing from your .env file")

    client = OpenAI(api_key=api_key, base_url=cfg["base_url"])
    resp = client.chat.completions.create(model=model, messages=messages, temperature=temperature)
    usage = resp.usage
    result = {
        "content": resp.choices[0].message.content or "",
        "provider": provider,
        "model": model,
        "prompt_tokens": usage.prompt_tokens if usage else 0,
        "completion_tokens": usage.completion_tokens if usage else 0,
        "cached": False,
    }
    if use_cache:
        conn.execute("INSERT OR REPLACE INTO cache (key, value) VALUES (?, ?)", (key, json.dumps(result)))
        conn.commit()
    conn.close()
    return result