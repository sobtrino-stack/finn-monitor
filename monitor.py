#!/usr/bin/env python3
"""
Finn.no monitor — Gis bort Møbler og Interiør (local area)
Runs on GitHub Actions every 10 minutes.
Sends Telegram message when new listings appear.
"""

import os
import re
import json
import time
import urllib.request
import urllib.parse
import urllib.error

FINN_URL = (
    "https://www.finn.no/recommerce/forsale/search"
    "?category=0.78&location=1.20015.20282&sort=PUBLISHED_DESC&trade_type=2"
)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT  = os.environ["TELEGRAM_CHAT_ID"]
SEEN_FILE      = "seen_ids.json"

# ── Junk filter ──────────────────────────────────────────────────────────────
JUNK_PATTERNS = [
    r"glass", r"tallerkn", r"\bfat\b", r"kopp", r"krus", r"bestikk",
    r"bilderamme", r"bildelist", r"\bramme\b",
    r"bordl.per", r"bordsk.ner", r"serviett",
    r"pynt", r"dekorasjon", r"\bdekor\b",
    r"\bvase\b", r"blomsterpotte",
    r"stearinlys", r"\blys\b", r"telys",
    r"\bkurv\b", r"\bboks\b", r"krukke",
]

def is_junk(title: str) -> bool:
    t = title.lower()
    return any(re.search(p, t) for p in JUNK_PATTERNS)

# ── Fetch listings ───────────────────────────────────────────────────────────
def get_listings():
    req = urllib.request.Request(
        FINN_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "no-NO,no;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }
    )
    import gzip
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                if r.info().get("Content-Encoding") == "gzip":
                    html = gzip.decompress(raw).decode("utf-8", errors="replace")
                else:
                    html = raw.decode("utf-8", errors="replace")
            break
        except urllib.error.HTTPError as e:
            print(f"  Attempt {attempt+1} failed: HTTP {e.code}")
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
            else:
                raise

    urls   = re.findall(r'"url":"(https://www\.finn\.no/recommerce/forsale/item/(\d+))"', html)
    if not urls:
        print(f"  WARNING: no listings found. HTML length={len(html)}, encoding={r.info().get('Content-Encoding')}")
    titles = re.findall(r'"name":"([^"]+)","image":"https://images\.finncdn', html)

    listings = []
    for i, (url, fid) in enumerate(urls):
        title = titles[i] if i < len(titles) else "Ukjent tittel"
        listings.append({"id": fid, "title": title, "url": url})
    return listings

# ── Telegram ─────────────────────────────────────────────────────────────────
def send_telegram(text: str):
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT,
        "text": text,
        "parse_mode": "HTML"
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    # Load seen IDs from file (persisted via GitHub Actions cache)
    seen = {}
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            seen = json.load(f)

    listings = get_listings()
    print(f"Fetched {len(listings)} listings from Finn.no")

    new_count = 0
    for item in listings:
        fid = item["id"]
        if fid in seen:
            continue
        seen[fid] = True  # mark seen regardless — avoids re-notifying junk

        if is_junk(item["title"]):
            print(f"  [junk] {item['title']}")
            continue

        msg = f"🛋 Ny gratis annonse på Finn.no!\n\n<b>{item['title']}</b>\n\n{item['url']}"
        send_telegram(msg)
        print(f"  [notified] {item['title']}")
        new_count += 1

    print(f"Notified: {new_count} new items")

    # Keep only last 1000 IDs to prevent file growing forever
    if len(seen) > 1000:
        keys = list(seen.keys())[-1000:]
        seen = {k: True for k in keys}

    with open(SEEN_FILE, "w") as f:
        json.dump(seen, f)

if __name__ == "__main__":
    main()
