# youzi_web/features/research/service.py
from youzi_web.data_access import harness_view, seed_harness


def get_seed_harness_view() -> dict:
    return harness_view(seed_harness())
