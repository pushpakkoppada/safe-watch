"""Rule-based unsafe-content classifier (swap for an ML/API model later)."""
from urllib.parse import urlparse

# category -> (blocked domains, URL keywords, severity)
RULES = {
    "adult":     ({"pornhub.com", "xvideos.com", "xnxx.com"}, ["porn", "xxx", "nsfw"], "high"),
    "gambling":  ({"bet365.com", "stake.com", "draftkings.com"}, ["casino", "betting", "poker"], "medium"),
    "violence":  ({"bestgore.com", "liveleak.com"}, ["gore", "beheading"], "high"),
    "self_harm": (set(), ["self-harm", "suicide-methods"], "high"),
    "drugs":     (set(), ["buy-weed", "buy-pills", "darknet-market"], "medium"),
}

def classify(url: str):
    """Return (category, severity) or None if the URL looks safe."""
    if not url:
        return None
    u = url.lower()
    host = (urlparse(u if "//" in u else "//" + u).hostname or "").removeprefix("www.")
    for cat, (domains, words, sev) in RULES.items():
        if host in domains or any(host.endswith("." + d) for d in domains):
            return cat, sev
        if any(w in u for w in words):
            return cat, sev
    return None
