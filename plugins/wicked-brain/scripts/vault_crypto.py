"""vault_crypto.py - client-side encryption for Phase 3 sync.

Every note that leaves this device for the sync server is encrypted here
first; every note that arrives from the sync server is decrypted here after.
The server (sync_server/) never sees plaintext and never holds the key - this
module is the entire trust boundary.

Key derivation: scrypt(passphrase, salt) -> a 32-byte key, fed to Fernet
(AES-128-CBC + HMAC, from the `cryptography` package - well-audited, no
hand-rolled crypto here). The salt is NOT secret (see sync_server/README.md);
only the passphrase is, and it is never written to disk or sent to the
server - it lives only in the WICKED_BRAIN_SYNC_PASSPHRASE env var for as long as a
sync command is running.
"""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

_SCRYPT_N = 2**14  # cost parameter - a few hundred ms on a laptop, not annoying per sync run
_SCRYPT_R = 8
_SCRYPT_P = 1
_KEY_LEN = 32


class WrongPassphrase(Exception):
    """Raised by decrypt() when the key doesn't open the ciphertext - a wrong
    passphrase or a salt mismatch, not a corrupted-data distinction the caller
    can usefully act on differently."""


def new_salt() -> bytes:
    return os.urandom(16)


def derive_key(passphrase: str, salt: bytes) -> bytes:
    """A Fernet-compatible (urlsafe-base64) 32-byte key from a passphrase + salt."""
    if not passphrase:
        raise ValueError("passphrase must not be empty")
    kdf = Scrypt(salt=salt, length=_KEY_LEN, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    raw = kdf.derive(passphrase.encode("utf-8"))
    return base64.urlsafe_b64encode(raw)


def encrypt(plaintext: bytes, key: bytes) -> bytes:
    return Fernet(key).encrypt(plaintext)


def decrypt(ciphertext: bytes, key: bytes) -> bytes:
    try:
        return Fernet(key).decrypt(ciphertext)
    except InvalidToken as e:
        raise WrongPassphrase("could not decrypt - wrong passphrase, wrong salt, or corrupted data") from e


def content_hash(plaintext: bytes) -> str:
    """sha256 of the PLAINTEXT, computed before encryption. Sent to the server
    alongside the ciphertext so it can diff manifests without ever decrypting -
    the hash reveals nothing about content (one-way), only whether two notes
    are byte-identical."""
    return hashlib.sha256(plaintext).hexdigest()
