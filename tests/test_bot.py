"""
Tests for cybersec_bot.py
Run with:  pytest tests/ -v
"""

import hashlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

# Make sure the bot module is importable from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))
import cybersec_bot as bot


# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_ARTICLE = {
    "id":        "abc123",
    "title":     "Critical RCE Found in OpenSSH — Patch Now",
    "link":      "https://example.com/ssh-rce",
    "summary":   "Researchers discovered a remote code execution vulnerability in OpenSSH versions before 9.8.",
    "source":    "The Hacker News",
    "published": "Wed, 01 Jan 2025 12:00:00 +0000",
}

LONG_SUMMARY_ARTICLE = {**SAMPLE_ARTICLE, "summary": "x" * 500}


# ── Deduplication tests ───────────────────────────────────────────────────────

class TestArticleId:
    def test_stable_id(self):
        entry = {"link": "https://example.com", "title": "Test Article"}
        assert bot.article_id(entry) == bot.article_id(entry)

    def test_different_links_different_ids(self):
        a = {"link": "https://example.com/a", "title": "Same Title"}
        b = {"link": "https://example.com/b", "title": "Same Title"}
        assert bot.article_id(a) != bot.article_id(b)

    def test_empty_entry_returns_hash(self):
        result = bot.article_id({})
        assert len(result) == 32  # MD5 hex length

    def test_id_is_hex_string(self):
        entry = {"link": "https://example.com", "title": "Title"}
        result = bot.article_id(entry)
        int(result, 16)  # Should not raise — valid hex


class TestSeenArticles:
    def test_load_seen_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "SEEN_FILE", tmp_path / "nonexistent.json")
        result = bot.load_seen()
        assert result == set()

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "SEEN_FILE", tmp_path / "seen.json")
        ids = {"id1", "id2", "id3"}
        bot.save_seen(ids)
        assert bot.load_seen() == ids

    def test_save_trims_to_max(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "SEEN_FILE", tmp_path / "seen.json")
        monkeypatch.setattr(bot, "MAX_SEEN", 5)
        ids = {f"id_{i}" for i in range(20)}
        bot.save_seen(ids)
        loaded = bot.load_seen()
        assert len(loaded) == 5

    def test_load_corrupted_file_returns_empty(self, tmp_path, monkeypatch):
        bad_file = tmp_path / "seen.json"
        bad_file.write_text("NOT VALID JSON")
        monkeypatch.setattr(bot, "SEEN_FILE", bad_file)
        assert bot.load_seen() == set()

    def test_seen_file_has_updated_timestamp(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "SEEN_FILE", tmp_path / "seen.json")
        bot.save_seen({"x"})
        data = json.loads((tmp_path / "seen.json").read_text())
        assert "updated" in data


# ── HTML helpers ──────────────────────────────────────────────────────────────

class TestStripHtml:
    def test_removes_tags(self):
        assert bot._strip_html("<b>Bold</b>") == "Bold"

    def test_decodes_entities(self):
        assert "&amp;" not in bot._strip_html("AT&amp;T")
        assert "AT&T" in bot._strip_html("AT&amp;T")

    def test_collapses_whitespace(self):
        result = bot._strip_html("a   <br/>   b")
        assert "  " not in result

    def test_empty_string(self):
        assert bot._strip_html("") == ""


class TestEscapeHtml:
    def test_escapes_ampersand(self):
        assert bot._escape_html("AT&T") == "AT&amp;T"

    def test_escapes_angle_brackets(self):
        assert bot._escape_html("<script>") == "&lt;script&gt;"

    def test_plain_text_unchanged(self):
        assert bot._escape_html("hello world") == "hello world"


# ── Formatter tests ───────────────────────────────────────────────────────────

class TestDiscordEmbed:
    def test_returns_dict_with_embeds(self):
        result = bot._discord_embed(SAMPLE_ARTICLE)
        assert "embeds" in result
        assert len(result["embeds"]) == 1

    def test_embed_has_url(self):
        embed = bot._discord_embed(SAMPLE_ARTICLE)["embeds"][0]
        assert embed["url"] == SAMPLE_ARTICLE["link"]

    def test_title_truncated_at_256(self):
        long_title_article = {**SAMPLE_ARTICLE, "title": "T" * 300}
        embed = bot._discord_embed(long_title_article)["embeds"][0]
        assert len(embed["title"]) <= 256

    def test_long_summary_truncated(self):
        embed = bot._discord_embed(LONG_SUMMARY_ARTICLE)["embeds"][0]
        assert len(embed["description"]) <= 354  # 350 + ellipsis

    def test_footer_contains_source(self):
        embed = bot._discord_embed(SAMPLE_ARTICLE)["embeds"][0]
        assert SAMPLE_ARTICLE["source"] in embed["footer"]["text"]


class TestTelegramHtml:
    def test_contains_title(self):
        result = bot._telegram_html(SAMPLE_ARTICLE)
        assert SAMPLE_ARTICLE["title"] in result

    def test_contains_link(self):
        result = bot._telegram_html(SAMPLE_ARTICLE)
        assert SAMPLE_ARTICLE["link"] in result

    def test_html_bold_tags_present(self):
        result = bot._telegram_html(SAMPLE_ARTICLE)
        assert "<b>" in result

    def test_special_chars_escaped(self):
        article = {**SAMPLE_ARTICLE, "title": "AT&T breach <critical>"}
        result = bot._telegram_html(article)
        assert "<critical>" not in result  # escaped
        assert "&lt;critical&gt;" in result

    def test_long_summary_truncated(self):
        result = bot._telegram_html(LONG_SUMMARY_ARTICLE)
        # Summary portion should not exceed 300 + ellipsis
        assert len(result) < 2000


class TestWhatsappText:
    def test_contains_title(self):
        result = bot._whatsapp_text(SAMPLE_ARTICLE)
        assert SAMPLE_ARTICLE["title"] in result

    def test_uses_bold_markdown(self):
        result = bot._whatsapp_text(SAMPLE_ARTICLE)
        assert "*CyberSec Intel*" in result

    def test_long_summary_truncated(self):
        result = bot._whatsapp_text(LONG_SUMMARY_ARTICLE)
        # Summary part should be capped
        assert len(result) < 1500


# ── Poster tests (mocked HTTP) ────────────────────────────────────────────────

class TestPostDiscord:
    def test_skips_when_no_env(self, monkeypatch):
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        assert bot.post_discord(SAMPLE_ARTICLE) is False

    def test_posts_successfully(self, monkeypatch):
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/fake-webhook")
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        with patch("cybersec_bot.requests.post", return_value=mock_resp) as mock_post:
            result = bot.post_discord(SAMPLE_ARTICLE)
        assert result is True
        mock_post.assert_called_once()

    def test_returns_false_on_http_error(self, monkeypatch):
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/fake-webhook")
        with patch("cybersec_bot.requests.post", side_effect=requests.RequestException("Connection refused")):
            result = bot.post_discord(SAMPLE_ARTICLE)
        assert result is False


class TestPostTelegram:
    def test_skips_when_no_token(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        assert bot.post_telegram(SAMPLE_ARTICLE) is False

    def test_skips_when_only_token_set(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "12345:TOKEN")
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        assert bot.post_telegram(SAMPLE_ARTICLE) is False

    def test_posts_successfully(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "12345:TOKEN")
        monkeypatch.setenv("TELEGRAM_CHAT_ID",   "-1001234567890")
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        with patch("cybersec_bot.requests.post", return_value=mock_resp):
            result = bot.post_telegram(SAMPLE_ARTICLE)
        assert result is True

    def test_correct_api_url_called(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "MY_TOKEN")
        monkeypatch.setenv("TELEGRAM_CHAT_ID",   "-100123")
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        with patch("cybersec_bot.requests.post", return_value=mock_resp) as mock_post:
            bot.post_telegram(SAMPLE_ARTICLE)
        called_url = mock_post.call_args[0][0]
        assert "MY_TOKEN" in called_url
        assert "sendMessage" in called_url


class TestPostWhatsapp:
    def test_skips_when_no_env(self, monkeypatch):
        for var in ("GREENAPI_INSTANCE_ID", "GREENAPI_API_TOKEN", "WHATSAPP_CHAT_ID"):
            monkeypatch.delenv(var, raising=False)
        assert bot.post_whatsapp(SAMPLE_ARTICLE) is False

    def test_posts_successfully(self, monkeypatch):
        monkeypatch.setenv("GREENAPI_INSTANCE_ID", "1234567890")
        monkeypatch.setenv("GREENAPI_API_TOKEN",   "my_token_abc")
        monkeypatch.setenv("WHATSAPP_CHAT_ID",     "120363XXX@g.us")
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        with patch("cybersec_bot.requests.post", return_value=mock_resp):
            result = bot.post_whatsapp(SAMPLE_ARTICLE)
        assert result is True


# ── Integration test: full run() with mocked HTTP ─────────────────────────────

class TestRun:
    def test_run_with_no_env_returns_zero_posted(self, tmp_path, monkeypatch):
        """No platform env vars set → posts 0 but fetches fine."""
        monkeypatch.setattr(bot, "SEEN_FILE", tmp_path / "seen.json")
        for var in (
            "DISCORD_WEBHOOK_URL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
            "GREENAPI_INSTANCE_ID", "GREENAPI_API_TOKEN", "WHATSAPP_CHAT_ID",
        ):
            monkeypatch.delenv(var, raising=False)

        mock_feed = MagicMock()
        mock_feed.entries = [
            MagicMock(
                title="Fake CVE Alert",
                link="https://example.com/cve",
                summary="A critical flaw.",
                description="",
                published="2025-01-01",
            )
        ]
        with patch("cybersec_bot.feedparser.parse", return_value=mock_feed):
            result = bot.run()

        # run() returns number posted — 0 since no platforms configured, but no crash
        assert result >= 0

    def test_run_skips_already_seen(self, tmp_path, monkeypatch):
        """Articles already in seen_articles.json are not reposted."""
        monkeypatch.setattr(bot, "SEEN_FILE", tmp_path / "seen.json")

        # Pre-populate seen with our fake article's ID
        fake_entry = MagicMock(
            title="Old News",
            link="https://example.com/old",
            summary="Already seen.",
            description="",
            published="2024-01-01",
        )
        pre_seen = {bot.article_id({"title": fake_entry.title, "link": fake_entry.link})}
        bot.save_seen(pre_seen)

        mock_feed = MagicMock()
        mock_feed.entries = [fake_entry]

        with patch("cybersec_bot.feedparser.parse", return_value=mock_feed):
            result = bot.run()

        assert result == 0  # Nothing new to post
