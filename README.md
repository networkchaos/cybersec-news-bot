# 🔐 CyberSec News Bot

Automatically fetches the latest cybersecurity news and posts it to your **Discord**, **Telegram**, and **WhatsApp** groups — for free, with zero servers, running 24/7 even when you're offline.

**How it works:** GitHub Actions runs the bot every 6 hours on GitHub's free servers. The bot pulls news from 8 RSS feeds (The Hacker News, BleepingComputer, Krebs on Security, SANS, etc.), filters out anything already posted, and sends the freshest articles to your communities.

---

## ✅ What you need (all free)

| Thing | Cost | Why |
|---|---|---|
| GitHub account | Free | Hosts code + runs the scheduler |
| Discord webhook | Free | Receives messages in your Discord |
| Telegram bot | Free | Receives messages in your Telegram group |
| Green API account | Free (1500 msgs/month) | WhatsApp group messages |

---

## 🚀 Step-by-Step Setup

### Step 1 — Fork or create the GitHub repo

1. Go to **github.com** and sign in (create an account if needed — it's free).
2. Click **"New repository"** → name it `cybersec-news-bot`.
3. Make it **Public** (required for unlimited free Actions minutes).
4. Upload all the files from this folder into the repo.

> 📌 **Tip:** You can drag-and-drop files onto the GitHub web interface — no Git needed.

---

### Step 2 — Set up Discord (5 minutes)

Discord uses **Incoming Webhooks** — no bot account, just a URL you paste.

1. Open Discord and go to your hacking community server.
2. Click the **⚙️ gear icon** next to the channel you want news posted in.
3. Click **"Integrations"** → **"Webhooks"** → **"New Webhook"**.
4. Give it a name like `CyberSec Intel` and click **"Copy Webhook URL"**.
5. Save that URL — you'll add it to GitHub Secrets in Step 5.

---

### Step 3 — Set up Telegram (10 minutes)

#### 3a. Create a Telegram Bot
1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the prompts (pick any name and username).
3. BotFather will give you a **token** that looks like: `1234567890:ABCDefGhij...`
4. Save this token.

#### 3b. Add the bot to your group
1. Open your Telegram group.
2. Go to **Group Settings** → **Administrators** → **Add Administrator**.
3. Search for your bot's username and add it.

#### 3c. Get the group Chat ID
1. Add **@RawDataBot** to your group (just temporarily).
2. Send any message in the group.
3. RawDataBot will reply with JSON. Look for `"id"` inside `"chat"` — it's a negative number like `-1001234567890`.
4. That's your **TELEGRAM_CHAT_ID**. Remove @RawDataBot after.

> 📌 **For channels:** Add your bot as an admin, and the Chat ID is `@your_channel_username` (with the @).

---

### Step 4 — Set up WhatsApp via Green API (15 minutes)

WhatsApp doesn't have a free official bot API, but **Green API** has a free tier (1500 messages/month — plenty for a news bot).

1. Go to **green-api.com** and create a free account.
2. Click **"Create Instance"** and choose the free plan.
3. You'll get an **Instance ID** (a number) and an **API Token**.
4. Click **"Connect"** and scan the QR code with WhatsApp on your phone (just like WhatsApp Web).
5. Your phone needs to stay connected to the internet (not necessarily open, just online).

#### Get your WhatsApp Group Chat ID
1. In Green API dashboard, click **"API"** → **"Receiving"** → **"LastIncomingMessages"**.
2. Send a message in your WhatsApp group.
3. In the response, look for `"chatId"` — it looks like `120363XXXXXXXXXX@g.us`.
4. That's your **WHATSAPP_CHAT_ID**.

> ⚠️ **Note on WhatsApp:** Because this uses an unofficial connection method, it's possible WhatsApp may detect and block it. This is rare for read-only bots, but be aware. Green API is the most stable free option available.

---

### Step 5 — Add secrets to GitHub (5 minutes)

GitHub Secrets are encrypted — no one can see them, not even you after saving.

1. Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions**.
2. Click **"New repository secret"** for each of these:

| Secret Name | Value |
|---|---|
| `DISCORD_WEBHOOK_URL` | The webhook URL from Step 2 |
| `TELEGRAM_BOT_TOKEN` | Your bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | The group chat ID (negative number) |
| `GREENAPI_INSTANCE_ID` | Your Green API instance ID |
| `GREENAPI_API_TOKEN` | Your Green API token |
| `WHATSAPP_CHAT_ID` | Your WhatsApp group ID ending in `@g.us` |

> 📌 You only need to add the secrets for platforms you want to use. If you skip WhatsApp, just don't add those 3 secrets — the bot will skip WhatsApp automatically.

---

### Step 6 — Enable GitHub Actions

1. In your repo, click the **"Actions"** tab.
2. If prompted, click **"I understand my workflows, go ahead and enable them"**.
3. Click on **"CyberSec News Bot"** in the left sidebar.
4. Click **"Run workflow"** → **"Run workflow"** to trigger it manually and test.

Watch the logs — you should see articles being posted to your channels within 1-2 minutes.

---

## ⚙️ Configuration

### Change posting frequency

Edit `.github/workflows/news_bot.yml` and change the cron line:

```yaml
schedule:
  - cron: '0 */6 * * *'   # Every 6 hours (default)
  # - cron: '0 */4 * * *' # Every 4 hours
  # - cron: '0 8,20 * * *' # Twice a day at 8AM and 8PM UTC
  # - cron: '0 9 * * *'   # Once a day at 9AM UTC
```

### Change number of articles per run

In `cybersec_bot.py`, change:
```python
MAX_POSTS_PER_RUN = int(os.getenv("MAX_POSTS_PER_RUN", "3"))
```
Or add a `MAX_POSTS_PER_RUN` secret in GitHub with value `5` (or whatever you want).

### Add or remove news sources

In `cybersec_bot.py`, edit the `RSS_FEEDS` list:
```python
RSS_FEEDS = [
    {"name": "My Custom Feed", "url": "https://example.com/feed.rss"},
    # ...
]
```

Some good additional feeds:
- `https://nvd.nist.gov/feeds/xml/cve/misc/nvd-rss.xml` — NVD CVE feed
- `https://www.cisa.gov/cybersecurity-advisories/all.xml` — CISA advisories
- `https://blog.malwarebytes.com/feed/` — Malwarebytes blog
- `https://nakedsecurity.sophos.com/feed/` — Sophos Naked Security

---

## 🧪 Running Tests

```bash
# Install dependencies
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --tb=short
```

All tests use mocked HTTP — no real API calls are made.

---

## 📁 Project Structure

```
cybersec-news-bot/
├── .github/
│   └── workflows/
│       └── news_bot.yml       ← GitHub Actions scheduler
├── tests/
│   └── test_bot.py            ← Full test suite
├── cybersec_bot.py            ← Main bot (single file)
├── requirements.txt
├── seen_articles.json         ← Auto-created; tracks posted articles
└── README.md
```

---

## 🐛 Troubleshooting

**No messages being posted:**
- Check the Actions run logs (Actions tab → click on the run → click the job).
- Make sure your secrets are named exactly right (case-sensitive).

**Telegram: "chat not found":**
- Make sure you added the bot as an admin to the group.
- Make sure the Chat ID is correct (should be negative like `-1001234567890`).

**WhatsApp stopped working:**
- Your phone may have gone offline. Open WhatsApp on your phone and reconnect.
- Go to Green API dashboard and reconnect the instance.

**Duplicate posts:**
- Check that `seen_articles.json` is being committed back. Look at the last step in your Actions logs.
- Make sure the workflow has `permissions: contents: write`.

**GitHub Actions not running on schedule:**
- GitHub may pause scheduled workflows on inactive repos. To fix: make any small commit (edit README, etc.) to show the repo is active.

---

## 💡 Ideas to Extend This Bot

- **CTF announcements**: Add CTFtime.org RSS feed
- **CVE alerts only**: Filter articles whose title contains "CVE-"
- **Severity filter**: Only post articles containing words like "critical", "RCE", "zero-day"
- **Weekly digest**: Change schedule to once a week, post top 10 articles
- **Voting/reactions**: More complex, needs a real server — but Discord reactions work out of the box

---

## 📜 License

MIT — use freely, modify, share with your hacking community.
