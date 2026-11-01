import hashlib
import numpy as np


def derive_rng(base_seed: int, namespace: str, name: str) -> np.random.Generator:
    seed_str = f"{base_seed}:{namespace}:{name}"
    derived_seed = int(hashlib.sha256(seed_str.encode("utf-8")).hexdigest(), 16) % (2**32)
    return np.random.default_rng(derived_seed)

