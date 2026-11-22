"""Verschlüsselung von Zugangsdaten (Fernet) und Admin-PIN."""


def encrypt(data: bytes) -> bytes:
    raise NotImplementedError


def decrypt(token: bytes) -> bytes:
    raise NotImplementedError


def verify_admin_pin(pin: str) -> bool:
    raise NotImplementedError
