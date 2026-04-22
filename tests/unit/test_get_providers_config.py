"""Ensure config/providers.yaml is found when resolving project root."""


def test_get_providers_config_has_image_generation_models():
    from shared import utils

    utils._providers_config_cache = {}
    from shared.utils import get_providers_config

    cfg = get_providers_config()
    ig = cfg.get("image_generation_models") or {}
    rows = ig.get("models") or ig.get("tiers") or []
    assert len(rows) >= 1
    for row in rows:
        assert row.get("id")
