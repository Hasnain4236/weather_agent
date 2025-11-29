import json
import os
import time
from typing import Any, Dict, Optional, Tuple

import requests

WEATHER_API_BASE_URL = os.getenv("WEATHER_API_BASE_URL", "https://api.open-meteo.com/v1/forecast")
WEATHER_GEOCODE_BASE_URL = os.getenv("WEATHER_GEOCODE_BASE_URL", "https://geocoding-api.open-meteo.com/v1/search")
WEATHER_API_TIMEOUT = float(os.getenv("WEATHER_API_TIMEOUT", "10"))
WEATHER_GEOCODE_CACHE_TTL = float(os.getenv("WEATHER_GEOCODE_CACHE_TTL", "86400"))  # 24 hours
WEATHER_CURRENT_CACHE_TTL = float(os.getenv("WEATHER_CURRENT_CACHE_TTL", "300"))  # 5 minutes

_SESSION = requests.Session()
_GEOCODE_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_CURRENT_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}

WEATHER_CODE_MAP = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def _format_measurement(value: Optional[float], unit: str, decimals: int = 1) -> str:
    if value is None:
        return "N/A"
    rounded = round(value, decimals)
    if decimals == 0:
        rounded = int(rounded)
    return f"{rounded}{unit}"


def _cache_get(cache: Dict[str, Tuple[float, Dict[str, Any]]], key: str, ttl: float) -> Optional[Dict[str, Any]]:
    if ttl <= 0:
        return None
    entry = cache.get(key)
    if not entry:
        return None
    expires_at, value = entry
    if expires_at < time.time():
        cache.pop(key, None)
        return None
    return value


def _cache_set(cache: Dict[str, Tuple[float, Dict[str, Any]]], key: str, value: Dict[str, Any], ttl: float) -> None:
    if ttl <= 0:
        return
    cache[key] = (time.time() + ttl, value)


def _clear_weather_caches() -> None:
    """Utility hook (mainly for tests) to reset cache state."""

    _GEOCODE_CACHE.clear()
    _CURRENT_CACHE.clear()


def _request_json(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    response = _SESSION.get(url, params=params, timeout=WEATHER_API_TIMEOUT)
    response.raise_for_status()
    return response.json()


def _geocode_location(location: str) -> Dict[str, Any]:
    cache_key = location.strip().lower()
    cached = _cache_get(_GEOCODE_CACHE, cache_key, WEATHER_GEOCODE_CACHE_TTL)
    if cached:
        return cached

    params = {
        "name": location,
        "count": 1,
        "language": "en",
        "format": "json",
    }
    payload = _request_json(WEATHER_GEOCODE_BASE_URL, params)
    results = payload.get("results") or []
    if not results:
        raise ValueError(f"Unable to resolve location '{location}'.")

    result = results[0]
    _cache_set(_GEOCODE_CACHE, cache_key, result, WEATHER_GEOCODE_CACHE_TTL)
    return result


def _fetch_current_weather(latitude: float, longitude: float) -> Dict[str, Any]:
    coord_key = f"{latitude:.4f},{longitude:.4f}"
    cached = _cache_get(_CURRENT_CACHE, coord_key, WEATHER_CURRENT_CACHE_TTL)
    if cached:
        return cached

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,wind_direction_10m,precipitation",
        "timezone": "auto",
    }
    payload = _request_json(WEATHER_API_BASE_URL, params)
    current = payload.get("current")
    if not current:
        raise ValueError("Open-Meteo response did not include 'current' data.")

    result = {"current": current, "timezone": payload.get("timezone")}
    _cache_set(_CURRENT_CACHE, coord_key, result, WEATHER_CURRENT_CACHE_TTL)
    return result


def _format_location(result: Dict[str, Any]) -> str:
    parts = [result.get("name")]
    admin1 = result.get("admin1")
    country = result.get("country_code") or result.get("country")
    if admin1:
        parts.append(admin1)
    if country:
        parts.append(country)
    return ", ".join([part for part in parts if part])


def _describe_weather_code(code: Any) -> str:
    try:
        numeric = int(code)
    except (TypeError, ValueError):
        return "Unknown conditions"
    return WEATHER_CODE_MAP.get(numeric, f"Weather code {numeric}")


def _build_summary(preferred_location: str, resolved_name: str, current: Dict[str, Any], timezone: Optional[str]) -> Dict[str, str]:
    temperature = current.get("temperature_2m")
    humidity = current.get("relative_humidity_2m")
    apparent = current.get("apparent_temperature")
    wind_speed = current.get("wind_speed_10m")
    wind_dir = current.get("wind_direction_10m")
    precipitation = current.get("precipitation")

    return {
        "location": resolved_name or preferred_location,
        "query": preferred_location,
        "temperature": _format_measurement(temperature, "°C"),
        "feels_like": _format_measurement(apparent, "°C"),
        "humidity": _format_measurement(float(humidity) if humidity is not None else None, "%", 0),
        "condition": _describe_weather_code(current.get("weather_code")),
        "wind_speed": _format_measurement(wind_speed, " km/h"),
        "wind_direction": _format_measurement(wind_dir, "°", 0),
        "precipitation": _format_measurement(precipitation, " mm"),
        "timezone": timezone or "auto",
        "source": "open-meteo.com",
    }

def get_current_weather_summary(location: str) -> Dict[str, Any]:
    """Return the structured summary dict for a location."""

    preferred_location = location.strip() or "auto:ip"
    geocode = _geocode_location(preferred_location)
    weather = _fetch_current_weather(geocode["latitude"], geocode["longitude"])

    current = weather["current"]
    resolved_name = _format_location(geocode)
    return _build_summary(preferred_location, resolved_name, current, weather.get("timezone"))


def get_current_weather(location: str) -> str:
    """Convenience wrapper that returns a JSON string (for backwards compatibility)."""

    try:
        summary = get_current_weather_summary(location)
        return json.dumps(summary, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        return json.dumps({"error": str(e)})
