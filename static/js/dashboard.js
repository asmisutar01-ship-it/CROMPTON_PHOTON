/**
 * CROMPTON SolarSense - Dashboard Scripts
 * Handles Chart.js initialization for Actual vs Expected Power diurnal curves,
 * health-check pinging, weather widget, and automated live prediction polling.
 */

// ── Global state: last resolved weather values for prediction queries ─────────
window._liveWeather = {};

document.addEventListener("DOMContentLoaded", () => {
    initPowerComparisonChart();
    initHealthPingButton();
    initWeatherWidget();
    initPredictionPolling();
});

/**
 * Initialize Chart.js comparing Actual Power vs Expected Clean Power over the day
 */
function initPowerComparisonChart() {
    const chartCanvas = document.getElementById("powerComparisonChart");
    if (!chartCanvas) return;

    let chartData = {
        labels: ["06:00", "07:00", "08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00"],
        expected_power_w: [0, 45, 120, 210, 290, 340, 360, 350, 310, 240, 160, 60, 0],
        actual_power_w: [0, 32, 88, 155, 218, 260, 275, 268, 235, 182, 120, 42, 0]
    };

    // Attempt to parse embedded backend initial data
    try {
        const rawJsonEl = document.getElementById("initialChartData");
        if (rawJsonEl && rawJsonEl.textContent.trim()) {
            const parsed = JSON.parse(rawJsonEl.textContent);
            if (parsed.labels && parsed.expected_power_w && parsed.actual_power_w) {
                chartData = parsed;
            }
        }
    } catch (e) {
        console.warn("Using fallback chart dataset:", e);
    }

    const ctx = chartCanvas.getContext("2d");

    // Gradients for chart fills
    const cleanGradient = ctx.createLinearGradient(0, 0, 0, 300);
    cleanGradient.addColorStop(0, "rgba(16, 185, 129, 0.25)");
    cleanGradient.addColorStop(1, "rgba(16, 185, 129, 0.0)");

    const actualGradient = ctx.createLinearGradient(0, 0, 0, 300);
    actualGradient.addColorStop(0, "rgba(245, 158, 11, 0.35)");
    actualGradient.addColorStop(1, "rgba(245, 158, 11, 0.02)");

    window.powerChartInstance = new Chart(ctx, {
        type: "line",
        data: {
            labels: chartData.labels,
            datasets: [
                {
                    label: "Expected Clean Power (W)",
                    data: chartData.expected_power_w,
                    borderColor: "#10b981",
                    backgroundColor: cleanGradient,
                    borderWidth: 2.5,
                    borderDash: [5, 5],
                    fill: true,
                    tension: 0.4,
                    pointBackgroundColor: "#10b981",
                    pointRadius: 3,
                    pointHoverRadius: 6
                },
                {
                    label: "Actual Soiled Power (W)",
                    data: chartData.actual_power_w,
                    borderColor: "#f59e0b",
                    backgroundColor: actualGradient,
                    borderWidth: 3,
                    fill: true,
                    tension: 0.4,
                    pointBackgroundColor: "#f59e0b",
                    pointRadius: 4,
                    pointHoverRadius: 7
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: "index",
                intersect: false
            },
            plugins: {
                legend: {
                    display: false // Using custom header legend in HTML
                },
                tooltip: {
                    backgroundColor: "rgba(15, 23, 42, 0.95)",
                    titleFont: { family: "'Plus Jakarta Sans', sans-serif", size: 13 },
                    bodyFont: { family: "'Space Grotesk', monospace", size: 12 },
                    padding: 12,
                    borderColor: "rgba(255, 255, 255, 0.1)",
                    borderWidth: 1,
                    displayColors: true,
                    callbacks: {
                        label: function(context) {
                            return `${context.dataset.label}: ${context.parsed.y} W`;
                        },
                        afterBody: function(tooltipItems) {
                            if (tooltipItems.length >= 2) {
                                const clean = tooltipItems[0].parsed.y;
                                const actual = tooltipItems[1].parsed.y;
                                const diff = clean - actual;
                                const lossPct = clean > 0 ? ((diff / clean) * 100).toFixed(1) : 0;
                                return `\nSoiling Loss Deficit: ${diff.toFixed(1)} W (-${lossPct}%)`;
                            }
                            return "";
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: "rgba(255, 255, 255, 0.05)",
                        borderColor: "rgba(255, 255, 255, 0.1)"
                    },
                    ticks: {
                        color: "#94a3b8",
                        font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 }
                    }
                },
                y: {
                    beginAtZero: true,
                    max: 420,
                    grid: {
                        color: "rgba(255, 255, 255, 0.05)",
                        borderColor: "rgba(255, 255, 255, 0.1)"
                    },
                    ticks: {
                        color: "#94a3b8",
                        font: { family: "'Space Grotesk', monospace", size: 11 },
                        callback: function(val) {
                            return val + " W";
                        }
                    }
                }
            }
        }
    });
}

/**
 * Health check ping button functionality
 */
function initHealthPingButton() {
    const pingBtn = document.getElementById("btnHealthCheck");
    const statusFlask = document.getElementById("statusFlask");
    const statusBadge = document.getElementById("backendStatusBadge");
    const statusTimestamp = document.getElementById("statusLastTimestamp");

    if (!pingBtn) return;

    pingBtn.addEventListener("click", async () => {
        pingBtn.textContent = "Checking...";
        pingBtn.disabled = true;

        try {
            const res = await fetch("/api/health");
            if (!res.ok) throw new Error(`HTTP error ${res.status}`);
            const data = await res.json();

            if (statusFlask) {
                statusFlask.textContent = "200 OK (Healthy)";
                statusFlask.className = "meta-val healthy-text";
            }
            const statusSupabase = document.getElementById("statusSupabase");
            if (statusSupabase && data.database) {
                statusSupabase.textContent = "Connected";
                statusSupabase.className = "meta-val healthy-text";
            }
            if (statusBadge) {
                statusBadge.textContent = "Backend Verified";
            }
            if (statusTimestamp && data.timestamp) {
                statusTimestamp.textContent = new Date(data.timestamp).toLocaleTimeString();
            }

            pingBtn.textContent = "Active ✓";
            setTimeout(() => {
                pingBtn.textContent = "Ping API";
                pingBtn.disabled = false;
            }, 2000);
        } catch (err) {
            console.error("Health check error:", err);
            if (statusFlask) {
                statusFlask.textContent = "Offline / Unreachable";
                statusFlask.className = "meta-val loss-cell";
            }
            pingBtn.textContent = "Retry";
            pingBtn.disabled = false;
        }
    });
}

/**
 * =========================================================================
 * WEATHER WIDGET
 * =========================================================================
 * - Reads last location from localStorage on page load and auto-fetches.
 * - Calls GET /api/weather?location=<city>
 * - Shows spinner / error banner / resolved data without page reload.
 * - Stores latest weather values in window._liveWeather for prediction queries.
 */
function initWeatherWidget() {
    const input     = document.getElementById("locationInput");
    const btn       = document.getElementById("btnGetWeather");
    const spinner   = document.getElementById("weatherLoadingSpinner");
    const errBanner = document.getElementById("weatherErrorBanner");

    if (!input || !btn) return;

    // ── Restore last-used location from localStorage or default to Pune ───
    const LS_KEY = "crompton_last_location";
    const saved  = localStorage.getItem(LS_KEY);
    const initialLocation = (saved && saved.trim()) ? saved.trim() : "Pune";
    input.value = initialLocation;
    fetchAndRenderWeather(initialLocation);

    // ── Button click ──────────────────────────────────────────────────────
    btn.addEventListener("click", () => {
        const loc = input.value.trim();
        if (!loc) {
            showWeatherError("Please enter a location before clicking Get Weather.");
            input.focus();
            return;
        }
        fetchAndRenderWeather(loc);
    });

    // ── Enter-key shortcut ────────────────────────────────────────────────
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            btn.click();
        }
    });

    // ── Clear error when user starts typing ───────────────────────────────
    input.addEventListener("input", () => hideWeatherError());


    // ── Core fetch function ───────────────────────────────────────────────
    async function fetchAndRenderWeather(location) {
        setLoadingState(true);
        hideWeatherError();

        try {
            const url = `/api/weather?location=${encodeURIComponent(location)}`;
            const res = await fetch(url);
            const data = await res.json();

            if (!res.ok) {
                const msg = data.error || "Weather data temporarily unavailable.";
                showWeatherError(msg);
                setLoadingState(false);
                return;
            }

            // Success – persist location and render data
            localStorage.setItem(LS_KEY, location);
            renderWeatherData(data, location);

        } catch (err) {
            console.error("Weather fetch failed:", err);
            showWeatherError("Weather data temporarily unavailable. Please check your connection.");
        } finally {
            setLoadingState(false);
        }
    }


    // ── Render successful weather data into the card ──────────────────────
    function renderWeatherData(data, requestedLocation) {
        const loc     = data.location || {};
        const weather = data.weather  || {};

        // Location banner
        const banner    = document.getElementById("weatherLocationBanner");
        const locName   = document.getElementById("weatherLocationName");
        const locCoords = document.getElementById("weatherCoords");

        if (banner) {
            const displayName = [
                loc.name,
                loc.admin1 && loc.admin1 !== loc.name ? loc.admin1 : null,
                loc.country
            ].filter(Boolean).join(", ");

            if (locName)   locName.textContent  = displayName || requestedLocation || "Resolved Location";
            if (locCoords && loc.latitude != null && loc.longitude != null) {
                locCoords.textContent = `(${loc.latitude.toFixed(3)}°, ${loc.longitude.toFixed(3)}°)`;
            }
            banner.removeAttribute("hidden");
            banner.style.display = "flex";
        }

        // Hide empty-state, show grid
        const emptyState = document.getElementById("weatherEmptyState");
        const dataGrid   = document.getElementById("weatherDataGrid");
        if (emptyState) {
            emptyState.setAttribute("hidden", "");
            emptyState.style.display = "none";
        }
        if (dataGrid) {
            dataGrid.removeAttribute("hidden");
            dataGrid.style.display = "grid";
        }

        // Populate individual weather values
        setWeatherVal("wvTemp",          weather.temperature,          "°C");
        setWeatherVal("wvHumidity",      weather.humidity,             "%");
        setWeatherVal("wvSolarRad",      weather.solar_radiation,      "W/m²");
        setWeatherVal("wvCloudCover",    weather.cloud_cover,          "%");
        setWeatherVal("wvWindSpeed",     weather.wind_speed,           "km/h");

        // Rich, dynamic rain values
        const curRain  = Number(weather.rainfall) || 0;
        const rain24h  = Number(weather.rain_forecast_24h_mm) || 0;
        const rainProb = Number(weather.rain_probability) || 0;

        const displayRain = curRain > 0
            ? `${curRain.toFixed(1)} mm (Live)`
            : (rain24h > 0 ? `${rain24h.toFixed(1)} mm (24h)` : "0.0 mm");

        const elWvRain = document.getElementById("wvRain");
        if (elWvRain) elWvRain.innerHTML = `${displayRain}`;

        setWeatherVal("wvRainProb",     rainProb.toFixed(0),          "%");
        setWeatherVal("wvRainForecast", rain24h.toFixed(1),           "mm");

        // Update System Status badge
        const weatherApiStatus = document.getElementById("statusWeatherApi");
        if (weatherApiStatus) {
            weatherApiStatus.textContent = "Live ✓ (Open-Meteo)";
            weatherApiStatus.className = "meta-val healthy-text";
        }

        // Persist live weather into global state so prediction polls pick them up
        window._liveWeather = {
            solar_radiation:      weather.solar_radiation,
            temperature:          weather.temperature,
            humidity:             weather.humidity,
            cloud_cover:          weather.cloud_cover,
            location:             loc.name || requestedLocation,
            rain_expected:        weather.rain_expected,
            rain_probability:     weather.rain_probability,
            rain_forecast_24h_mm: weather.rain_forecast_24h_mm
        };

        // Update Irradiance label on KPI Card 2
        const elKpiIrradiance = document.getElementById("valKpiIrradiance");
        if (elKpiIrradiance && weather.solar_radiation !== undefined) {
            elKpiIrradiance.textContent = `${weather.solar_radiation} W/m²`;
        }

        // Immediately refresh predictions with live weather context
        if (typeof window.triggerPredictionFetch === "function") {
            window.triggerPredictionFetch();
        }
    }


    // ── Helper: populate a weather value element ──────────────────────────
    function setWeatherVal(id, value, unit) {
        const el = document.getElementById(id);
        if (!el) return;
        const display = (value !== null && value !== undefined) ? value : "—";
        el.innerHTML = `${display}<small> ${unit}</small>`;
    }


    // ── UI State helpers ──────────────────────────────────────────────────
    function setLoadingState(loading) {
        btn.disabled   = loading;
        input.disabled = loading;
        if (loading) {
            spinner.removeAttribute("hidden");
            spinner.style.display = "inline-flex";
            btn.setAttribute("hidden", "");
            btn.style.display = "none";
        } else {
            spinner.setAttribute("hidden", "");
            spinner.style.display = "none";
            btn.removeAttribute("hidden");
            btn.style.display = "inline-flex";
        }
    }

    function showWeatherError(msg) {
        errBanner.textContent = msg;
        errBanner.removeAttribute("hidden");
    }

    function hideWeatherError() {
        errBanner.setAttribute("hidden", "");
    }
}

/**
 * =========================================================================
 * AUTOMATED PREDICTION POLLING
 * =========================================================================
 * Calls GET /api/prediction every POLL_INTERVAL_MS milliseconds.
 *
 * The backend /api/prediction endpoint automatically:
 *   1. Generates a fresh sensor reading (voltage, current, panel_temp, actual_power)
 *      via sensor_service.py (simulated now; ESP32 hardware later).
 *   2. Combines sensor data with optional weather query params.
 *   3. Runs the RandomForestRegressor to predict expected_clean_power.
 *   4. Returns full soiling metrics, financial loss & weather-aware recommendation.
 *
 * The frontend passes the latest resolved weather values (from weather widget)
 * as query params so the model uses real environmental context and rain forecast.
 */
function initPredictionPolling() {
    const POLL_INTERVAL_MS = 5000; // refresh every 5 seconds

    async function fetchAndRenderPrediction() {
        try {
            // Pass live weather values to the prediction endpoint if available
            const params = new URLSearchParams();
            const w = window._liveWeather || {};
            if (w.solar_radiation      != null) params.append("solar_radiation",      w.solar_radiation);
            if (w.temperature          != null) params.append("temperature",          w.temperature);
            if (w.humidity             != null) params.append("humidity",             w.humidity);
            if (w.cloud_cover          != null) params.append("cloud_cover",          w.cloud_cover);
            if (w.location             != null) params.append("location",             w.location);
            if (w.rain_expected        != null) params.append("rain_expected",        w.rain_expected);
            if (w.rain_probability     != null) params.append("rain_probability",     w.rain_probability);
            if (w.rain_forecast_24h_mm != null) params.append("rain_forecast_24h_mm", w.rain_forecast_24h_mm);

            const queryStr = params.toString();
            const url = queryStr ? `/api/prediction?${queryStr}` : `/api/prediction`;

            const res = await fetch(url);
            if (!res.ok) {
                console.warn("Prediction endpoint returned non-200 status:", res.status);
                return;
            }

            const data = await res.json();
            renderPredictionData(data);
        } catch (err) {
            console.error("Failed to fetch ML prediction:", err);
        }
    }

    // Expose trigger for immediate update upon weather change
    window.triggerPredictionFetch = fetchAndRenderPrediction;

    function renderPredictionData(data) {
        if (!data || typeof data !== "object") return;

        const actualPower    = Number(data.actual_power)          || 0;
        const cleanPower     = Number(data.expected_clean_power)   || 0;
        const lossPercent    = Number(data.soiling_loss_percent)   || 0;
        const powerLossW     = Number(data.power_loss_w)           || 0;
        const energyLossKwh  = Number(data.energy_loss_kwh)        || 0;
        const costLossInr    = Number(data.estimated_cost_loss)    || 0;
        const cleaningStatus = data.cleaning_status                || "NORMAL";
        const sensorSource   = data.sensor_source                  || "Simulated";

        // ── 1. KPI Cards ───────────────────────────────────────────────────
        const elActual        = document.getElementById("valActualPower");
        const elExpected      = document.getElementById("valExpectedPower");
        const elSoiling       = document.getElementById("valSoilingLoss");
        const elPowerLoss     = document.getElementById("valPowerLoss");
        const elEnergyLoss    = document.getElementById("valEnergyLoss");
        const elFinancialLoss = document.getElementById("valFinancialLoss");
        const elKpiCleaningTag = document.getElementById("kpiCleaningTag");
        const elCardSoiling   = document.getElementById("cardSoilingLoss");
        const elVoltage       = document.getElementById("valPanelVoltage");
        const elCurrent       = document.getElementById("valPanelCurrent");

        if (elActual)        elActual.textContent        = actualPower.toFixed(1);
        if (elExpected)      elExpected.textContent      = cleanPower.toFixed(1);
        if (elSoiling)       elSoiling.textContent       = lossPercent.toFixed(1);
        if (elPowerLoss)     elPowerLoss.textContent     = powerLossW.toFixed(1);
        if (elEnergyLoss)    elEnergyLoss.textContent    = energyLossKwh.toFixed(2);
        if (elFinancialLoss) elFinancialLoss.textContent = costLossInr.toFixed(2);

        if (data.voltage !== undefined && elVoltage)
            elVoltage.textContent = Number(data.voltage).toFixed(1);
        if (data.current !== undefined && elCurrent)
            elCurrent.textContent = Number(data.current).toFixed(2);

        if (elKpiCleaningTag) elKpiCleaningTag.textContent = cleaningStatus;

        // ── 2. Sensor source chip ──────────────────────────────────────────
        const elSensorLabel = document.getElementById("sensorSourceLabel");
        const elSensorChip  = document.getElementById("sensorSourceChip");
        if (elSensorLabel) {
            elSensorLabel.textContent = `Sensor: ${sensorSource}`;
        }
        if (elSensorChip) {
            elSensorChip.classList.toggle("hardware", sensorSource === "Hardware");
        }

        // ── 3. AI Insight / Cleaning Status pill styling ───────────────────
        const elCleaningStatus = document.getElementById("valCleaningStatus");
        if (elCleaningStatus) {
            elCleaningStatus.textContent = cleaningStatus;
            elCleaningStatus.className = "urgency-pill font-mono ";
            if (cleaningStatus === "NORMAL") {
                elCleaningStatus.classList.add("status-pill-normal");
            } else if (cleaningStatus === "WATCH") {
                elCleaningStatus.classList.add("status-pill-watch");
            } else {
                elCleaningStatus.classList.add("status-pill-advised");
            }
        }

        if (elCardSoiling) {
            elCardSoiling.classList.remove("warning", "danger", "healthy");
            if (cleaningStatus === "NORMAL") {
                elCardSoiling.classList.add("healthy");
            } else if (cleaningStatus === "WATCH") {
                elCardSoiling.classList.add("warning");
            } else {
                elCardSoiling.classList.add("warning");
            }
        }

        // ── 4. Visual Dual-Bar Power Comparison ───────────────────────────
        const elVisualRatio  = document.getElementById("valVisualRatio");
        const elBarActualFill = document.getElementById("barActualFill");
        const elBarCleanFill = document.getElementById("barCleanFill");
        const elBarActualVal = document.getElementById("barActualVal");
        const elBarCleanVal  = document.getElementById("barCleanVal");

        const ratio = cleanPower > 0
            ? Math.min(100, Math.max(0, (actualPower / cleanPower) * 100))
            : 100;

        if (elVisualRatio)   elVisualRatio.textContent  = `${ratio.toFixed(1)}% clean power`;
        if (elBarActualFill) elBarActualFill.style.width = `${ratio.toFixed(1)}%`;
        if (elBarCleanFill)  elBarCleanFill.style.width  = "100%";
        if (elBarActualVal)  elBarActualVal.textContent  = `${actualPower.toFixed(1)} W`;
        if (elBarCleanVal)   elBarCleanVal.textContent   = `${cleanPower.toFixed(1)} W`;

        // ── 5. Insight Metric Box values ───────────────────────────────────
        const elInsightPowerLoss  = document.getElementById("valInsightPowerLoss");
        const elInsightEnergyLoss = document.getElementById("valInsightEnergyLoss");
        const elInsightCostLoss   = document.getElementById("valInsightCostLoss");

        if (elInsightPowerLoss)  elInsightPowerLoss.textContent  = `${powerLossW.toFixed(1)} W`;
        if (elInsightEnergyLoss) elInsightEnergyLoss.textContent = `${energyLossKwh.toFixed(2)} kWh`;
        if (elInsightCostLoss)   elInsightCostLoss.textContent   = `₹ ${costLossInr.toFixed(2)}`;

        // ── 6. Weather-Aware Cleaning Recommendation Card ───────────────────
        const rainExpected  = (data.rain_expected !== undefined)
            ? Boolean(data.rain_expected)
            : Boolean(window._liveWeather && window._liveWeather.rain_expected);

        const rainProb      = (data.rain_probability !== undefined)
            ? Number(data.rain_probability)
            : Number(window._liveWeather && window._liveWeather.rain_probability) || 0;

        const rainVol       = (data.rain_forecast_24h_mm !== undefined)
            ? Number(data.rain_forecast_24h_mm)
            : Number(window._liveWeather && window._liveWeather.rain_forecast_24h_mm) || 0;

        const cleaningRec   = data.cleaning_recommendation ||
            (lossPercent < 5.0 ? "NO CLEANING NEEDED" :
            (lossPercent <= 15.0 ? "MONITOR" :
            (rainExpected ? "WAIT FOR RAIN" : "CLEANING ADVISED")));

        const elRecCard     = document.getElementById("sectionCleaningRecommendation");
        const elRecBadge    = document.getElementById("valCleaningRecBadge");
        const elRecBanner   = document.getElementById("recBannerBox");
        const elRecAction   = document.getElementById("valRecAction");
        const elRecDesc     = document.getElementById("valRecDesc");
        const elRecIcon     = document.getElementById("recActionIcon");
        const elRecRain     = document.getElementById("valRecRainExpected");
        const elRecProb     = document.getElementById("valRecRainProb");

        if (elRecBadge) {
            elRecBadge.textContent = cleaningRec;
            elRecBadge.className = "urgency-pill pill-medium ";
            if (cleaningRec === "NO CLEANING NEEDED") {
                elRecBadge.classList.add("status-pill-normal");
            } else if (cleaningRec === "MONITOR") {
                elRecBadge.classList.add("status-pill-watch");
            } else if (cleaningRec === "WAIT FOR RAIN") {
                elRecBadge.classList.add("status-pill-rain");
            } else {
                elRecBadge.classList.add("status-pill-advised");
            }
        }

        if (elRecCard) {
            elRecCard.classList.remove("rec-state-normal", "rec-state-watch", "rec-state-rain", "rec-state-advised");
            if (cleaningRec === "NO CLEANING NEEDED") elRecCard.classList.add("rec-state-normal");
            else if (cleaningRec === "MONITOR") elRecCard.classList.add("rec-state-watch");
            else if (cleaningRec === "WAIT FOR RAIN") elRecCard.classList.add("rec-state-rain");
            else elRecCard.classList.add("rec-state-advised");
        }

        if (elRecBanner) {
            elRecBanner.className = "rec-banner ";
            if (cleaningRec === "NO CLEANING NEEDED") elRecBanner.classList.add("rec-banner-normal");
            else if (cleaningRec === "MONITOR") elRecBanner.classList.add("rec-banner-watch");
            else if (cleaningRec === "WAIT FOR RAIN") elRecBanner.classList.add("rec-banner-rain");
            else elRecBanner.classList.add("rec-banner-advised");
        }

        if (elRecAction) elRecAction.textContent = cleaningRec;

        if (elRecIcon) {
            if (cleaningRec === "NO CLEANING NEEDED") elRecIcon.textContent = "✨";
            else if (cleaningRec === "MONITOR") elRecIcon.textContent = "👁️";
            else if (cleaningRec === "WAIT FOR RAIN") elRecIcon.textContent = "🌧️";
            else elRecIcon.textContent = "🧹";
        }

        if (elRecDesc) {
            if (cleaningRec === "NO CLEANING NEEDED") {
                elRecDesc.textContent = "Soiling is low (<5%). Clean panel is operating at peak yield.";
            } else if (cleaningRec === "MONITOR") {
                elRecDesc.textContent = "Moderate soiling (5–15%). Monitor output degradation before scheduling maintenance.";
            } else if (cleaningRec === "WAIT FOR RAIN") {
                elRecDesc.textContent = `Rain expected within 24h (~${rainVol.toFixed(1)} mm, ${rainProb.toFixed(0)}% chance). Natural washing will restore efficiency — save water & labor cost.`;
            } else {
                elRecDesc.textContent = "Heavy soiling (>15%) and no rain forecast in next 24h. Manual cleaning recommended.";
            }
        }

        if (elRecRain) {
            if (rainExpected) {
                elRecRain.textContent = rainVol > 0 ? `Rain Expected (~${rainVol.toFixed(1)} mm) 🌧` : "Rain Expected 🌧";
                elRecRain.classList.add("has-rain");
            } else {
                elRecRain.textContent = "No Rain Forecast ☀️";
                elRecRain.classList.remove("has-rain");
            }
        }

        if (elRecProb) {
            elRecProb.textContent = `${rainProb.toFixed(0)}%`;
        }

        // ── 7. Update live chart actual-power data point at current hour ───
        if (window.powerChartInstance) {
            const chart = window.powerChartInstance;
            const hour = new Date().getHours();
            // Chart labels go 06–18; map hour to index
            const idx = Math.max(0, Math.min(12, hour - 6));
            if (chart.data.datasets && chart.data.datasets.length > 1) {
                chart.data.datasets[1].data[idx] = Math.round(actualPower);
                chart.data.datasets[0].data[idx] = Math.round(cleanPower);
                chart.update("none"); // silent update (no animation) for smooth live feel
            }
        }
    }

    // ── Start polling immediately, then every POLL_INTERVAL_MS ────────────
    fetchAndRenderPrediction();
    setInterval(fetchAndRenderPrediction, POLL_INTERVAL_MS);
}


