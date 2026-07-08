"""Vault encryption tests."""

import pytest
from hive.browser import vault


@pytest.fixture(autouse=True)
def clean_vault(tmp_path, monkeypatch):
    monkeypatch.setenv("HIVE_HOME", str(tmp_path))
    monkeypatch.setenv("HIVE_VAULT_MASTER_PASSWORD", "test-vault-key-xyz")
    # Force fresh vault path
    vault.VAULT_DIR = tmp_path / "vault"
    vault.VAULT_FILE = vault.VAULT_DIR / "secrets.enc"
    yield


def test_store_and_get_credential():
    cid = vault.store_credential("test.com", "user@test.com", "secret123")
    assert cid
    cred = vault.get_credential("test.com")
    assert cred["username"] == "user@test.com"
    assert cred["password"] == "secret123"


def test_list_credentials_hides_password():
    vault.store_credential("a.com", "a@a.com", "pass")
    creds = vault.list_credentials()
    assert all("password" not in c for c in creds)


def test_store_and_get_card():
    cid = vault.store_card("test", "4111111111111111", "12/28", "123", "Test", "10001")
    card = vault.get_card(cid)
    assert card["last4"] == "1111"
    sensitive = vault.get_card_sensitive_data(cid)
    assert sensitive["card_number"] == "4111111111111111"


def test_delete_credential():
    cid = vault.store_credential("del.com", "x@x.com", "p")
    assert vault.delete_credential(cid)
    assert vault.get_credential("del.com") is None
