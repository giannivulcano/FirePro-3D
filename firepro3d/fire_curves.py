"""
Standard fire time-temperature curves for thermal radiation analysis.

All functions return temperature in Kelvin.
"""

from __future__ import annotations

import math


def can_ulc_s101(time_minutes: float, ambient_c: float = 20.0) -> float:
    """CAN/ULC-S101 standard time-temperature curve.

    T(t) = 750 * (1 - exp(-3.79553 * sqrt(t_h))) + 170.41 * sqrt(t_h) + T_ambient

    Parameters
    ----------
    time_minutes : float
        Fire duration in minutes (must be > 0).
    ambient_c : float
        Ambient temperature in Celsius (default 20).

    Returns
    -------
    float
        Surface temperature in Kelvin.
    """
    if time_minutes <= 0:
        return ambient_c + 273.15
    t_hours = time_minutes / 60.0
    sqrt_t = math.sqrt(t_hours)
    temp_c = 750.0 * (1.0 - math.exp(-3.79553 * sqrt_t)) + 170.41 * sqrt_t + ambient_c
    return temp_c + 273.15


def iso_834(time_minutes: float, ambient_c: float = 20.0) -> float:
    """ISO 834 / ASTM E119 standard fire curve.

    T(t) = 345 * log10(8*t + 1) + T_ambient   (t in minutes)

    Parameters
    ----------
    time_minutes : float
        Fire duration in minutes (must be > 0).
    ambient_c : float
        Ambient temperature in Celsius (default 20).

    Returns
    -------
    float
        Surface temperature in Kelvin.
    """
    if time_minutes <= 0:
        return ambient_c + 273.15
    temp_c = 345.0 * math.log10(8.0 * time_minutes + 1.0) + ambient_c
    return temp_c + 273.15


def constant_temperature(temp_celsius: float) -> float:
    """Convert a constant temperature from Celsius to Kelvin.

    Parameters
    ----------
    temp_celsius : float
        Temperature in Celsius.

    Returns
    -------
    float
        Temperature in Kelvin.
    """
    return temp_celsius + 273.15
