import unittest
from unittest.mock import Mock, patch

from prediction_model import FEATURE_ORDER, calculate_soiling_loss
import weather_api


class CleaningDecisionTests(unittest.TestCase):
    def test_actual_power_meets_or_exceeds_expected(self):
        # Slightly above or equal (< 0.5 mW tolerance) results in NO CLEANING NEEDED
        for actual_power in (12.0, 12.3):
            with self.subTest(actual_power=actual_power):
                result = calculate_soiling_loss(actual_power, 12.0)
                self.assertEqual(result["power_loss_mw"], 0.0)
                self.assertEqual(result["soiling_loss_percent"], 0.0)
                self.assertEqual(result["cleaning_recommendation"], "NO CLEANING NEEDED")

    def test_actual_power_exceeds_expected_triggers_mismatch_warning(self):
        # Significant excess (> 0.5 mW) triggers MODEL/IRRADIANCE MISMATCH diagnostic warning
        result = calculate_soiling_loss(15.0, 12.0)
        self.assertEqual(result["power_loss_mw"], 0.0)
        self.assertEqual(result["cleaning_recommendation"], "MODEL/IRRADIANCE MISMATCH")
        self.assertEqual(result["cleaning_status"], "WARNING")
        self.assertTrue(result["power_mismatch"])
        self.assertIsNotNone(result["diagnostic_warning"])

    def test_meaningful_rain_within_four_hours_defers_cleaning(self):
        result = calculate_soiling_loss(
            6.0,
            12.0,
            rain_expected_next_4h=True,
            rain_probability_next_4h=60.0,
            rain_next_4h_mm=0.8,
            cleaning_cost=0.0001,
            expected_operating_hours=8.0,
        )
        self.assertEqual(result["cleaning_recommendation"], "WAIT FOR RAIN")

    def test_positive_net_benefit_advises_cleaning(self):
        # 6.0 mW loss * 8h = 48 mWh = 0.000048 kWh
        # 0.000048 kWh * 8.0 INR/kWh = 0.000384 INR -> rounded to 4 decimals = 0.0004
        result = calculate_soiling_loss(
            6.0,
            12.0,
            rain_expected_next_4h=False,
            cleaning_cost=0.0001,
            expected_operating_hours=8.0,
        )
        self.assertAlmostEqual(result["estimated_future_savings"], 0.0004, places=4)
        self.assertGreater(result["net_benefit"], 0.0)
        self.assertEqual(result["cleaning_recommendation"], "CLEANING ADVISED")

    def test_non_positive_net_benefit_does_not_clean(self):
        result = calculate_soiling_loss(
            6.0,
            12.0,
            rain_expected_next_4h=False,
            cleaning_cost=0.0004,
            expected_operating_hours=8.0,
        )
        self.assertLessEqual(result["net_benefit"], 0.0)
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


class LDRCalibrationTests(unittest.TestCase):
    def test_ldr_to_irradiance_calibration(self):
        from prediction_model import ldr_to_irradiance
        self.assertEqual(ldr_to_irradiance(0.0), 0.0)
        self.assertAlmostEqual(ldr_to_irradiance(4095.0), 1000.0, delta=1.0)
        self.assertAlmostEqual(ldr_to_irradiance(2047.5), 500.0, delta=2.0)

    def test_cross_check_irradiance_fallback(self):
        from prediction_model import cross_check_irradiance
        res = cross_check_irradiance(None, 2047.5)
        self.assertEqual(res["source"], "LDR_CALIBRATED")
        self.assertAlmostEqual(res["resolved_irradiance"], 500.0, delta=2.0)
        self.assertFalse(res["mismatch_detected"])

    def test_cross_check_irradiance_mismatch_flag(self):
        from prediction_model import cross_check_irradiance
        # Weather says 900 W/m², but LDR indicates 200 W/m² (gap 700 > 150)
        res = cross_check_irradiance(900.0, 819.0)
        self.assertEqual(res["source"], "WEATHER_API_FLAGGED")
        self.assertTrue(res["mismatch_detected"])
        self.assertGreater(res["discrepancy"], 150.0)


if __name__ == "__main__":
    unittest.main()