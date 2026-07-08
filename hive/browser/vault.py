"""Encrypted local vault for site credentials and payment cards.

Secrets are never stored in plaintext .env and are never sent to the LLM.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

VAULT_DIR = Path(os.environ.get("HIVE_HOME", Path.home() / ".hive")) / "vault"
VAULT_FILE = VAULT_DIR / "secrets.enc"
KEYRING_SERVICE = "hive-os"
KEYRING_USER = "vault-key"


def _derive_key_from_password(password: str) -> bytes:
    salt = b"hive-vault-v1"
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return base64.urlsafe_b64encode(derived)


def _get_key() -> bytes:
    master = os.environ.get("HIVE_VAULT_MASTER_PASSWORD")
    if master:
        return _derive_key_from_password(master)

    try:
        import keyring
        stored = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
        if stored:
            return stored.encode()
    except Exception as e:
        logger.debug("Keyring unavailable: %s", e)

    key_file = VAULT_DIR / ".vault_key"
    if key_file.exists():
        return key_file.read_bytes()

    new_key = Fernet.generate_key()
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import keyring
        keyring.set_password(KEYRING_SERVICE, KEYRING_USER, new_key.decode())
        logger.info("Created new vault encryption key in OS keyring")
    except Exception:
        key_file.write_bytes(new_key)
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
        logger.warning("Vault key stored at %s (keyring unavailable)", key_file)
    return new_key


def _fernet() -> Fernet:
    return Fernet(_get_key())


def _load_data() -> dict:
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    if not VAULT_FILE.exists():
        return {"credentials": {}, "cards": {}, "accounts": {}}
    try:
        raw = VAULT_FILE.read_bytes()
        decrypted = _fernet().decrypt(raw)
        return json.loads(decrypted.decode())
    except InvalidToken:
        logger.error("Vault decryption failed — wrong master password or corrupted vault")
        return {"credentials": {}, "cards": {}, "accounts": {}}
    except Exception as e:
        logger.error("Vault load error: %s", e)
        return {"credentials": {}, "cards": {}, "accounts": {}}


def _save_data(data: dict) -> None:
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    encrypted = _fernet().encrypt(json.dumps(data).encode())
    VAULT_FILE.write_bytes(encrypted)
    try:
        os.chmod(VAULT_FILE, 0o600)
    except OSError:
        pass


def store_credential(site: str, username: str, password: str, extra: Optional[dict] = None) -> str:
    data = _load_data()
    cred_id = secrets.token_hex(8)
    data["credentials"][cred_id] = {
        "site": site.lower().strip(),
        "username": username,
        "password": password,
        "extra": extra or {},
        "created_at": time.time(),
    }
    _save_data(data)
    return cred_id


def get_credential(site: str) -> Optional[dict]:
    data = _load_data()
    site_lower = site.lower().strip()
    matches = [
        (cid, c) for cid, c in data["credentials"].items()
        if c.get("site") == site_lower
    ]
    if not matches:
        return None
    matches.sort(key=lambda x: x[1].get("created_at", 0), reverse=True)
    cid, cred = matches[0]
    return {"id": cid, **cred}


def list_credentials() -> list[dict]:
    data = _load_data()
    return [
        {"id": cid, "site": c["site"], "username": c["username"], "created_at": c.get("created_at")}
        for cid, c in data["credentials"].items()
    ]


def delete_credential(cred_id: str) -> bool:
    data = _load_data()
    if cred_id in data["credentials"]:
        del data["credentials"][cred_id]
        _save_data(data)
        return True
    return False


def get_credentials_dict(site: str) -> dict:
    cred = get_credential(site)
    if not cred:
        return {}
    result = {}
    if cred.get("username"):
        if "@" in cred["username"]:
            result["email"] = cred["username"]
        else:
            result["username"] = cred["username"]
        result["email"] = result.get("email", cred["username"])
    if cred.get("password"):
        result["password"] = cred["password"]
    return result


def store_card(
    label: str,
    number: str,
    expiry: str,
    cvv: str,
    name: str = "",
    billing_zip: str = "",
) -> str:
    data = _load_data()
    card_id = secrets.token_hex(8)
    data["cards"][card_id] = {
        "label": label,
        "number": number,
        "expiry": expiry,
        "cvv": cvv,
        "name": name,
        "billing_zip": billing_zip,
        "last4": number[-4:] if len(number) >= 4 else "****",
        "created_at": time.time(),
    }
    _save_data(data)
    return card_id


def get_card(card_id: Optional[str] = None, label: Optional[str] = None) -> Optional[dict]:
    data = _load_data()
    cards = data.get("cards", {})
    if card_id and card_id in cards:
        return {"id": card_id, **cards[card_id]}
    if label:
        for cid, c in cards.items():
            if c.get("label", "").lower() == label.lower():
                return {"id": cid, **c}
    if cards:
        best = max(cards.items(), key=lambda x: x[1].get("created_at", 0))
        return {"id": best[0], **best[1]}
    return None


def list_cards() -> list[dict]:
    data = _load_data()
    return [
        {"id": cid, "label": c["label"], "last4": c.get("last4", "****"), "name": c.get("name", "")}
        for cid, c in data.get("cards", {}).items()
    ]


def delete_card(card_id: str) -> bool:
    data = _load_data()
    if card_id in data.get("cards", {}):
        del data["cards"][card_id]
        _save_data(data)
        return True
    return False


def get_card_sensitive_data(card_id: Optional[str] = None) -> dict:
    card = get_card(card_id)
    if not card:
        return {}
    return {
        "card_number": card.get("number", ""),
        "card_expiry": card.get("expiry", ""),
        "card_cvv": card.get("cvv", ""),
        "card_name": card.get("name", ""),
        "billing_zip": card.get("billing_zip", ""),
    }


def store_account(
    site: str,
    email: str,
    session_name: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> str:
    data = _load_data()
    acc_id = secrets.token_hex(8)
    data.setdefault("accounts", {})[acc_id] = {
        "site": site.lower().strip(),
        "email": email,
        "session_name": session_name,
        "metadata": metadata or {},
        "created_at": time.time(),
    }
    _save_data(data)
    return acc_id


def list_accounts() -> list[dict]:
    data = _load_data()
    return [
        {"id": aid, "site": a["site"], "email": a["email"], "session_name": a.get("session_name")}
        for aid, a in data.get("accounts", {}).items()
    ]
