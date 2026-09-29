import unittest
from unittest.mock import Mock, patch

from prediction_model import FEATURE_ORDER, calculate_soiling_loss
import weather_api


class CleaningDecisionTests(unittest.TestCase):
    def test_actual_power_meets_or_exceeds_expected(self):
        for actual_power in (100.0, 120.0):
            with self.subTest(actual_power=actual_power):
                result = calculate_soiling_loss(actual_power, 100.0)
                self.assertEqual(result["power_loss_w"], 0.0)
                self.assertEqual(result["soiling_loss_percent"], 0.0)
                self.assertEqual(result["cleaning_recommendation"], "NO CLEANING NEEDED")

    def test_meaningful_rain_within_four_hours_defers_cleaning(self):
        result = calculate_soiling_loss(
            50.0,
            100.0,
            rain_expected_next_4h=True,
            rain_probability_next_4h=60.0,
            rain_next_4h_mm=0.8,
            cleaning_cost=1.0,
            expected_operating_hours=8.0,
        )
        self.assertEqual(result["cleaning_recommendation"], "WAIT FOR RAIN")

    def test_positive_net_benefit_advises_cleaning(self):
        result = calculate_soiling_loss(
            50.0,
            100.0,
            rain_expected_next_4h=False,
            cleaning_cost=1.0,
            expected_operating_hours=8.0,
        )
        self.assertEqual(result["estimated_future_savings"], 3.2)
        self.assertEqual(result["net_benefit"], 2.2)
        self.assertEqual(result["cleaning_recommendation"], "CLEANING ADVISED")

    def test_non_positive_net_benefit_does_not_clean(self):
        result = calculate_soiling_loss(
            50.0,
            100.0,
            rain_expected_next_4h=False,
            cleaning_cost=3.2,
            expected_operating_hours=8.0,
        )
        self.assertEqual(result["net_benefit"], 0.0)
        self.assertEqual(result["cleaning_recommendation"], "DO NOT CLEAN")

    def test_model_features_are_environmental_and_include_ldr(self):
        self.assertEqual(len(FEATURE_ORDER), 7)
        self.assertIn("ldr_value", FEATURE_ORDER)
        self.assertNotIn("actual_power", FEATURE_ORDER)
        self.assertNotIn("voltage", FEATURE_ORDER)
        self.assertNotIn("current", FEATURE_ORDER)


class FourHourWeatherTests(unittest.TestCase):
    def test_forecast_after_four_hours_does_not_trigger_four_hour_rain(self):
        probabilities = [0.0] * 24
        precipitation = [0.0] * 24
        probabilities[11] = 10.0
        probabilities[14] = 99.0
        precipitation[14] = 5.0

        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "current": {
                "time": "2026-09-29T10:00",
                "temperature_2m": 25.0,
                "relative_humidity_2m": 50,
                "shortwave_radiation": 500.0,
                "cloud_cover": 10,
                "precipitation": 0.0,
                "wind_speed_10m": 5.0,
            },
            "hourly": {
                "time": [f"2026-09-29T{hour:02}:00" for hour in range(24)],
                "precipitation": precipitation,
                "precipitation_probability": probabilities,
            },
            "current_units": {},
        }

        with patch.object(weather_api.requests, "get", return_value=response):
            result = weather_api.get_weather(1.0, 2.0)

        self.assertFalse(result["rain_expected_next_4h"])
        self.assertEqual(result["rain_next_4h_mm"], 0.0)
        self.assertTrue(result["rain_expected"])


if __name__ == "__main__":
    unittest.main()