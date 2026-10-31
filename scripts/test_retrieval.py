from app.retrieval import search

# (customer-style query, the policy that should be found)
CASES = [
    ("my headphones arrived with a cracked case", "KB-02"),
    ("I ordered a blue jacket but got a red one", "KB-03"),
    ("tracking says delivered but nothing at my door", "KB-04"),
    ("how long does standard shipping take", "KB-05"),
    ("I want to cancel my order before it ships", "KB-06"),
    ("refunded two weeks ago and still no money in my account", "KB-07"),
    ("I was charged twice for the same order", "KB-10"),
    ("can I change my delivery address", "KB-12"),
    ("my laptop battery is swelling and getting hot", "KB-17"),
    ("I am going to sue you", "KB-16"),
    ("how many days do gold members have to return something", "KB-14"),
    ("can I return a gift card", "KB-15"),
    ("my coffee maker stopped working after 2 months", "KB-09"),
    ("my promo code did not apply", "KB-11"),
    ("I cannot log in to my account", "KB-13"),
]

n = len(CASES)
for mode in ("bm25", "embed", "hybrid"):
    hit1 = hit3 = 0
    misses = []
    for query, expected in CASES:
        ids = [r["id"] for r in search(query, k=3, mode=mode)]
        hit1 += ids[0] == expected
        hit3 += expected in ids
        if expected not in ids:
            misses.append((query, expected, ids))
    print(f"{mode:7s} hit@1={hit1}/{n}  hit@3={hit3}/{n}")
    for q, e, ids in misses:
        print(f"   MISS: {q!r} wanted {e}, got {ids}")