import hashlib
import json
import os
from base64 import b64decode

from Crypto.PublicKey import Ed25519


def load_ed25519_private_key_from_file(path: str) -> Ed25519.Ed25519PrivateKey:
    with open(path, "rb") as f:
        return Ed25519.import_key(f.read())


def load_ed25519_private_key_from_env(env_var: str) -> Ed25519.Ed25519PrivateKey:
    key_b64 = os.environ[env_var]
    return Ed25519.import_key(b64decode(key_b64))


def sha256_hash(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def canonical_json_serialize(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(',', ':')).encode("utf-8")
