"""Local Authenticated Encryption Manager for sensitive operational command fields.

Provides field-level symmetric authenticated encryption (Fernet: AES-128-CBC + HMAC-SHA256
with 256-bit derived key) on raw captured terminal commands stored in SQLite.
Structured metadata (timestamps, incident IDs, health statuses) is stored in local SQLite
protected by POSIX 0600 file permissions and process isolation.
"""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
from cryptography.fernet import Fernet


class LocalCryptoManager:
    """Manages field-level symmetric authenticated encryption (Fernet) keys and payload cryptography."""

    def __init__(self, key_dir: str | None = None):
        if key_dir is not None:
            self.key_dir = Path(key_dir)
        elif "OPSGENOME_HOME" in os.environ:
            self.key_dir = Path(os.environ["OPSGENOME_HOME"])
        else:
            try:
                home_dir = Path.home() / ".opsgenome"
                home_dir.mkdir(parents=True, exist_ok=True)
                self.key_dir = home_dir
            except (PermissionError, OSError):
                # Fallback to local workspace directory
                local_dir = Path("./.opsgenome_data")
                local_dir.mkdir(parents=True, exist_ok=True)
                self.key_dir = local_dir

        self.key_dir.mkdir(parents=True, exist_ok=True)
        self.key_file = self.key_dir / "master.key"
        self._fernet = Fernet(self._load_or_create_key())

    def _load_or_create_key(self) -> bytes:
        """Load the master key from disk or generate a new secure 256-bit Fernet key."""
        if self.key_file.exists():
            with open(self.key_file, "rb") as f:
                return f.read().strip()
        else:
            key = Fernet.generate_key()
            with open(self.key_file, "wb") as f:
                f.write(key)
            try:
                os.chmod(self.key_file, 0o600)
            except OSError:
                pass
            return key

    @classmethod
    def from_passphrase(cls, passphrase: str) -> LocalCryptoManager:
        """Derive a deterministic AES-256 key from a user-supplied passphrase."""
        instance = cls.__new__(cls)
        digest = hashlib.sha256(passphrase.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest)
        instance._fernet = Fernet(key)
        return instance

    def encrypt(self, plaintext: str | bytes) -> str:
        """Encrypt plaintext string or bytes into a base64 ciphertext string."""
        if isinstance(plaintext, str):
            data = plaintext.encode("utf-8")
        else:
            data = plaintext
        return self._fernet.encrypt(data).decode("utf-8")

    def decrypt(self, ciphertext: str | bytes) -> str:
        """Decrypt base64 ciphertext string back to plaintext UTF-8 string."""
        if isinstance(ciphertext, str):
            data = ciphertext.encode("utf-8")
        else:
            data = ciphertext
        return self._fernet.decrypt(data).decode("utf-8")
