from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision.config import DecisionConfig, config_hash


def test_default_config_uses_cash_aware_12000_single_position_cap():
    config = DecisionConfig()
    assert config.configured_position_cap_cny == 12_000.0
    assert config.available_cash_cny == 12_000.0
    assert config.effective_position_cap_cny == 12_000.0
    assert config.max_total_exposure == 12_000.0
    assert config.max_instrument_exposure == 12_000.0
    assert config.research_stock_limit == 300
    assert config.realtime_stock_limit == 30
    assert config.realtime_etf_limit == 10
    assert config.max_etf_candidates == 2
    assert config.max_stock_candidates == 3
    assert config.min_etf_daily_amount == 50_000_000.0
    assert config.max_etf_premium_pct == 1.0
    assert config.min_stock_daily_amount == 300_000_000.0
    assert config.min_stock_listing_days == 60
    assert config.max_stock_daily_gain_pct == 9.2
    assert config.near_limit_distance_pct == 0.5


def test_available_cash_is_the_effective_cap_when_lower():
    config = DecisionConfig(
        configured_position_cap_cny=12_000.0,
        available_cash_cny=7_600.0,
    )
    assert config.effective_position_cap_cny == 7_600.0


def test_missing_available_cash_has_no_effective_cap():
    assert DecisionConfig(available_cash_cny=None).effective_position_cap_cny is None


def test_config_rejects_non_positive_cap_or_cash():
    with pytest.raises(ValueError, match="configured_position_cap_cny"):
        DecisionConfig(configured_position_cap_cny=0.0)
    with pytest.raises(ValueError, match="available_cash_cny"):
        DecisionConfig(available_cash_cny=0.0)


def test_config_hash_is_deterministic():
    assert config_hash(DecisionConfig()) == config_hash(DecisionConfig())
