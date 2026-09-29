"""
prediction_engine.py
CROMPTON Solar Monitor - Prediction & ML Engine Adapter
Re-exports and adapts core routines from prediction_model.py.
"""

from prediction_model import (
    predict_clean_power,
    calculate_soiling_loss,
    train_model,
    generate_demo_training_data
)

def calculate_expected_power(irradiance: float, temp_c: float, rated_capacity_w: float = 400.0) -> float:
    """Wrapper using ML model for expected clean power."""
    input_data = {
        "solar_radiation": irradiance,
        "ambient_temperature": temp_c,
        "panel_temperature": temp_c + (irradiance / 1000.0) * 15.0,
        "humidity": 50.0,
        "ldr_value": max(0.0, min(4095.0, irradiance / 1100.0 * 4095.0)),
        "cloud_cover": 15.0,
        "time_of_day": 12.0
    }
    return predict_clean_power(input_data)

def estimate_soiling_loss(actual_power: float, expected_power: float) -> dict:
    """Wrapper calling calculate_soiling_loss."""
    return calculate_soiling_loss(actual_power, expected_power)

def predict_cleaning_schedule(historical_losses: list, weather_forecast: list) -> dict:
    """Provides cleaning advice based on current/recent loss percentage."""
    recent_loss = historical_losses[-1] if historical_losses else 18.0
    return {
        "cleaning_recommended": recent_loss > 15.0,
        "urgency": "High" if recent_loss > 20.0 else ("Medium" if recent_loss > 10.0 else "Low"),
        "reason": f"Observed soiling loss is {recent_loss:.1f}%."
    }
