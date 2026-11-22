"""Sicherheit: Verschlüsselung von Zugangsdaten, Admin-PIN, Sitzungs-Tokens, Sperre bei Fehlversuchen.

- Zugangsdaten (OAuth-Tokens, iCloud-Passwort) werden mit Fernet verschlüsselt.
  Der Schlüssel liegt in ``security.secret_key_file`` (Rechte 600).
- Die Admin-PIN wird mit scrypt gehasht in der Tabelle ``setting`` abgelegt.
- Sitzungen sind zustandslose, HMAC-signierte Tokens im Cookie. Der PIN-Hash fließt in die
  Signatur ein, eine PIN-Änderung macht also alle bestehenden Sitzungen ungültig.
"""
import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from sqlmodel import Session

from app.domain.models import Setting

PIN_SETTING_KEY = "admin_pin"
SESSION_COOKIE = "fp_session"
MIN_PIN_LENGTH = 4
MAX_PIN_LENGTH = 32


class SecretBox:
    def __init__(self, key_file: Path) -> None:
        self._key = self._load_or_create(key_file)
        self._fernet = Fernet(self._key)
        # Separater Schlüssel für Sitzungs-Signaturen, abgeleitet vom Hauptschlüssel
        self.signing_key = hashlib.sha256(b"familienplaner-session:" + self._key).digest()

    @staticmethod
    def _load_or_create(key_file: Path) -> bytes:
        if key_file.is_file():
            return key_file.read_bytes().strip()
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(key)
        return key

    def encrypt(self, data: bytes) -> bytes:
        return self._fernet.encrypt(data)

    def decrypt(self, token: bytes) -> bytes:
        try:
            return self._fernet.decrypt(token)
        except InvalidToken as exc:
            raise ValueError("Zugangsdaten konnten nicht entschlüsselt werden") from exc


# --- PIN ------------------------------------------------------------------------------------

def _hash_pin(pin: str, salt: bytes) -> bytes:
    return hashlib.scrypt(pin.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)


def validate_pin_format(pin: str) -> None:
    if not (MIN_PIN_LENGTH <= len(pin) <= MAX_PIN_LENGTH):
        raise ValueError(f"Die PIN muss {MIN_PIN_LENGTH}–{MAX_PIN_LENGTH} Zeichen lang sein")


def get_pin_record(session: Session) -> dict | None:
    row = session.get(Setting, PIN_SETTING_KEY)
    return row.value if row else None


def set_pin(session: Session, pin: str) -> None:
    validate_pin_format(pin)
    salt = secrets.token_bytes(16)
    value = {"salt": salt.hex(), "hash": _hash_pin(pin, salt).hex()}
    row = session.get(Setting, PIN_SETTING_KEY)
    if row is None:
        session.add(Setting(key=PIN_SETTING_KEY, value=value))
    else:
        row.value = value
        session.add(row)
    session.commit()


def verify_pin(session: Session, pin: str) -> bool:
    record = get_pin_record(session)
    if record is None:
        return False
    expected = bytes.fromhex(record["hash"])
    return hmac.compare_digest(_hash_pin(pin, bytes.fromhex(record["salt"])), expected)


# --- Sitzungen ------------------------------------------------------------------------------

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _sign(signing_key: bytes, payload: str, pin_hash: str) -> str:
    return _b64(hmac.new(signing_key, f"{payload}|{pin_hash}".encode(), hashlib.sha256).digest())


def create_session_token(signing_key: bytes, pin_hash: str, hours: int) -> str:
    payload = f"{int(time.time()) + hours * 3600}.{secrets.token_urlsafe(8)}"
    return f"{payload}.{_sign(signing_key, payload, pin_hash)}"


def verify_session_token(signing_key: bytes, pin_hash: str, token: str | None) -> bool:
    if not token:
        return False
    try:
        expires, nonce, signature = token.split(".")
        payload = f"{expires}.{nonce}"
        if not hmac.compare_digest(signature, _sign(signing_key, payload, pin_hash)):
            return False
        return int(expires) > time.time()
    except ValueError:
        return False


# --- Sperre bei Fehlversuchen ----------------------------------------------------------------

@dataclass
class LoginThrottle:
    """Nach ``max_attempts`` Fehlversuchen wird der Client gesperrt (Dauer verdoppelt sich)."""

    max_attempts: int = 5
    base_lock_seconds: int = 60
    _failures: dict[str, int] = field(default_factory=dict)
    _locked_until: dict[str, float] = field(default_factory=dict)

    def retry_after(self, client: str) -> int:
        remaining = self._locked_until.get(client, 0) - time.monotonic()
        return max(0, int(remaining + 0.999))

    def register_failure(self, client: str) -> None:
        count = self._failures.get(client, 0) + 1
        self._failures[client] = count
        if count >= self.max_attempts:
            factor = 2 ** (count - self.max_attempts)
            self._locked_until[client] = time.monotonic() + self.base_lock_seconds * factor

    def register_success(self, client: str) -> None:
        self._failures.pop(client, None)
        self._locked_until.pop(client, None)
