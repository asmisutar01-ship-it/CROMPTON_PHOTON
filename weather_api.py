"""
weather_api.py
CROMPTON Solar Monitor - Open-Meteo Weather Integration
No API key required. Uses Open-Meteo Geocoding + Weather APIs.
"""

import os
import socket
import requests

# Optional API key for weather providers (retained for backward compatibility)
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")

# Open-Meteo endpoints (dynamic geocoding and real-time weather)
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL   = "https://api.open-meteo.com/v1/forecast"

# DNS fallback (reuse same approach as supabase_db)
_orig_getaddrinfo = socket.getaddrinfo

def _resilient_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    try:
        return _orig_getaddrinfo(host, port, family, type, proto, flags)
    except socket.gaierror:
        try:
            import dns.resolver
            resolver = dns.resolver.Resolver()
            resolver.nameservers = ["8.8.8.8", "1.1.1.1"]
            answers = resolver.resolve(host, "A")
            ip = answers[0].to_text()
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]
        except Exception:
            raise

socket.getaddrinfo = _resilient_getaddrinfo


# ---------------------------------------------------------------------------
# 1. Geocode a location string → lat/lon
# ---------------------------------------------------------------------------

def geocode_location(location: str) -> dict:
    """
    Convert a location string (e.g. "Pune") to coordinates via Open-Meteo Geocoding API.

    Returns:
        {
            "name":      "Pune",
            "latitude":  18.52,
            "longitude": 73.85,
            "country":   "India",
            "admin1":    "Maharashtra",    # state / region (may be absent)
            "timezone":  "Asia/Kolkata"
        }

    Raises:
        ValueError  – location string is empty
        LookupError – no match found
        RuntimeError – API/network failure
    """
    location = location.strip()
    if not location:
        raise ValueError("Location cannot be empty.")

    try:
        resp = requests.get(
            GEOCODING_URL,
            params={"name": location, "count": 1, "language": "en", "format": "json"},
            timeout=8
        )
        resp.raise_for_status()
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(f"Cannot reach Open-Meteo Geocoding API: {e}") from e
    except requests.exceptions.Timeout:
        raise RuntimeError("Geocoding API timed out. Please try again.")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Geocoding API error: {e}") from e

    data = resp.json()
    results = data.get("results")
    if not results:
        raise LookupError(f"Location not found: '{location}'. Please enter a valid city, town or location.")

    r = results[0]
    return {
        "name":      r.get("name", location),
        "latitude":  round(float(r["latitude"]), 6),
        "longitude": round(float(r["longitude"]), 6),
        "country":   r.get("country", ""),
        "admin1":    r.get("admin1", ""),          # state / province / region
        "timezone":  r.get("timezone", "UTC"),
    }


# ---------------------------------------------------------------------------
# 2. Fetch current weather given lat/lon
# ---------------------------------------------------------------------------

def get_weather(latitude: float, longitude: float) -> dict:
    """
    Retrieve current/hourly weather from Open-Meteo (no API key needed).

    Returns:
        {
            "temperature":     30.5,      # °C
            "humidity":        55,         # %
            "solar_radiation": 720.0,      # W/m²  (shortwave)
            "cloud_cover":     20,         # %
            "rainfall":        0.0,        # mm (last hour)
            "wind_speed":      12.3        # km/h
        }
    """
    params = {
        "latitude":  latitude,
        "longitude": longitude,
        # current-moment variables (Open-Meteo v1 'current' block)
        "current": [
            "temperature_2m",
            "relative_humidity_2m",
            "shortwave_radiation",
            "cloud_cover",
            "precipitation",
            "wind_speed_10m",
        ],
        "hourly": [
            "precipitation",
            "precipitation_probability",
        ],
        "wind_speed_unit": "kmh",
        "timezone": "auto",
        "forecast_days": 2,
    }

    try:
        resp = requests.get(WEATHER_URL, params=params, timeout=10)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(f"Cannot reach Open-Meteo Weather API: {e}") from e
    except requests.exceptions.Timeout:
        raise RuntimeError("Weather API timed out. Please try again.")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Weather API error: {e}") from e

    data    = resp.json()
    current = data.get("current", {})
    hourly  = data.get("hourly", {})
    units   = data.get("current_units", {})

    def _val(key, default=0.0):
        v = current.get(key)
        return v if v is not None else default

    # -----------------------------------------------------------------------
    # Upcoming 24-Hour Precipitation Forecast Analysis
    # -----------------------------------------------------------------------
    times       = hourly.get("time", [])
    precip_list = hourly.get("precipitation", [])
    prob_list   = hourly.get("precipitation_probability", [])

    # Align starting hour with current observation time in location timezone
    cur_time_str = current.get("time", "")
    hour_prefix  = cur_time_str[:13] if cur_time_str else ""

    start_idx = 0
    if hour_prefix and times:
        for idx, t in enumerate(times):
            if t.startswith(hour_prefix) or t >= hour_prefix:
                start_idx = idx
                break

    next_24_precip = precip_list[start_idx : start_idx + 24] if precip_list else []
    next_24_prob   = prob_list[start_idx : start_idx + 24] if prob_list else []

    max_prob   = float(max(next_24_prob)) if next_24_prob else 0.0
    sum_precip = float(sum(next_24_precip)) if next_24_precip else 0.0

    # Rain expected within 24 hours if highest precipitation probability >= 35%
    # or total forecast rainfall over 24h >= 0.5 mm
    rain_expected = bool((max_prob >= 35.0) or (sum_precip >= 0.5))
    rain_probability = round(max_prob, 1)

    # Dynamic rain summary note
    if rain_expected:
        rain_note = f"Rain forecast (~{round(sum_precip, 1)} mm, {int(rain_probability)}% chance)"
    else:
        rain_note = "Clear / No rain forecast in 24h"

    result = {
        "temperature":          round(_val("temperature_2m"), 1),
        "humidity":             round(_val("relative_humidity_2m")),
        "solar_radiation":      round(_val("shortwave_radiation"), 1),
        "cloud_cover":          round(_val("cloud_cover")),
        "rainfall":             round(_val("precipitation"), 2),
        "current_rainfall":     round(_val("precipitation"), 2),
        "rainfall_today_mm":    round(sum_precip, 2),
        "wind_speed":           round(_val("wind_speed_10m"), 1),
        "rain_expected":        rain_expected,
        "rain_probability":     rain_probability,
        "rain_forecast_24h_mm": round(sum_precip, 2),
        "rain_note":            rain_note,
        "_units": {
            "temperature":          units.get("temperature_2m", "°C"),
            "humidity":             units.get("relative_humidity_2m", "%"),
            "solar_radiation":      units.get("shortwave_radiation", "W/m²"),
            "cloud_cover":          units.get("cloud_cover", "%"),
            "rainfall":             units.get("precipitation", "mm"),
            "current_rainfall":     units.get("precipitation", "mm"),
            "rainfall_today_mm":    "mm",
            "wind_speed":           units.get("wind_speed_10m", "km/h"),
            "rain_forecast_24h_mm": "mm",
            "rain_probability":     "%",
        }
    }
    return result


# Module-level cache of the most recently fetched weather
_LAST_WEATHER_CACHE = {}


# ---------------------------------------------------------------------------
# 3. Combined convenience function
# ---------------------------------------------------------------------------

def get_weather_by_location(location: str) -> dict:
    """
    End-to-end: location string → geocode → weather with 24h rain forecast.

    Returns:
        {
            "location": { "name", "latitude", "longitude", "country", "admin1" },
            "weather":  { "temperature", "humidity", "solar_radiation",
                          "cloud_cover", "rainfall", "wind_speed",
                          "rain_expected", "rain_probability", "rain_forecast_24h_mm" }
        }

    Propagates ValueError / LookupError / RuntimeError to the caller.
    """
    global _LAST_WEATHER_CACHE
    geo = geocode_location(location)
    weather = get_weather(geo["latitude"], geo["longitude"])

    output = {
        "location": {
            "name":      geo["name"],
            "latitude":  geo["latitude"],
            "longitude": geo["longitude"],
            "country":   geo["country"],
            "admin1":    geo["admin1"],
        },
        "weather": {k: v for k, v in weather.items() if not k.startswith("_")},
    }
    _LAST_WEATHER_CACHE = output
    return output

