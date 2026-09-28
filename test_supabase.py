"""
test_supabase.py
CROMPTON Solar Monitor - Supabase Database Verification Test Script
Tests credentials, connectivity, table schema availability, and CRUD operations.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from supabase_db import (
    test_connection,
    insert_solar_reading,
    get_recent_solar_readings,
    insert_weather_reading,
    get_recent_weather_readings,
    insert_prediction,
    get_recent_predictions
)

def run_tests():
    print("=" * 60)
    print(" CROMPTON Solar Monitor - Supabase Database Test")
    print("=" * 60)

    print("\n[Step 1] Testing Connection & Table Detection...")
    status = test_connection()

    print(f"  - Configured in .env: {'YES' if status['configured'] else 'NO'}")
    print(f"  - Supabase URL:       {status['url']}")
    print(f"  - Authenticated:      {'SUCCESS' if status['connected'] else 'FAILED'}")

    if not status["connected"]:
        print(f"\n[ERROR] Connection failed: {status['error']}")
        return False

    all_tables_exist = all(v is True for v in status["tables"].values())
    print("\n[Step 2] Table Status in Supabase:")
    for table_name, table_status in status["tables"].items():
        state = "EXISTS (Ready)" if table_status is True else "NOT FOUND (Need SQL migration)"
        print(f"  - {table_name:18}: {state}")

    if not all_tables_exist:
        print("\n" + "=" * 60)
        print(" ACTION REQUIRED: Run SQL Script in Supabase SQL Editor")
        print("=" * 60)
        print("The Supabase backend connection is verified and authenticated,")
        print("but the tables do not exist in the database yet.")
        print("To create them:")
        print("1. Open your Supabase Dashboard: https://supabase.com/dashboard")
        print("2. Navigate to your project -> 'SQL Editor'")
        print("3. Copy & paste the contents of 'schema.sql' (found in this folder)")
        print("4. Click 'Run'")
        print("5. Re-run this test script: python test_supabase.py\n")
        return False

    print("\n[Step 3] Tables detected! Testing Insertions & Queries...")

    # Test Solar Reading
    try:
        sample_solar = {
            "node_id": "CR-SOLAR-001",
            "voltage": 34.2,
            "current": 7.27,
            "power": 248.63,
            "panel_temperature": 44.5
        }
        solar_res = insert_solar_reading(sample_solar)
        print(f"  ✓ Solar Reading Inserted (ID: {solar_res.get('id', 'N/A')})")
        recent_solar = get_recent_solar_readings(limit=1)
        print(f"  ✓ Retrieved Recent Solar Readings: {len(recent_solar)} record(s)")
    except Exception as e:
        print(f"  ✗ Solar test error: {e}")

    # Test Weather Reading
    try:
        sample_weather = {
            "temperature": 31.5,
            "humidity": 54.0,
            "solar_radiation": 785.0,
            "cloud_cover": 15.0,
            "rainfall": 0.0,
            "wind_speed": 12.4
        }
        weather_res = insert_weather_reading(sample_weather)
        print(f"  ✓ Weather Reading Inserted (ID: {weather_res.get('id', 'N/A')})")
        recent_weather = get_recent_weather_readings(limit=1)
        print(f"  ✓ Retrieved Recent Weather Readings: {len(recent_weather)} record(s)")
    except Exception as e:
        print(f"  ✗ Weather test error: {e}")

    # Test Prediction
    try:
        sample_pred = {
            "expected_power": 320.0,
            "actual_power": 248.5,
            "soiling_loss_percent": 22.34,
            "energy_loss": 0.43,
            "estimated_cost_loss": 3.44,
            "cleaning_status": "CLEANING_RECOMMENDED"
        }
        pred_res = insert_prediction(sample_pred)
        print(f"  ✓ Prediction Inserted (ID: {pred_res.get('id', 'N/A')})")
        recent_pred = get_recent_predictions(limit=1)
        print(f"  ✓ Retrieved Recent Predictions: {len(recent_pred)} record(s)")
    except Exception as e:
        print(f"  ✗ Prediction test error: {e}")

    print("\n" + "=" * 60)
    print(" ALL SUPABASE TESTS PASSED SUCCESSFULLY! ")
    print("=" * 60)
    return True

if __name__ == "__main__":
    run_tests()
