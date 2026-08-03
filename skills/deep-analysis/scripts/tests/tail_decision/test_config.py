from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision.config import DecisionConfig, config_hash


def test_default_config_uses_one_shared_8000_exposure_cap():
    config = DecisionConfig()
    assert config.account_assets == 10_000.0
    assert config.max_total_exposure == 8_000.0
    assert config.max_instrument_exposure == 4_000.0
    assert config.max_etf_candidates == 2
    assert config.max_stock_candidates == 2
    assert config.min_etf_daily_amount == 50_000_000.0
    assert config.max_etf_premium_pct == 1.0
    assert config.min_stock_daily_amount == 300_000_000.0
    assert config.min_stock_listing_days == 60
    assert config.max_stock_daily_gain_pct == 9.2
    assert config.near_limit_distance_pct == 0.5


def test_config_rejects_exposure_above_assets():
    with pytest.raises(ValueError, match="max_total_exposure"):
        DecisionConfig(account_assets=5_000.0, max_total_exposure=8_000.0)


def test_config_hash_is_deterministic():
    assert config_hash(DecisionConfig()) == config_hash(DecisionConfig())
