"""
Rainforest Dashboard — Simple deforestation projection.
No external dependencies beyond numpy.
"""
import numpy as np


def project_deforestation(
    years: list,
    area_km2: list,
    rate_pct: float,
    horizon: int,
) -> list:
    """
    Project annual deforestation forward from the last historical value.

    Args:
        years:     Historical years e.g. [2000, 2001, ..., 2024]
        area_km2:  Annual deforestation matching years
        rate_pct:  Annual change rate in percent (e.g. -10.0 for -10%/year)
        horizon:   Last projection year e.g. 2050

    Returns:
        List of projected km² values for years (last_year+1) to horizon.
        Values are clamped to >= 0.
    """
    if not years or not area_km2:
        return []

    last_year = max(years)
    # Use mean of last 5 years as baseline (more stable than single year)
    recent = [a for y, a in zip(years, area_km2) if y >= last_year - 4]
    baseline = float(np.mean(recent)) if recent else float(area_km2[-1])

    multiplier = 1.0 + rate_pct / 100.0
    projection = []
    value = baseline
    for _ in range(horizon - last_year):
        value = max(0.0, value * multiplier)
        projection.append(round(value, 2))

    return projection


def cumulative_projection(projection: list) -> list:
    """Running cumulative sum of projected values."""
    total = 0.0
    result = []
    for v in projection:
        total += v
        result.append(round(total, 2))
    return result
