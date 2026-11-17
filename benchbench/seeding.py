import hashlib
import random


def derive_seed(*parts: object) -> int:
    """Stable 64-bit seed from any parts, e.g. (study_seed, benchmark, page_id, condition)."""
    digest = hashlib.sha256(":".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(digest[:8], "big")


def rng(*parts: object) -> random.Random:
    return random.Random(derive_seed(*parts))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
