"""Security utilities: checkpoint field encryption using Fernet symmetric crypto.

If `settings.checkpoint_encryption_key` is set, fields listed in
`settings.sensitive_checkpoint_fields` will be encrypted before storage and
decrypted on load.
"""
import base64
import json
import logging
from typing import Dict, Any, List, Optional

from .config import settings

logger = logging.getLogger(__name__)


def _get_fernet():
    key = settings.checkpoint_encryption_key
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise ImportError("cryptography package required for checkpoint encryption")

    # Accept raw or base64 urlsafe key
    try:
        k = key.encode() if isinstance(key, str) else key
        # If key is not 32 urlsafe base64 bytes, attempt to derive
        return Fernet(k)
    except Exception:
        # Try base64 urlsafe encoding
        k2 = base64.urlsafe_b64encode(key.encode())
        return Fernet(k2)


def encrypt_fields(data: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
    f = _get_fernet()
    if not f:
        return data

    out = dict(data)
    for fld in fields:
        if fld in out and out[fld] is not None:
            try:
                raw = json.dumps(out[fld]).encode()
                token = f.encrypt(raw).decode()
                out[fld] = {"__encrypted__": True, "value": token}
            except Exception:
                logger.exception(f"Failed to encrypt field {fld}")
    return out


def decrypt_fields(data: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
    f = _get_fernet()
    if not f:
        return data

    out = dict(data)
    for fld in fields:
        v = out.get(fld)
        if isinstance(v, dict) and v.get("__encrypted__"):
            try:
                token = v.get("value")
                raw = f.decrypt(token.encode())
                out[fld] = json.loads(raw)
            except Exception:
                logger.exception(f"Failed to decrypt field {fld}")
    return out
