"""
CyberSec News Bot
=================
Fetches the latest cybersecurity news from multiple RSS feeds and
posts them to Discord, Telegram, and WhatsApp (via Green API).

Run manually:
    python cybersec_bot.py

Or let GitHub Actions run it on a schedule (see .github/workflows/news_bot.yml).
"""

import hashlib
import json
import os
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import requests

# ── Configuration ─────────────────────────────────────────────────────────────

RSS_FEEDS = [
    {"name": "The Hacker News",   "url": "https://feeds.feedburner.com/TheHackersNews"},
    {"name": "BleepingComputer",  "url": "https://www.bleepingcomputer.com/feed/"},
    {"name": "Krebs on Security", "url": "https://krebsonsecurity.com/feed/"},
    {"name": "SANS Internet SC",  "url": "https://isc.sans.edu/rssfeed_full.xml"},
    {"name": "SecurityWeek",      "url": "https://feeds.feedburner.com/Securityweek"},
    {"name": "Dark Reading",      "url": "https://www.darkreading.com/rss.xml"},
    {"name": "Threatpost",        "url": "https://threatpost.com/feed/"},
    {"name": "Exploit-DB",        "url": "https://www.exploit-db.com/rss.xml"},
]

# How many new articles to post per run (keeps channels clean)
MAX_POSTS_PER_RUN = int(os.getenv("MAX_POSTS_PER_RUN", "3"))

# How many entries to look at from each feed per run
ENTRIES_PER_FEED = int(os.getenv("ENTRIES_PER_FEED", "5"))

# File to track already-posted articles (committed back to repo)
SEEN_FILE = Path("seen_articles.json")

# Maximum number of article IDs to keep in seen list (prevents file bloat)
MAX_SEEN = 1000


# ── Deduplication ─────────────────────────────────────────────────────────────

def article_id(entry: dict) -> str:
    """Stable ID: MD5 of (link + title). Survives minor title edits."""
    raw = (entry.get("link", "") + entry.get("title", "")).encode()
    return hashlib.md5(raw).hexdigest()


def load_seen() -> set:
    """Load set of already-posted article IDs from disk."""
    if SEEN_FILE.exists():
        try:
            data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
            return set(data.get("seen", []))
        except (json.JSONDecodeError, KeyError):
            return set()
    return set()


def save_seen(seen: set) -> None:
    """Persist seen IDs. Trims to MAX_SEEN most recent to avoid file bloat."""
    ids = sorted(seen)[-MAX_SEEN:]
    SEEN_FILE.write_text(
        json.dumps({"seen": ids, "updated": _utc_now()}, indent=2),
        encoding="utf-8",
    )


# ── News Fetching ─────────────────────────────────────────────────────────────

def fetch_all_articles() -> list[dict]:
    """Pull latest articles from all configured RSS feeds."""
    articles: list[dict] = []

    for feed_meta in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_meta["url"])
            for entry in feed.entries[:ENTRIES_PER_FEED]:
                # Strip HTML tags from summary crudely but effectively
                raw_summary = entry.get("summary", entry.get("description", ""))
                clean_summary = _strip_html(raw_summary)[:400].strip()

                articles.append(
                    {
                        "id":        article_id(entry),
                        "title":     entry.get("title", "No Title").strip(),
                        "link":      entry.get("link", ""),
                        "summary":   clean_summary,
                        "source":    feed_meta["name"],
                        "published": entry.get("published", ""),
                    }
                )
        except Exception as exc:
            _warn(f"Failed to fetch {feed_meta['name']}: {exc}")

    return articles


# ── Message Formatting ────────────────────────────────────────────────────────

def _discord_embed(article: dict) -> dict:
    """Rich embed for Discord."""
    summary = article["summary"]
    if len(summary) > 350:
        summary = summary[:347] + "…"

    return {
        "username":   "🔐 CyberSec Intel",
        "embeds": [
            {
                "title":       article["title"][:256],
                "url":         article["link"],
                "description": summary or "*No summary available.*",
                "color":       0x00FF41,  # classic terminal green
                "footer": {
                    "text": f"📡 {article['source']}  •  {_utc_now()}"
                },
            }
        ],
    }


def _telegram_html(article: dict) -> str:
    """HTML-formatted Telegram message (Telegram supports a subset of HTML)."""
    title   = _escape_html(article["title"])
    source  = _escape_html(article["source"])
    summary = _escape_html(article["summary"][:300])
    if len(article["summary"]) > 300:
        summary += "…"
    link = article["link"]

    return (
        f"🔐 <b>CyberSec Intel</b>\n\n"
        f"<b>{title}</b>\n\n"
        f"{summary}\n\n"
        f"📡 <i>{source}</i>\n"
        f"🔗 <a href='{link}'>Read full article →</a>"
    )


def _whatsapp_text(article: dict) -> str:
    """Plain-text WhatsApp message (supports *bold* and _italic_)."""
    summary = article["summary"][:300]
    if len(article["summary"]) > 300:
        summary += "…"

    return (
        f"🔐 *CyberSec Intel*\n\n"
        f"*{article['title']}*\n\n"
        f"{summary}\n\n"
        f"📡 _{article['source']}_\n"
        f"🔗 {article['link']}"
    )


# ── Platform Posters ──────────────────────────────────────────────────────────

def post_discord(article: dict) -> bool:
    """Post to Discord via Incoming Webhook."""
    url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        _info("Discord skipped — DISCORD_WEBHOOK_URL not set")
        return False

    try:
        resp = requests.post(url, json=_discord_embed(article), timeout=15)
        resp.raise_for_status()
        _ok(f"Discord ✓  {article['title'][:70]}")
        return True
    except requests.RequestException as exc:
        _warn(f"Discord ✗  {exc}")
        return False


def post_telegram(article: dict) -> bool:
    """Post to a Telegram group/channel via Bot API."""
    token   = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        _info("Telegram skipped — TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return False

    try:
        url  = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {
            "chat_id":                  chat_id,
            "text":                     _telegram_html(article),
            "parse_mode":               "HTML",
            "disable_web_page_preview": False,
        }
        resp = requests.post(url, json=data, timeout=15)
        resp.raise_for_status()
        _ok(f"Telegram ✓  {article['title'][:70]}")
        return True
    except requests.RequestException as exc:
        _warn(f"Telegram ✗  {exc}")
        return False


def post_whatsapp(article: dict) -> bool:
    """
    Post to a WhatsApp group via Green API (free tier: 1500 msgs/month).
    
    Required env vars:
        GREENAPI_INSTANCE_ID   — your instance ID from green-api.com
        GREENAPI_API_TOKEN     — your API token
        WHATSAPP_CHAT_ID       — group chat ID, e.g. "120363XXXXXXXXXX@g.us"
                                 (get it from Green API → showMessagesHistory)
    """
    instance_id = os.getenv("GREENAPI_INSTANCE_ID", "").strip()
    api_token   = os.getenv("GREENAPI_API_TOKEN", "").strip()
    chat_id     = os.getenv("WHATSAPP_CHAT_ID", "").strip()

    if not instance_id or not api_token or not chat_id:
        _info("WhatsApp skipped — GREENAPI_INSTANCE_ID, GREENAPI_API_TOKEN, or WHATSAPP_CHAT_ID not set")
        return False

    try:
        url  = (
            f"https://api.green-api.com/waInstance{instance_id}"
            f"/sendMessage/{api_token}"
        )
        data = {
            "chatId":  chat_id,
            "message": _whatsapp_text(article),
        }
        resp = requests.post(url, json=data, timeout=15)
        resp.raise_for_status()
        _ok(f"WhatsApp ✓  {article['title'][:70]}")
        return True
    except requests.RequestException as exc:
        _warn(f"WhatsApp ✗  {exc}")
        return False


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run() -> int:
    """
    Main entry point.
    Returns: number of articles posted.
    """
    _banner()

    seen     = load_seen()
    articles = fetch_all_articles()

    _info(f"Loaded {len(seen)} seen IDs  |  Fetched {len(articles)} total articles")

    new_articles = [a for a in articles if a["id"] not in seen]
    _info(f"{len(new_articles)} new article(s) to post\n")

    if not new_articles:
        _info("Nothing new — all caught up. 🎉")
        return 0

    posted_ids: set[str] = set()

    for article in new_articles[:MAX_POSTS_PER_RUN]:
        _info(f"→  {article['source']:20s}  {article['title'][:60]}")
        post_discord(article)
        post_telegram(article)
        post_whatsapp(article)
        posted_ids.add(article["id"])
        print()

    save_seen(seen | posted_ids)
    _info(f"Done. Posted {len(posted_ids)} article(s). seen_articles.json updated.")
    return len(posted_ids)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _strip_html(text: str) -> str:
    """Remove HTML tags naively (no external dependency)."""
    import re
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ",  text)
    text = re.sub(r"&amp;",  "&",  text)
    text = re.sub(r"&lt;",   "<",  text)
    text = re.sub(r"&gt;",   ">",  text)
    text = re.sub(r"&quot;", '"',  text)
    text = re.sub(r"\s+",    " ",  text)
    return text.strip()


def _escape_html(text: str) -> str:
    """Minimal HTML escaping for Telegram messages."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _banner():
    print("\n" + "=" * 65)
    print(f"  CyberSec News Bot  —  {_utc_now()}")
    print("=" * 65 + "\n")


def _ok(msg):   print(f"  \033[32m✓\033[0m  {msg}")
def _warn(msg): print(f"  \033[33m⚠\033[0m  {msg}", file=sys.stderr)
def _info(msg): print(f"  \033[36mℹ\033[0m  {msg}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.exit(0 if run() >= 0 else 1)
