"""Tests for personal-inbox verification code extraction."""

import os

import pytest

from hive.browser.email_codes import extract_code, resolve_imap_config


class TestExtractCode:
    def test_google_style_code(self):
        assert extract_code("Your Google verification code", "G-482913 is your code") == "482913"

    def test_labelled_numeric_code(self):
        assert extract_code("Verify your email", "Your verification code is: 583920") == "583920"

    def test_labelled_alphanumeric_code(self):
        assert extract_code("Login code", "Use code 7XK92B to sign in") == "7XK92B"

    def test_code_in_subject(self):
        assert extract_code("123456 is your Spotify code", "Enter it to continue") == "123456"

    def test_code_on_verification_line(self):
        body = "Hello,\nSomeone tried to log in.\nVerification code: 9081\nThanks"
        assert extract_code("Security alert", body) == "9081"

    def test_standalone_six_digit_fallback(self):
        assert extract_code("Welcome", "Please enter 440217 on the website.") == "440217"

    def test_no_code(self):
        assert extract_code("Newsletter", "Check out our summer deals!") is None

    def test_ignores_years_in_footer_when_labelled_code_exists(self):
        body = "Your code is 775501.\n\nCopyright 2026 Example Inc."
        assert extract_code("Verification", body) == "775501"


class TestResolveImapConfig:
    def test_unconfigured_returns_none(self, monkeypatch):
        for var in ("HIVE_IMAP_USER", "HIVE_IMAP_PASSWORD", "HIVE_IMAP_HOST"):
            monkeypatch.delenv(var, raising=False)
        assert resolve_imap_config() is None

    def test_gmail_host_autodetected(self, monkeypatch):
        monkeypatch.setenv("HIVE_IMAP_USER", "someone@gmail.com")
        monkeypatch.setenv("HIVE_IMAP_PASSWORD", "app-password")
        monkeypatch.delenv("HIVE_IMAP_HOST", raising=False)
        config = resolve_imap_config()
        assert config["host"] == "imap.gmail.com"
        assert config["port"] == 993

    def test_explicit_host_wins(self, monkeypatch):
        monkeypatch.setenv("HIVE_IMAP_USER", "someone@company.com")
        monkeypatch.setenv("HIVE_IMAP_PASSWORD", "app-password")
        monkeypatch.setenv("HIVE_IMAP_HOST", "mail.company.com")
        config = resolve_imap_config()
        assert config["host"] == "mail.company.com"
