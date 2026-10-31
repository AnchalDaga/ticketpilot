import sys
import time

from app.llm import chat

provider = sys.argv[1] if len(sys.argv) > 1 else None
messages = [{"role": "user", "content": "Reply with exactly one word: pong"}]

for attempt in (1, 2):
    start = time.time()
    r = chat(messages, provider=provider)
    print(
        f"call {attempt}: {r['content']!r} | {r['provider']} / {r['model']} | "
        f"cached={r['cached']} | tokens in/out={r['prompt_tokens']}/{r['completion_tokens']} | "
        f"{time.time() - start:.2f}s"
    )