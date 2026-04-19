from app.services.cost_calculator import calculate_cloud_cost, calculate_onprem_monthly_cost
from app.models.cost_config import CloudPricing, OnPremConfig


def _mock_pricing():
    return CloudPricing(
        provider="openai", model_name="gpt-4o",
        prompt_cost_per_1k=0.005, completion_cost_per_1k=0.015,
    )


def _mock_onprem():
    return OnPremConfig(
        config_name="test",
        hardware_cost_usd=1200.0,
        amortization_months=36,
        power_draw_watts=100.0,
        electricity_cost_kwh=0.10,
        utilization_hours_day=8.0,
    )


def test_cloud_cost_calculation():
    pricing = _mock_pricing()
    cost = calculate_cloud_cost(1000, 500, pricing)
    # 1000/1000 * 0.005 + 500/1000 * 0.015 = 0.005 + 0.0075 = 0.0125
    assert abs(cost - 0.0125) < 1e-6


def test_cloud_cost_zero_tokens():
    pricing = _mock_pricing()
    assert calculate_cloud_cost(0, 0, pricing) == 0.0


def test_onprem_monthly_cost():
    config = _mock_onprem()
    cost = calculate_onprem_monthly_cost(config)
    hardware = 1200.0 / 36  # ~33.33
    electricity = (100 / 1000) * 8 * 30 * 0.10  # 2.4
    expected = hardware + electricity
    assert abs(cost - expected) < 0.01


def test_onprem_monthly_cost_higher_power():
    config = _mock_onprem()
    config.power_draw_watts = 300.0
    cost = calculate_onprem_monthly_cost(config)
    assert cost > calculate_onprem_monthly_cost(_mock_onprem())
