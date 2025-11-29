import json
import unittest
from unittest.mock import MagicMock, patch

from weather_agent import tools as weather_tools
from weather_agent.tools import get_current_weather, get_current_weather_summary


class GetCurrentWeatherTests(unittest.TestCase):
    def setUp(self) -> None:  # noqa: D401 - standard unittest hook
        weather_tools._clear_weather_caches()
        self.geocode_payload = {
            "results": [
                {
                    "name": "Seattle",
                    "admin1": "Washington",
                    "country": "United States",
                    "country_code": "US",
                    "latitude": 47.6062,
                    "longitude": -122.3321,
                }
            ]
        }
        self.forecast_payload = {
            "timezone": "America/Los_Angeles",
            "current": {
                "temperature_2m": 18.3,
                "relative_humidity_2m": 42,
                "weather_code": 3,
                "apparent_temperature": 16.8,
                "wind_speed_10m": 5.6,
                "wind_direction_10m": 172,
                "precipitation": 0.0,
            },
        }

    @patch("weather_agent.tools._request_json")
    def test_summary_returns_expected_json(self, mock_request_json: MagicMock) -> None:
        mock_request_json.side_effect = [self.geocode_payload, self.forecast_payload]

        data = get_current_weather_summary("Seattle")

        self.assertNotIn("error", data)
        self.assertEqual(data["location"], "Seattle, Washington, US")
        self.assertEqual(data["temperature"], "18.3°C")
        self.assertEqual(data["feels_like"], "16.8°C")
        self.assertEqual(data["condition"], "Overcast")
        self.assertEqual(data["humidity"], "42%")
        self.assertEqual(data["wind_speed"], "5.6 km/h")
        self.assertEqual(data["wind_direction"], "172°")
        self.assertEqual(data["precipitation"], "0.0 mm")
        self.assertEqual(data["source"], "open-meteo.com")
        self.assertEqual(mock_request_json.call_count, 2)

    @patch("weather_agent.tools._request_json")
    def test_string_wrapper_includes_error_field(self, mock_request_json: MagicMock) -> None:
        mock_request_json.side_effect = ValueError("boom")

        raw = get_current_weather("Seattle")
        data = json.loads(raw)

        self.assertIn("error", data)
        self.assertIn("boom", data["error"])


if __name__ == "__main__":
    unittest.main()
