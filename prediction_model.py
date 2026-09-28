"""
prediction_model.py
CROMPTON Solar Monitor - Machine Learning Prediction Layer
Uses RandomForestRegressor to predict expected clean solar panel power and compute soiling losses.

NOTE: Model is trained on a synthetic benchmark dataset based on standard photovoltaic physics
relationships (STC: 1000 W/m², 25°C, 400W rated capacity). It is NOT trained on real Crompton plant data.
"""

import os
import logging
from typing import Dict, Any, Tuple, Union
import numpy as np

logger = logging.getLogger("crompton.prediction_model")

# ---------------------------------------------------------------------------
# Model selection: RandomForestRegressor (scikit-learn with fallback)
# ---------------------------------------------------------------------------
try:
    from sklearn.ensemble import RandomForestRegressor as _SklearnRF
    # Test if tree Cython DLLs load successfully under OS Application Control policies
    _test_model = _SklearnRF(n_estimators=1, max_depth=2, random_state=42)
    _dummy_X = np.array([[100, 25, 10, 50, 30, 35, 2]])
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
    "temperature",
    "cloud_cover",
    "humidity",
    "panel_temperature",
    "voltage",
    "current"
]


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
    temperature = np.random.uniform(15.0, 42.0, n_samples)
    cloud_cover = np.random.uniform(0.0, 95.0, n_samples)
    humidity = np.random.uniform(20.0, 90.0, n_samples)

    # Panel temperature: ambient + solar irradiance heating effect
    panel_temperature = temperature + (solar_radiation / 1000.0) * 22.0 + np.random.normal(0, 1.2, n_samples)

    # Clean panel target power (STC 400W reference with thermal derating)
    temp_derate = 1.0 - 0.004 * (panel_temperature - 25.0)
    cloud_attenuation = 1.0 - (cloud_cover / 100.0) * 0.15
    humidity_effect = 1.0 - (humidity / 100.0) * 0.02

    clean_power = 400.0 * (solar_radiation / 1000.0) * temp_derate * cloud_attenuation * humidity_effect
    clean_power = np.maximum(0.0, clean_power) + np.random.normal(0, 1.5, n_samples)
    clean_power = np.maximum(0.0, np.round(clean_power, 2))

    # Clean panel operating voltage & current
    voltage = np.where(solar_radiation > 60.0, np.random.uniform(33.0, 39.5, n_samples), np.random.uniform(10.0, 20.0, n_samples))
    voltage = np.round(voltage, 2)

    current = np.where(voltage > 0, clean_power / voltage, 0.0)
    current = np.maximum(0.0, np.round(current, 2))

    X = np.column_stack([
        solar_radiation,
        temperature,
        cloud_cover,
        humidity,
        panel_temperature,
        voltage,
        current
    ])
    y = clean_power

    return X, y


# ---------------------------------------------------------------------------
# 2. Train model
# ---------------------------------------------------------------------------
def train_model() -> Any:
    """
    Train RandomForestRegressor on synthetic clean-panel data.
    Caches model in module-level _TRAINED_MODEL.
    """
    global _TRAINED_MODEL
    logger.info("Training clean-panel RandomForestRegressor using backend: %s...", MODEL_BACKEND_NAME)
    X, y = generate_demo_training_data()
    model = RandomForestRegressor(n_estimators=50, max_depth=8, random_state=42)
    model.fit(X, y)
    _TRAINED_MODEL = model
    logger.info("RandomForestRegressor trained successfully on %d synthetic samples.", len(y))
    return model


# ---------------------------------------------------------------------------
# 3. Predict clean power
# ---------------------------------------------------------------------------
def predict_clean_power(data: Union[Dict[str, Any], list, np.ndarray]) -> float:
    """
    Predict the expected clean-panel power (in Watts) for given input conditions.

    Input features:
    - solar_radiation (W/m²)
    - temperature (°C)
    - cloud_cover (%)
    - humidity (%)
    - panel_temperature (°C)
    - voltage (V)
    - current (A)

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
            float(data.get("temperature", 30.0) or 30.0),
            float(data.get("cloud_cover", 15.0) or 15.0),
            float(data.get("humidity", 50.0) or 50.0),
            float(data.get("panel_temperature", 42.0) or 42.0),
            float(data.get("voltage", 34.0) or 34.0),
            float(data.get("current", 6.0) or 6.0),
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
    rain_probability: float = 0.0
) -> Dict[str, Any]:
    """
    Calculates soiling metrics from actual power and predicted clean power:
    - actual_power (W)
    - expected_clean_power (W)
    - soiling_loss_percent (%)
    - power_loss_w (W)
    - energy_loss_kwh (daily equivalent over 8 standard operational peak daylight hours)
    - estimated_cost_loss (₹ based on ELECTRICITY_TARIFF in .env)
    - cleaning_status ("NORMAL", "WATCH", "CLEANING ADVISED")
    - rain_expected (bool: precipitation expected within next 24 hours)
    - rain_probability (float: highest rain chance in next 24h %)
    - cleaning_recommendation:
        - Soiling < 5%  → "NO CLEANING NEEDED"
        - Soiling 5–15% → "MONITOR"
        - Soiling > 15%:
            - Rain expected within 24h → "WAIT FOR RAIN"
            - No rain expected         → "CLEANING ADVISED"
    """
    actual_power = max(0.0, round(float(actual_power), 1))
    predicted_clean_power = max(0.0, round(float(predicted_clean_power), 1))

    if predicted_clean_power > 0:
        raw_loss_pct = ((predicted_clean_power - actual_power) / predicted_clean_power) * 100.0
        soiling_loss_percent = round(max(0.0, raw_loss_pct), 1)
    else:
        soiling_loss_percent = 0.0

    power_loss_w = round(max(0.0, predicted_clean_power - actual_power), 1)

    # Daily equivalent energy deficit over ~8 standard daylight peak hours: (power_loss_w * 8h / 1000)
    energy_loss_kwh = round((power_loss_w * 8.0) / 1000.0, 2)

    # Tariff from .env (defaults to 8 if not set or invalid)
    tariff_env = os.getenv("ELECTRICITY_TARIFF", "8").strip()
    try:
        tariff = float(tariff_env)
    except (ValueError, TypeError):
        tariff = 8.0

    estimated_cost_loss = round(energy_loss_kwh * tariff, 2)

    # 1. Base status thresholding
    if soiling_loss_percent < 5.0:
        cleaning_status = "NORMAL"
    elif soiling_loss_percent <= 15.0:
        cleaning_status = "WATCH"
    else:
        cleaning_status = "CLEANING ADVISED"

    # 2. Weather-aware cleaning recommendation logic:
    #    - Soiling < 5%  → "NO CLEANING NEEDED"
    #    - Soiling 5–15% → "MONITOR"
    #    - Soiling > 15%:
    #        - Rain expected within 24h → "WAIT FOR RAIN"
    #        - No rain expected         → "CLEANING ADVISED"
    is_rain = bool(rain_expected)
    if soiling_loss_percent < 5.0:
        cleaning_recommendation = "NO CLEANING NEEDED"
    elif soiling_loss_percent <= 15.0:
        cleaning_recommendation = "MONITOR"
    else:
        if is_rain:
            cleaning_recommendation = "WAIT FOR RAIN"
        else:
            cleaning_recommendation = "CLEANING ADVISED"

    return {
        "actual_power": actual_power,
        "expected_clean_power": predicted_clean_power,
        "soiling_loss_percent": soiling_loss_percent,
        "power_loss_w": power_loss_w,
        "energy_loss_kwh": energy_loss_kwh,
        "estimated_cost_loss": estimated_cost_loss,
        "cleaning_status": cleaning_status,
        "rain_expected": is_rain,
        "rain_probability": round(float(rain_probability or 0.0), 1),
        "cleaning_recommendation": cleaning_recommendation
    }

