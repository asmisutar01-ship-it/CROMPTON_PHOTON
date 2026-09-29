"""
prediction_model.py
CROMPTON Solar Monitor - Machine Learning Prediction Layer
Uses RandomForestRegressor to predict expected clean solar panel power and compute soiling losses.

NOTE: Model is trained on a synthetic benchmark dataset based on standard photovoltaic physics
relationships (STC: 1000 W/m², 25°C, 400W rated capacity). It is NOT trained on real Crompton plant data.
"""

import os
import csv
import logging
from typing import Dict, Any, Tuple, Union, Optional
import numpy as np

logger = logging.getLogger("crompton.prediction_model")

# ---------------------------------------------------------------------------
# Model selection: RandomForestRegressor (scikit-learn with fallback)
# ---------------------------------------------------------------------------
try:
    from sklearn.ensemble import RandomForestRegressor as _SklearnRF
    # Test if tree Cython DLLs load successfully under OS Application Control policies
    _test_model = _SklearnRF(n_estimators=1, max_depth=2, random_state=42)
    _dummy_X = np.array([[100, 10, 25, 35, 50, 2800, 12]])
    _dummy_y = np.array([50.0])
    _test_model.fit(_dummy_X, _dummy_y)
    RandomForestRegressor = _SklearnRF
    MODEL_BACKEND_NAME = "scikit-learn RandomForestRegressor"
except Exception as _e:
    # If Windows Application Control policy blocks compiled _quad_tree.pyd,
    # use pure-Python/NumPy RandomForestRegressor ensemble with identical API.
    class _SimpleDecisionTree:
        def __init__(self, max_depth=7, min_samples_split=4, max_features=None):
            self.max_depth = max_depth
            self.min_samples_split = min_samples_split
            self.max_features = max_features
            self.tree = None

        def fit(self, X, y, depth=0):
            n_samples, n_features = X.shape
            if depth >= self.max_depth or n_samples < self.min_samples_split or np.var(y) < 1e-4:
                return float(np.mean(y))

            k = self.max_features or max(1, int(np.sqrt(n_features)) + 1)
            feat_idxs = np.random.choice(n_features, min(k, n_features), replace=False)
            best_feat, best_thresh, best_score = None, None, float("inf")

            for f in feat_idxs:
                col = X[:, f]
                vals = np.unique(col)
                if len(vals) > 12:
                    vals = np.percentile(vals, np.linspace(10, 90, 10))
                for thresh in vals:
                    left_mask = col <= thresh
                    right_mask = ~left_mask
                    n_l, n_r = np.sum(left_mask), np.sum(right_mask)
                    if n_l == 0 or n_r == 0:
                        continue
                    score = np.var(y[left_mask]) * n_l + np.var(y[right_mask]) * n_r
                    if score < best_score:
                        best_score, best_feat, best_thresh = score, f, thresh

            if best_feat is None:
                return float(np.mean(y))

            left_mask = X[:, best_feat] <= best_thresh
            left_node = self.fit(X[left_mask], y[left_mask], depth + 1)
            right_node = self.fit(X[~left_mask], y[~left_mask], depth + 1)
            return (best_feat, best_thresh, left_node, right_node)

        def _predict_one(self, node, x):
            if not isinstance(node, tuple):
                return float(node)
            feat, thresh, left, right = node
            return self._predict_one(left if x[feat] <= thresh else right, x)

        def predict(self, X):
            return np.array([self._predict_one(self.tree, row) for row in X])

    class _FallbackRandomForestRegressor:
        def __init__(self, n_estimators=40, max_depth=7, random_state=42):
            self.n_estimators = n_estimators
            self.max_depth = max_depth
            self.random_state = random_state
            self.trees = []

        def fit(self, X, y):
            np.random.seed(self.random_state)
            n_samples, n_features = X.shape
            self.trees = []
            for _ in range(self.n_estimators):
                bootstrap_idx = np.random.choice(n_samples, n_samples, replace=True)
                tree = _SimpleDecisionTree(
                    max_depth=self.max_depth,
                    max_features=max(1, int(np.sqrt(n_features)) + 1)
                )
                tree.tree = tree.fit(X[bootstrap_idx], y[bootstrap_idx])
                self.trees.append(tree)
            return self

        def predict(self, X):
            if not self.trees:
                raise RuntimeError("Model is not fitted yet.")
            preds = np.array([t.predict(X) for t in self.trees])
            return np.mean(preds, axis=0)

    RandomForestRegressor = _FallbackRandomForestRegressor
    MODEL_BACKEND_NAME = "NumPy RandomForestRegressor (Pure Python Fallback)"

# Global trained model instance
_TRAINED_MODEL = None

FEATURE_ORDER = [
    "solar_radiation",
    "cloud_cover",
    "ambient_temperature",
    "panel_temperature",
    "humidity",
    "ldr_value",
    "time_of_day"
]
TARGET_COLUMN = "clean_power"
MODEL_VERSION = "rf-clean-power-v3"
_MODEL_METRICS = {}
_TRAINING_DATA_SOURCE = ""


# ---------------------------------------------------------------------------
# 1. Synthetic training data generator
# ---------------------------------------------------------------------------
def generate_demo_training_data(n_samples: int = 500, seed: int = 42) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate synthetic clean-panel training data based on standard photovoltaic physics.
    Simulates a 400W Crompton monocrystalline panel under standard test conditions (STC):
    - 1000 W/m² irradiance, 25°C panel temperature
    - Temperature coefficient ~ -0.4% / °C
    - Cloud attenuation factor

    NOTE: This synthetic benchmark is for demonstration and immediate training only.
    It is NOT trained on real Crompton plant data.
    """
    np.random.seed(seed)

    # Environmental features
    solar_radiation = np.random.uniform(50.0, 1100.0, n_samples)
    ambient_temperature = np.random.uniform(15.0, 42.0, n_samples)
    cloud_cover = np.random.uniform(0.0, 95.0, n_samples)
    humidity = np.random.uniform(20.0, 90.0, n_samples)
    ldr_value = np.clip((solar_radiation / 1100.0) * 4095.0 + np.random.normal(0, 120, n_samples), 0, 4095)
    time_of_day = np.random.uniform(6.0, 18.0, n_samples)

    # Panel temperature: ambient + solar irradiance heating effect
    panel_temperature = ambient_temperature + (solar_radiation / 1000.0) * 22.0 + np.random.normal(0, 1.2, n_samples)

    # Clean panel target power (STC 400W reference with thermal derating)
    temp_derate = 1.0 - 0.004 * (panel_temperature - 25.0)
    cloud_attenuation = 1.0 - (cloud_cover / 100.0) * 0.15
    humidity_effect = 1.0 - (humidity / 100.0) * 0.02

    clean_power = 400.0 * (solar_radiation / 1000.0) * temp_derate * cloud_attenuation * humidity_effect
    clean_power = np.maximum(0.0, clean_power) + np.random.normal(0, 1.5, n_samples)
    clean_power = np.maximum(0.0, np.round(clean_power, 2))

    X = np.column_stack([
        solar_radiation,
        cloud_cover,
        ambient_temperature,
        panel_temperature,
        humidity,
        ldr_value,
        time_of_day,
    ])
    y = clean_power

    return X, y


def load_training_data(source_path: Optional[str] = None) -> Tuple[np.ndarray, np.ndarray]:
    """Load a CSV with FEATURE_ORDER plus clean_power, or synthetic prototype data."""
    global _TRAINING_DATA_SOURCE
    source_path = source_path or os.getenv("CLEAN_PANEL_TRAINING_DATA")
    if not source_path:
        _TRAINING_DATA_SOURCE = "synthetic_prototype_fallback"
        logger.warning(
            "Using synthetic prototype training data; model accuracy is not production-validated."
        )
        return generate_demo_training_data()

    rows = []
    with open(source_path, "r", newline="", encoding="utf-8-sig") as training_file:
        reader = csv.DictReader(training_file)
        required_columns = FEATURE_ORDER + [TARGET_COLUMN]
        missing_columns = [name for name in required_columns if name not in (reader.fieldnames or [])]
        if missing_columns:
            raise ValueError(f"Training CSV is missing columns: {', '.join(missing_columns)}")
        for row in reader:
            rows.append([float(row[name]) for name in required_columns])

    if len(rows) < 5:
        raise ValueError("Training CSV must contain at least 5 valid data rows.")
    values = np.asarray(rows, dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Training CSV contains non-finite values.")
    _TRAINING_DATA_SOURCE = "historical_csv"
    return values[:, :-1], values[:, -1]


# ---------------------------------------------------------------------------
# 2. Train model
# ---------------------------------------------------------------------------
def train_model(training_data_path: Optional[str] = None) -> Any:
    """
    Train RandomForestRegressor on synthetic clean-panel data.
    Caches model in module-level _TRAINED_MODEL.
    """
    global _TRAINED_MODEL, _MODEL_METRICS
    logger.info("Training clean-panel RandomForestRegressor using backend: %s...", MODEL_BACKEND_NAME)
    X, y = load_training_data(training_data_path)
    rng = np.random.RandomState(42)
    indices = rng.permutation(len(y))
    test_size = max(1, int(round(len(y) * 0.2)))
    test_indices, train_indices = indices[:test_size], indices[test_size:]
    model = RandomForestRegressor(n_estimators=50, max_depth=8, random_state=42)
    model.fit(X[train_indices], y[train_indices])
    predictions = np.asarray(model.predict(X[test_indices]), dtype=float)
    actuals = y[test_indices]
    errors = predictions - actuals
    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(errors ** 2)))
    residual_sum = float(np.sum(errors ** 2))
    total_sum = float(np.sum((actuals - np.mean(actuals)) ** 2))
    r_squared = 1.0 - residual_sum / total_sum if total_sum > 0 else 0.0

    model.fit(X, y)
    _TRAINED_MODEL = model
    _MODEL_METRICS = {
        "mae": round(mae, 3),
        "rmse": round(rmse, 3),
        "r2": round(r_squared, 4),
        "training_samples": int(len(train_indices)),
        "evaluation_samples": int(len(test_indices)),
        "data_source": _TRAINING_DATA_SOURCE,
        "prototype_data": _TRAINING_DATA_SOURCE == "synthetic_prototype_fallback"
    }
    logger.info("RandomForest holdout metrics: %s", _MODEL_METRICS)
    return model


def get_model_metrics() -> Dict[str, Any]:
    """Return the latest holdout evaluation metrics and training data provenance."""
    return dict(_MODEL_METRICS)


# ---------------------------------------------------------------------------
# 3. Predict clean power
# ---------------------------------------------------------------------------
def predict_clean_power(data: Union[Dict[str, Any], list, np.ndarray]) -> float:
    """
    Predict the expected clean-panel power (in Watts) for given input conditions.

    Input features:
    - solar_radiation (W/m²)
    - cloud_cover (%)
    - ambient_temperature (°C)
    - panel_temperature (°C)
    - humidity (%)
    - ldr_value (raw ESP32 LDR/light reading)
    - time_of_day (hour, 0-24)

    Returns:
        float: Expected clean power in Watts (rounded to 1 decimal place, >= 0.0).
    """
    global _TRAINED_MODEL
    if _TRAINED_MODEL is None:
        train_model()

    if isinstance(data, dict):
        # Extract features in expected order with realistic fallback defaults
        features = [
            float(data.get("solar_radiation", 785.0) or 785.0),
            float(data.get("cloud_cover", 15.0) or 15.0),
            float(data.get("ambient_temperature", data.get("temperature", 30.0)) or 30.0),
            float(data.get("panel_temperature", 42.0) or 42.0),
            float(data.get("humidity", 50.0) or 50.0),
            float(data.get("ldr_value", data.get("ldr", 2900.0)) or 2900.0),
            float(data.get("time_of_day", 12.0) or 12.0),
        ]
        X = np.array([features])
    elif isinstance(data, (list, tuple)):
        X = np.array([data], dtype=float)
    elif isinstance(data, np.ndarray):
        X = data if data.ndim == 2 else data.reshape(1, -1)
    else:
        raise ValueError(f"Unsupported data format for prediction: {type(data)}")

    try:
        prediction = _TRAINED_MODEL.predict(X)
        pred_val = float(prediction[0])
        return max(0.0, round(pred_val, 1))
    except Exception as e:
        logger.error("Error during clean power prediction: %s", e)
        raise RuntimeError(f"Prediction failed: {e}") from e


# ---------------------------------------------------------------------------
# 4. Calculate soiling loss & financial impact
# ---------------------------------------------------------------------------
def calculate_soiling_loss(
    actual_power: float,
    predicted_clean_power: float,
    rain_expected: bool = False,
    rain_probability: float = 0.0,
    rain_expected_next_4h: Optional[bool] = None,
    rain_probability_next_4h: Optional[float] = None,
    rain_next_4h_mm: float = 0.0,
    cloud_cover: Optional[float] = None,
    cleaning_cost: Optional[float] = None,
    expected_operating_hours: Optional[float] = None
) -> Dict[str, Any]:
    """
    Compare measured and expected clean power, then evaluate automated cleaning
    economics after checking precipitation expected in the next four hours.
    """
    actual_power = max(0.0, round(float(actual_power), 1))
    predicted_clean_power = max(0.0, round(float(predicted_clean_power), 1))
    power_loss_w = round(max(0.0, predicted_clean_power - actual_power), 1)
    soiling_loss_percent = round(
        max(0.0, (power_loss_w / predicted_clean_power) * 100.0)
        if predicted_clean_power > 0 else 0.0,
        1
    )

    def env_float(name: str, default: float) -> float:
        try:
            return float(os.getenv(name, str(default)))
        except (TypeError, ValueError):
            logger.warning("Invalid %s value; using default %s.", name, default)
            return default

    tariff = env_float("ELECTRICITY_TARIFF", 8.0)
    cleaning_cost_value = max(0.0, float(
        cleaning_cost if cleaning_cost is not None else env_float("CLEANING_COST", 5.0)
    ))
    operating_hours = max(0.0, float(
        expected_operating_hours if expected_operating_hours is not None
        else env_float("EXPECTED_OPERATING_HOURS", 8.0)
    ))
    recoverable_energy_kwh = round((power_loss_w * operating_hours) / 1000.0, 4)
    estimated_future_savings = round(recoverable_energy_kwh * tariff, 2)
    net_benefit = round(estimated_future_savings - cleaning_cost_value, 2)
    rain_probability_4h = float(
        rain_probability_next_4h if rain_probability_next_4h is not None else rain_probability
    )
    rain_amount_4h = max(0.0, float(rain_next_4h_mm or 0.0))
    if rain_expected_next_4h is None:
        is_rain_next_4h = (
            rain_probability_4h >= env_float("RAIN_PROBABILITY_THRESHOLD", 35.0)
            or rain_amount_4h >= env_float("RAIN_PRECIPITATION_THRESHOLD_MM", 0.5)
        )
    else:
        is_rain_next_4h = bool(rain_expected_next_4h)

    if power_loss_w <= 0:
        cleaning_status = "NORMAL"
        cleaning_recommendation = "NO CLEANING NEEDED"
    elif is_rain_next_4h:
        cleaning_status = "WATCH"
        cleaning_recommendation = "WAIT FOR RAIN"
    elif net_benefit > 0:
        cleaning_status = "CLEANING ADVISED"
        cleaning_recommendation = "CLEANING ADVISED"
    else:
        cleaning_status = "NORMAL"
        cleaning_recommendation = "DO NOT CLEAN"

    return {
        "actual_power": actual_power,
        "actual_power_w": actual_power,
        "expected_clean_power": predicted_clean_power,
        "power_loss_w": power_loss_w,
        "soiling_loss_percent": soiling_loss_percent,
        "energy_loss_kwh": recoverable_energy_kwh,
        "recoverable_energy_kwh": recoverable_energy_kwh,
        "estimated_cost_loss": estimated_future_savings,
        "estimated_future_savings": estimated_future_savings,
        "cleaning_cost": round(cleaning_cost_value, 2),
        "net_benefit": net_benefit,
        "cleaning_status": cleaning_status,
        "rain_expected": is_rain_next_4h,
        "rain_expected_next_4h": is_rain_next_4h,
        "rain_probability": round(rain_probability_4h, 1),
        "rain_probability_next_4h": round(rain_probability_4h, 1),
        "rain_next_4h_mm": round(rain_amount_4h, 2),
        "cloud_cover": round(float(cloud_cover), 1) if cloud_cover is not None else None,
        "cleaning_recommendation": cleaning_recommendation,
        "model_version": MODEL_VERSION
    }

