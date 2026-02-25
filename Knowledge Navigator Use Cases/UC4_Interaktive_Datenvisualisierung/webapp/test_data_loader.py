"""
Unit tests for data_loader.py.
These tests mock the HTTP calls so no live Supabase connection is needed.
"""
import pandas as pd
from unittest.mock import patch, MagicMock
import sys
import os

# Ensure webapp directory is on path
sys.path.insert(0, os.path.dirname(__file__))


def _mock_response(data: list) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = data
    mock.raise_for_status.return_value = None
    return mock


MOCK_STATES = [
    {"state_id": 1, "state_code": "PA", "state_name": "Pará", "region": "Norte"},
    {"state_id": 2, "state_code": "AM", "state_name": "Amazonas", "region": "Norte"},
]
MOCK_CLASSES = [
    {"class_id": 1, "class_name": "Desmatamento"},
]
MOCK_FACTS = [
    {"id": 1, "year": 2022, "state_id": 1, "class_id": 1, "area_km2": "1200.50", "accumulated_km2": "10000.00"},
    {"id": 2, "year": 2023, "state_id": 1, "class_id": 1, "area_km2": "1100.00", "accumulated_km2": "11100.00"},
    {"id": 3, "year": 2023, "state_id": 2, "class_id": 1, "area_km2": "800.25",  "accumulated_km2": "8000.00"},
]


def test_load_deforestation_data_columns():
    """load_deforestation_data() must return df with required columns."""
    import data_loader
    data_loader.clear_cache()

    with patch("data_loader.requests.get") as mock_get:
        def side_effect(url, **kwargs):
            if "dim_state" in url:
                return _mock_response(MOCK_STATES)
            if "dim_class" in url:
                return _mock_response(MOCK_CLASSES)
            return _mock_response(MOCK_FACTS)
        mock_get.side_effect = side_effect

        df = data_loader.load_deforestation_data()

    assert isinstance(df, pd.DataFrame), "Must return DataFrame"
    for col in ["year", "state_name", "class_name", "area_km2", "accumulated_km2"]:
        assert col in df.columns, f"Missing column: {col}"
    assert df["year"].dtype == int
    assert df["area_km2"].dtype == float
    print(f"✓ test_load_deforestation_data_columns passed ({len(df)} rows)")


def test_get_years():
    """get_years() must return sorted list of ints."""
    import data_loader
    data_loader.clear_cache()

    with patch("data_loader.requests.get") as mock_get:
        def side_effect(url, **kwargs):
            if "dim_state" in url:
                return _mock_response(MOCK_STATES)
            if "dim_class" in url:
                return _mock_response(MOCK_CLASSES)
            return _mock_response(MOCK_FACTS)
        mock_get.side_effect = side_effect

        years = data_loader.get_years()

    assert years == sorted(years), "Years must be sorted"
    assert all(isinstance(y, int) for y in years), "Years must be ints"
    assert 2022 in years and 2023 in years
    print(f"✓ test_get_years passed: {years}")


def test_get_states():
    """get_states() must return sorted list of strings."""
    import data_loader
    data_loader.clear_cache()

    with patch("data_loader.requests.get") as mock_get:
        def side_effect(url, **kwargs):
            if "dim_state" in url:
                return _mock_response(MOCK_STATES)
            if "dim_class" in url:
                return _mock_response(MOCK_CLASSES)
            return _mock_response(MOCK_FACTS)
        mock_get.side_effect = side_effect

        states = data_loader.get_states()

    assert "Pará" in states
    assert "Amazonas" in states
    assert states == sorted(states)
    print(f"✓ test_get_states passed: {states}")


def test_projection_zero_rate():
    """0% rate should keep baseline constant."""
    from simulation import project_deforestation
    years = list(range(2015, 2025))
    areas = [1000.0] * 10
    result = project_deforestation(years, areas, rate_pct=0.0, horizon=2030)
    assert len(result) == 6, f"Expected 6 values, got {len(result)}"
    assert abs(result[0] - 1000.0) < 1.0, f"0% should keep ~1000, got {result[0]}"
    print(f"✓ test_projection_zero_rate passed")


def test_projection_decline():
    """Negative rate should produce declining values."""
    from simulation import project_deforestation
    years = list(range(2015, 2025))
    areas = [1000.0] * 10
    result = project_deforestation(years, areas, rate_pct=-10.0, horizon=2027)
    assert len(result) == 3
    assert result[0] < 1000.0, "Should decline from baseline"
    assert result[1] < result[0], "Should decline each year"
    print(f"✓ test_projection_decline passed: {result}")


if __name__ == "__main__":
    test_load_deforestation_data_columns()
    test_get_years()
    test_get_states()
    test_projection_zero_rate()
    test_projection_decline()
    print("\n✅ All tests passed")
