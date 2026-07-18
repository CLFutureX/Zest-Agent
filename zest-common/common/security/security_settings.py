"""
Shared security settings for zest-agent.
Provides cipher creation from environment variables.
"""
import os
import logging
from pydantic import SecretStr
from common.utils.cipher import Cipher

_logger = logging.getLogger(__name__)

# Environment variable name
SECRET_KEY_ENV = "ZEST_SECRET_KEY" 

_cipher_singleton: Cipher | None | bool = False  # False = not yet initialized


def get_secret_key() -> SecretStr | None:
    """Read secret key from environment variables.

    Priority:
      1. ZEST_SECRET_KEY 
    """
    value = os.getenv(SECRET_KEY_ENV)
    if value:
        return SecretStr(value)
    return None


def get_cipher_from_env() -> Cipher | None:
    """Lazy singleton: build Cipher from secret key env var.

    Returns None and logs a warning if no secret key is configured.
    The same Cipher instance is reused across calls within a process.
    """
    global _cipher_singleton
    if _cipher_singleton is not False:
        return _cipher_singleton  # type: ignore[return-value]

    secret_key = get_secret_key()
    if secret_key is None:
        _logger.warning(
            "⚠️ ZEST_SECRET_KEY was not defined. "
            "Secrets will not be persisted between restarts."
        )
        _cipher_singleton = None
    else:
        _cipher_singleton = Cipher(secret_key.get_secret_value())

    return _cipher_singleton  # type: ignore[return-value]
