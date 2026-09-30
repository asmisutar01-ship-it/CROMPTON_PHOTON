"""
prediction_model.py
CROMPTON Solar Monitor - Machine Learning Prediction Layer
Uses RandomForestRegressor to predict expected clean solar panel power and compute soiling losses.

PROTOTYPE PANEL SPECIFICATIONS (calibrated):
  - Maximum voltage:  6 V
  - Maximum current:  4 mA
  - Maximum power:    6 × 0.004 = 0.024 W = 24 mW

All power values in this module are in milliwatts (mW).
actual_power_mW              = voltage_V × current_mA
expected_clean_power_mW      bounded: 0 ≤ value ≤ 24 mW
power_loss_mW                = max(0, expected_clean_power_mW - actual_power_mW)
soiling_loss_percent         = (power_loss_mW / expected_clean_power_mW) × 100
"""

import os
import csv
import logging
from typing import Dict, Any, Tuple, Union, Optional
import numpy as np

logger = logging.getLogger("crompton.prediction_model")

# ---------------------------------------------------------------------------
# Panel physical constants (3W solar panel)
# ---------------------------------------------------------------------------
PANEL_MAX_VOLTAGE_V  = float(os.getenv("PANEL_MAX_VOLTAGE_V", "6.0"))      # Maximum panel voltage (V)
PANEL_MAX_CURRENT_MA = float(os.getenv("PANEL_MAX_CURRENT_MA", "500.0"))   # Maximum panel current (mA) - 6V × 500mA = 3000 mW = 3W
PANEL_MAX_POWER_W    = float(os.getenv("PANEL_MAX_POWER_W", "3.0"))        # Maximum panel power (W)
PANEL_MAX_POWER_MW   = float(os.getenv("PANEL_MAX_POWER_MW", "3000.0"))    # Maximum panel power (mW: 3W = 3000 mW)

# ---------------------------------------------------------------------------
# ESP32 LDR -> Irradiance Calibration Constants & Configuration
# Model: Irradiance (W/m²) = LDR_SCALE * ((ldr_raw - LDR_OFFSET) / (LDR_MAX - LDR_OFFSET)) ^ LDR_GAMMA
# Can be adjusted via environment variables or updated directly after hardware calibration.
# ---------------------------------------------------------------------------
LDR_RAW_MIN      = float(os.getenv("LDR_RAW_MIN", "0.0"))         # Minimum ADC reading in dark
LDR_RAW_MAX      = float(os.getenv("LDR_RAW_MAX", "4095.0"))      # Maximum ADC reading in full sun (12-bit ESP32)
LDR_MAX_IRRAD    = float(os.getenv("LDR_MAX_IRRAD", "1000.0"))    # Irradiance at maximum LDR reading (W/m²)
LDR_GAMMA        = float(os.getenv("LDR_GAMMA", "1.0"))           # Nonlinearity exponent (1.0 = linear response)
IRRAD_MISMATCH_THRESHOLD = float(os.getenv("IRRAD_MISMATCH_THRESHOLD", "150.0")) # W/m² discrepancy threshold


def ldr_to_irradiance(
    ldr_raw: float,
    raw_min: float = LDR_RAW_MIN,
    raw_max: float = LDR_RAW_MAX,
    max_irrad: float = LDR_MAX_IRRAD,
    gamma: float = LDR_GAMMA
) -> float:
    """
    Calibrate ESP32 LDR analog ADC value (0-4095) into solar irradiance (W/m²).
    Configurable for real ESP32 bench calibration.
    """
    try:
        val = float(ldr_raw)
    except (TypeError, ValueError):
        val = 0.0

    # Normalization with span clamping
    span = max(1.0, raw_max - raw_min)
    norm = max(0.0, min(1.0, (val - raw_min) / span))
    if gamma != 1.0 and norm > 0:
        norm = norm ** gamma
    return round(float(norm * max_irrad), 2)


def cross_check_irradiance(
    weather_irradiance: Optional[float],
    ldr_raw: float,
    threshold: float = IRRAD_MISMATCH_THRESHOLD
) -> Dict[str, Any]:
    """
    Cross-checks weather API irradiance against calibrated ESP32 LDR irradiance.
    Uses LDR irradiance as fallback if weather irradiance is unavailable.
    Detects significant discrepancies between local ground sensor and remote weather station.
    """
    ldr_irrad = ldr_to_irradiance(ldr_raw)

    if weather_irradiance is None:
        return {
            "resolved_irradiance": ldr_irrad,
            "source": "LDR_CALIBRATED",
            "weather_irradiance": None,
            "ldr_irradiance": ldr_irrad,
            "discrepancy": 0.0,
            "mismatch_detected": False,
            "note": "Weather irradiance unavailable; used calibrated ESP32 LDR."
        }

    w_irrad = max(0.0, float(weather_irradiance))
    diff = abs(w_irrad - ldr_irrad)
    mismatch = diff >= threshold

    return {
        "resolved_irradiance": w_irrad,
        "source": "WEATHER_API" if not mismatch else "WEATHER_API_FLAGGED",
        "weather_irradiance": round(w_irrad, 2),
        "ldr_irradiance": round(ldr_irrad, 2),
        "discrepancy": round(diff, 2),
        "mismatch_detected": mismatch,
        "note": f"Irradiance discrepancy of {diff:.1f} W/m² (Weather: {w_irrad:.1f}, LDR: {ldr_irrad:.1f})." if mismatch else "Irradiance sources consistent."
    }

# ---------------------------------------------------------------------------
# Model selection: RandomForestRegressor (scikit-learn with fallback)
# ---------------------------------------------------------------------------
try:
    from sklearn.ensemble import RandomForestRegressor as _SklearnRF
    # Test if tree Cython DLLs load successfully under OS Application Control policies
    _test_model = _SklearnRF(n_estimators=1, max_depth=2, random_state=42)
    _dummy_X = np.array([[100, 10, 25, 35, 50, 2800, 12]])
    _dummy_y = np.array([12.0])
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
TARGET_COLUMN = "clean_power_mw"
MODEL_VERSION = "rf-clean-power-3w-v1"
_MODEL_METRICS = {}
_TRAINING_DATA_SOURCE = ""


# ---------------------------------------------------------------------------
# 1. Synthetic training data generator
# ---------------------------------------------------------------------------
def generate_demo_training_data(n_samples: int = 500, seed: int = 42) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate synthetic clean-panel training data calibrated to the 3W panel.

    Panel specifications:
      - Maximum voltage:  6 V
      - Maximum current:  500 mA (0.5 A)
      - Maximum power:    3000 mW = 3 W  (at STC: 1000 W/m², 25 °C)

    Physics model:
      clean_power_mW = 3000 mW × (irradiance / 1000) × temp_derate × cloud_factor × humidity_factor
      Hard-clamped to [0, 3000] mW (3 W).
    """
    np.random.seed(seed)

    # Environmental features
    solar_radiation = np.random.uniform(0.0, 1100.0, n_samples)
    ambient_temperature = np.random.uniform(15.0, 42.0, n_samples)
    cloud_cover = np.random.uniform(0.0, 95.0, n_samples)
    humidity = np.random.uniform(20.0, 90.0, n_samples)
    time_of_day = np.random.uniform(6.0, 18.0, n_samples)

    # Invert the calibrated LDR formula to generate physical sensor raw values:
    # irradiance = LDR_MAX_IRRAD * ((ldr - LDR_RAW_MIN)/(LDR_RAW_MAX - LDR_RAW_MIN))^LDR_GAMMA
    # => ldr = LDR_RAW_MIN + (LDR_RAW_MAX - LDR_RAW_MIN) * (irradiance / LDR_MAX_IRRAD)^(1/LDR_GAMMA)
    gamma_inv = 1.0 / max(0.01, LDR_GAMMA)
    raw_span = max(1.0, LDR_RAW_MAX - LDR_RAW_MIN)
    ideal_norm = np.clip(solar_radiation / max(1.0, LDR_MAX_IRRAD), 0.0, 1.0)
    ideal_ldr = LDR_RAW_MIN + raw_span * (ideal_norm ** gamma_inv)
    # Add realistic sensor noise (photocell jitter ~80 counts)
    ldr_value = np.clip(ideal_ldr + np.random.normal(0, 80, n_samples), LDR_RAW_MIN, LDR_RAW_MAX)

    # Panel temperature: ambient + solar irradiance heating effect
    panel_temperature = ambient_temperature + (solar_radiation / 1000.0) * 22.0 + np.random.normal(0, 1.2, n_samples)

    # Clean panel target power in mW (calibrated to 3000 mW / 3W panel at STC)
    temp_derate = 1.0 - 0.004 * (panel_temperature - 25.0)
    cloud_attenuation = 1.0 - (cloud_cover / 100.0) * 0.15
    humidity_effect = 1.0 - (humidity / 100.0) * 0.02

    # Base clean power proportional to panel max (3000 mW = 3W)
    clean_power = (
        PANEL_MAX_POWER_MW
        * (solar_radiation / 1000.0)
        * temp_derate
        * cloud_attenuation
        * humidity_effect
    )
    # Realistic noise proportional to 3W scale (σ = 2.0 mW)
    clean_power += np.random.normal(0, 2.0, n_samples)
    # Zero power when irradiance is negligible (< 15 W/m²)
    clean_power = np.where(solar_radiation <= 15.0, 0.0, clean_power)
    # Hard physical clamp: 0 ≤ power ≤ 3000 mW (3 W)
    clean_power = np.clip(np.round(clean_power, 4), 0.0, PANEL_MAX_POWER_MW)

    X = np.column_stack([
        solar_radiation,
        cloud_cover,
        ambient_temperature,
        panel_temperature,
        humidity,
        ldr_value,
        time_of_day,
    ])
    y = clean_power  # in mW, clamped to [0, 24]

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
        "mae_mw":  round(mae, 4),
        "rmse_mw": round(rmse, 4),
        "r2":      round(r_squared, 4),
        "training_samples":   int(len(train_indices)),
        "evaluation_samples": int(len(test_indices)),
        "data_source":        _TRAINING_DATA_SOURCE,
        "prototype_data":     _TRAINING_DATA_SOURCE == "synthetic_prototype_fallback",
        "panel_max_power_mw": PANEL_MAX_POWER_MW,
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
    Predict the expected clean-panel power in milliwatts (mW) for given input conditions.

    Input features (environmental only — no voltage/current/actual_power):
    - solar_radiation      (W/m²)
    - cloud_cover          (%)
    - ambient_temperature  (°C)
    - panel_temperature    (°C)
    - humidity             (%)
    - ldr_value            (raw ESP32 LDR/light reading, 0–4095)
    - time_of_day          (hour, 0–24)

    Returns:
        float: Expected clean power in mW, clamped to [0.0, 3000.0] mW (3 W).
    """
    global _TRAINED_MODEL
    if _TRAINED_MODEL is None:
        train_model()

    if isinstance(data, dict):
        # Physical boundary: if effective solar radiation is negligible (<= 15 W/m²), clean power is 0.0 mW
        sol_rad = float(data.get("solar_radiation", 785.0) if data.get("solar_radiation") is not None else 785.0)
        if sol_rad <= 15.0:
            return 0.0

        # Extract features in expected order with realistic fallback defaults
        features = [
            sol_rad,
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
        if X.size > 0 and X.ndim == 2 and X[0, 0] <= 15.0:
            return 0.0
    elif isinstance(data, np.ndarray):
        X = data if data.ndim == 2 else data.reshape(1, -1)
        if X.size > 0 and X[0, 0] <= 15.0:
            return 0.0
    else:
        raise ValueError(f"Unsupported data format for prediction: {type(data)}")

    try:
        prediction = _TRAINED_MODEL.predict(X)
        pred_val = float(prediction[0])
        # Hard physical clamp: 0 ≤ expected_clean_power_mW ≤ 24 mW
        return float(np.clip(round(pred_val, 3), 0.0, PANEL_MAX_POWER_MW))
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
    Compare measured and expected clean power (both in mW), then evaluate automated
    cleaning economics after checking precipitation expected in the next four hours.

    Formulas:
      actual_power_mW        = voltage_V × current_mA            (calculated upstream)
      power_loss_mW          = max(0, expected_clean_power_mW - actual_power_mW)
      soiling_loss_percent   = (power_loss_mW / expected_clean_power_mW) × 100
      recoverable_energy_mWh = power_loss_mW × operating_hours
      recoverable_energy_kWh = recoverable_energy_mWh / 1_000_000
      estimated_future_savings (₹) = recoverable_energy_kWh × tariff
    """
    # Clamp both inputs to physically valid mW range
    actual_power_mw    = float(np.clip(round(float(actual_power),           4), 0.0, None))
    predicted_clean_mw = float(np.clip(round(float(predicted_clean_power),  4), 0.0, PANEL_MAX_POWER_MW))

    power_loss_mw = round(max(0.0, predicted_clean_mw - actual_power_mw), 4)
    soiling_loss_percent = round(
        max(0.0, (power_loss_mw / predicted_clean_mw) * 100.0)
        if predicted_clean_mw > 0 else 0.0,
        2
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
    # Energy loss: mW × hours = mWh → convert to kWh (1 kWh = 1 000 000 mWh)
    recoverable_energy_mwh = round(power_loss_mw * operating_hours, 6)
    recoverable_energy_kwh = round(recoverable_energy_mwh / 1_000_000.0, 9)
    estimated_future_savings = round(recoverable_energy_kwh * tariff, 6)
    net_benefit = round(estimated_future_savings - cleaning_cost_value, 6)
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

    # Detect if actual power exceeds expected clean power (diagnostic warning)
    power_mismatch = (actual_power_mw > predicted_clean_mw)
    power_excess_mw = round(max(0.0, actual_power_mw - predicted_clean_mw), 4)

    if power_loss_mw <= 0:
        if power_excess_mw > 0.5:
            # Significant divergence: flag as diagnostic warning
            cleaning_status = "WARNING"
            cleaning_recommendation = "MODEL/IRRADIANCE MISMATCH"
            diagnostic_warning = (
                f"Actual power ({actual_power_mw:.2f} mW) exceeds expected clean power ({predicted_clean_mw:.2f} mW) "
                f"by {power_excess_mw:.2f} mW. Check LDR calibration or weather irradiance sync."
            )
        else:
            cleaning_status = "NORMAL"
            cleaning_recommendation = "NO CLEANING NEEDED"
            diagnostic_warning = None
    elif is_rain_next_4h:
        cleaning_status = "WATCH"
        cleaning_recommendation = "WAIT FOR RAIN"
        diagnostic_warning = None
    elif net_benefit > 0:
        cleaning_status = "CLEANING ADVISED"
        cleaning_recommendation = "CLEANING ADVISED"
        diagnostic_warning = None
    else:
        cleaning_status = "NORMAL"
        cleaning_recommendation = "DO NOT CLEAN"
        diagnostic_warning = None

    return {
        # --- Core power metrics (mW) ---
        "actual_power_mw":          actual_power_mw,
        "actual_power":             actual_power_mw,          # convenience alias
        "actual_power_w":           actual_power_mw,          # legacy alias (value is mW)
        "expected_clean_power_mw":  predicted_clean_mw,
        "expected_clean_power":     predicted_clean_mw,       # convenience alias
        "power_loss_mw":            power_loss_mw,
        "power_loss_w":             power_loss_mw,            # legacy alias (value is mW)
        "soiling_loss_percent":     soiling_loss_percent,
        # --- Energy & financial ---
        "energy_loss_mwh":          recoverable_energy_mwh,
        "energy_loss_kwh":          recoverable_energy_kwh,
        "recoverable_energy_kwh":   recoverable_energy_kwh,
        "estimated_cost_loss":      estimated_future_savings,
        "estimated_future_savings": estimated_future_savings,
        "cleaning_cost":            round(cleaning_cost_value, 2),
        "net_benefit":              net_benefit,
        # --- Cleaning decision & diagnostic ---
        "cleaning_status":          cleaning_status,
        "cleaning_recommendation":  cleaning_recommendation,
        "power_mismatch":           power_mismatch,
        "power_excess_mw":          power_excess_mw,
        "diagnostic_warning":       diagnostic_warning,
        # --- Rain / weather context ---
        "rain_expected":            is_rain_next_4h,
        "rain_expected_next_4h":    is_rain_next_4h,
        "rain_probability":         round(rain_probability_4h, 1),
        "rain_probability_next_4h": round(rain_probability_4h, 1),
        "rain_next_4h_mm":          round(rain_amount_4h, 2),
        "cloud_cover":              round(float(cloud_cover), 1) if cloud_cover is not None else None,
        # --- Metadata ---
        "panel_max_power_mw":       PANEL_MAX_POWER_MW,
        "panel_max_power_w":        PANEL_MAX_POWER_W,
        "model_version":            MODEL_VERSION,
    }

