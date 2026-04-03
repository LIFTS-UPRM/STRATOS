from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import numpy as np

import app as astra_app
from astra.GFS import GFS_Handler, GFS_Map
from astra.interpolate import Linear4DInterpolator


FIXTURE_DIR = Path(__file__).parent / "example_data"


class DummyResponse(object):
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeProfile(object):
    def __init__(
        self,
        *,
        launch_dt,
        time_vector,
        latitude_profile,
        longitude_profile,
        altitude_profile,
        highest_alt_index,
        highest_altitude,
        has_burst=True,
        flight_number=1,
    ):
        self.launchDateTime = launch_dt
        self.timeVector = time_vector
        self.latitudeProfile = latitude_profile
        self.longitudeProfile = longitude_profile
        self.altitudeProfile = altitude_profile
        self.highestAltIndex = highest_alt_index
        self.highestAltitude = highest_altitude
        self.hasBurst = has_burst
        self.flightNumber = flight_number


class DummyEnvironment(object):
    def __init__(self, launch_dt):
        self.launchSiteLat = 34.05
        self.launchSiteLon = -118.24
        self.launchSiteElev = 87.0
        self.dateAndTime = launch_dt
        self.forceNonHD = False
        self.forecastDuration = 4
        self.UTC_offset = 0
        self._UTC_time = None
        self._weatherLoaded = False
        self._GFSmodule = None

    def load(self, progressHandler=None):
        raise RuntimeError("simulated GFS failure")


def _read_fixture(name):
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def _open_meteo_payload(start_time):
    times = [
        start_time.isoformat(timespec="minutes"),
        (start_time + timedelta(hours=1)).isoformat(timespec="minutes"),
        (start_time + timedelta(hours=2)).isoformat(timespec="minutes"),
    ]
    payload = {"hourly": {"time": times}}
    profiles = {
        1000: ([18.0, 18.2, 18.4], [120.0, 125.0, 130.0], [12.0, 14.0, 16.0], [240.0, 245.0, 250.0]),
        850: ([10.0, 10.2, 10.4], [1500.0, 1510.0, 1520.0], [25.0, 26.0, 27.0], [245.0, 250.0, 255.0]),
        700: ([2.0, 2.2, 2.4], [3000.0, 3015.0, 3030.0], [35.0, 36.0, 37.0], [250.0, 255.0, 260.0]),
        500: ([-10.0, -9.8, -9.6], [5500.0, 5520.0, 5540.0], [45.0, 46.0, 47.0], [255.0, 260.0, 265.0]),
        300: ([-30.0, -29.8, -29.6], [9000.0, 9025.0, 9050.0], [55.0, 56.0, 57.0], [260.0, 265.0, 270.0]),
        100: ([-55.0, -54.8, -54.6], [16000.0, 16050.0, 16100.0], [65.0, 66.0, 67.0], [265.0, 270.0, 275.0]),
        30: ([-48.0, -47.8, -47.6], [24000.0, 24050.0, 24100.0], [75.0, 76.0, 77.0], [270.0, 275.0, 280.0]),
        10: ([-42.0, -41.8, -41.6], [31000.0, 31050.0, 31100.0], [80.0, 81.0, 82.0], [275.0, 280.0, 285.0]),
    }
    for level, (temps, heights, speeds, directions) in profiles.items():
        payload["hourly"][f"temperature_{level}hPa"] = temps
        payload["hourly"][f"geopotential_height_{level}hPa"] = heights
        payload["hourly"][f"wind_speed_{level}hPa"] = speeds
        payload["hourly"][f"wind_direction_{level}hPa"] = directions
    return payload


def test_generate_matrix_parses_thredds_time1():
    handler = GFS_Handler(0.0, 0.0, datetime(2026, 4, 1, 6), HD=True)
    handler.cycleDateTime = datetime(2026, 4, 1, 6)

    matrix, matrix_map = handler._generate_matrix([
        _read_fixture("thredds_0p25_temperature.ascii")
    ])

    expected_start = handler.cycleDateTime.toordinal() + handler.cycleDateTime.hour / 24.0
    assert matrix.shape == (2, 2, 2, 2)
    assert matrix[0, 0, 0, 0] == pytest.approx(292.3999)
    assert matrix_map.fwdPressure == pytest.approx([850.0, 900.0])
    assert matrix_map.fwdLongitude == pytest.approx([175.0, 175.25])
    assert matrix_map.fwdTime[0] == pytest.approx(expected_start)
    assert matrix_map.fwdTime[1] == pytest.approx(expected_start + 3.0 / 24.0)


def test_generate_matrix_parses_thredds_time_coordinate():
    handler = GFS_Handler(0.0, 0.0, datetime(2026, 4, 1, 6), HD=False)
    handler.cycleDateTime = datetime(2026, 4, 1, 6)

    matrix, matrix_map = handler._generate_matrix([
        _read_fixture("thredds_0p5_temperature.ascii")
    ])

    expected_start = handler.cycleDateTime.toordinal() + handler.cycleDateTime.hour / 24.0
    assert matrix.shape == (2, 2, 2, 2)
    assert matrix[1, 1, 1, 1] == pytest.approx(288.0)
    assert matrix_map.fwdPressure == pytest.approx([850.0, 900.0])
    assert matrix_map.fwdLongitude == pytest.approx([180.0, -179.5])
    assert matrix_map.fwdTime[0] == pytest.approx(expected_start)
    assert matrix_map.fwdTime[1] == pytest.approx(expected_start + 3.0 / 24.0)


def test_pressure_interpolator_handles_ascending_thredds_pressures():
    handler = GFS_Handler(0.5, 0.5, datetime(2026, 4, 1, 6), HD=True)
    handler.lonStep = 1.0
    handler.altitudeMap = GFS_Map()
    handler.altitudeMap.fwdLatitude = [0.0, 1.0]
    handler.altitudeMap.fwdLongitude = [0.0, 1.0]
    handler.altitudeMap.fwdPressure = [10.0, 100.0, 1000.0]
    handler.altitudeMap.fwdTime = [0.0, 1.0]
    handler.altitudeMap.revLatitude = {0.0: 0, 1.0: 1}
    handler.altitudeMap.revLongitude = {0.0: 0, 1.0: 1}
    handler.altitudeMap.revPressure = {10.0: 0, 100.0: 1, 1000.0: 2}
    handler.altitudeMap.revTime = {0.0: 0, 1.0: 1}
    handler.altitudeData = np.array(
        [
            [[[30000.0, 30000.0], [15000.0, 15000.0], [0.0, 0.0]]] * 2,
            [[[30000.0, 30000.0], [15000.0, 15000.0], [0.0, 0.0]]] * 2,
        ]
    )

    assert handler._pressure_interpolator(0.5, 0.5, 0.0, 0.5) == pytest.approx(1000.0)
    assert handler._pressure_interpolator(0.5, 0.5, 15000.0, 0.5) == pytest.approx(100.0)
    assert handler._pressure_interpolator(0.5, 0.5, 30000.0, 0.5) == pytest.approx(10.0)


def test_linear_interpolator_clips_pressure_upper_bound_without_index_error():
    data = np.array(
        [
            [[[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]], [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]],
            [[[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]], [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]],
        ],
        dtype=float,
    )
    interpolator = Linear4DInterpolator(
        data,
        [
            [0.0, 1.0],
            [0.0, 1.0],
            [10.0, 100.0, 1000.0],
            [0.0, 1.0],
            {0.0: 0, 1.0: 1},
            {0.0: 0, 1.0: 1},
            {10.0: 0, 100.0: 1, 1000.0: 2},
            {0.0: 0, 1.0: 1},
        ],
    )

    assert interpolator(0.5, 0.5, 1000.0, 0.5) == pytest.approx(3.0)


def test_fetch_open_meteo_uses_correct_wind_variable_names(monkeypatch):
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return DummyResponse({"hourly": {"time": ["2026-04-01T00:00"]}})

    monkeypatch.setattr(astra_app.requests, "get", fake_get)

    launch_dt = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=2)
    environment = DummyEnvironment(launch_dt)
    astra_app._fetch_open_meteo_weather_profile(environment)

    hourly = captured["params"]["hourly"]
    assert "wind_speed_1000hPa" in hourly
    assert "wind_direction_1000hPa" in hourly
    assert "windspeed_1000hPa" not in hourly
    assert "winddirection_1000hPa" not in hourly


def test_load_or_refresh_forecast_cache_falls_back_to_open_meteo(monkeypatch, tmp_path):
    launch_dt = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=2)
    payload = _open_meteo_payload(launch_dt)

    def fake_get(url, params=None, timeout=None):
        return DummyResponse(payload)

    monkeypatch.setattr(astra_app, "GFS_CACHE_ROOT", tmp_path)
    monkeypatch.setattr(astra_app.requests, "get", fake_get)

    from astra import global_tools as tools

    monkeypatch.setattr(tools, "getUTCOffset", lambda lat, lon, dt: 0)

    environment = DummyEnvironment(launch_dt)
    forecast = astra_app._load_or_refresh_forecast_cache(environment)

    assert forecast["source"] == "open-meteo"
    assert environment._weatherLoaded is True
    assert environment.getWindSpeed(
        environment.launchSiteLat,
        environment.launchSiteLon,
        5000.0,
        launch_dt + timedelta(minutes=30),
    ) > 0.0


def test_hardware_endpoint_returns_catalog():
    client = astra_app.app.test_client()

    response = client.get("/api/hardware")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["gas_types"] == ["Helium", "Hydrogen"]
    assert any(item["name"] == "TA800" for item in payload["balloons"])
    assert any(item["name"] == "SPH36" for item in payload["parachutes"])


def test_lookup_launch_elevation_uses_open_topo_data(monkeypatch):
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return DummyResponse(
            {
                "status": "OK",
                "results": [
                    {
                        "dataset": "test-dataset",
                        "elevation": 321.9,
                        "location": {"lat": 56.0, "lng": 123.0},
                    }
                ],
            }
        )

    monkeypatch.setattr(astra_app, "OPENTOPO_ENDPOINTS", ["https://api.opentopodata.org/v1/mapzen"])
    monkeypatch.setattr(astra_app.requests, "get", fake_get)

    payload = astra_app.lookup_launch_elevation(56.0, 123.0)

    assert captured["url"] == "https://api.opentopodata.org/v1/mapzen"
    assert captured["params"] == {"locations": "56.0,123.0"}
    assert payload["elevation_m"] == pytest.approx(321.9)
    assert payload["dataset"] == "test-dataset"
    assert payload["source"] == "open-topo-data"


def test_elevation_endpoint_returns_lookup(monkeypatch):
    monkeypatch.setattr(
        astra_app,
        "lookup_launch_elevation",
        lambda lat, lon: {
            "lat": lat,
            "lon": lon,
            "elevation_m": 432.1,
            "dataset": "test-dataset",
            "status": "OK",
            "source": "open-topo-data",
        },
    )
    client = astra_app.app.test_client()

    response = client.get("/api/elevation?lat=56&lon=123")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["elevation_m"] == pytest.approx(432.1)
    assert payload["dataset"] == "test-dataset"


def test_coerce_datetime_normalizes_utc_payload():
    assert astra_app._coerce_datetime({"launch_datetime": "2026-04-01T16:30:00Z"}, "launch_datetime") == datetime(
        2026, 4, 1, 16, 30
    )
    assert astra_app._coerce_datetime({"launch_datetime": "2026-04-01T12:30:00-04:00"}, "launch_datetime") == datetime(
        2026, 4, 1, 16, 30
    )


def test_simulate_endpoint_uses_service_result(monkeypatch):
    expected = {
        "status": "success",
        "launch": {"lat": 29.21, "lon": -81.02, "elevation_m": 4.0, "datetime": "2026-04-01T12:00:00"},
        "config": {"balloon_model": "TA800"},
        "num_runs": 1,
        "forecast": {"source": "downloaded"},
        "runs": [{"run": 1, "landing_lat": 29.5, "landing_lon": -80.5, "landing_alt_m": 0.0, "max_altitude_m": 30000.0, "flight_duration_s": 7200.0, "burst": True}],
        "aggregate": {"landing_spread_km": 0.0, "max_altitude_m_mean": 30000.0, "flight_duration_s_mean": 7200.0, "burst_rate": 1.0},
        "trajectory_run1": [{"time_s": 0.0, "lat": 29.21, "lon": -81.02, "alt_m": 4.0}],
    }

    monkeypatch.setattr(astra_app, "run_simulation", lambda payload: expected)
    client = astra_app.app.test_client()

    response = client.post(
        "/api/simulate",
        json={
            "launch_lat": 29.21,
            "launch_lon": -81.02,
            "launch_elevation_m": 4.0,
            "launch_datetime": "2026-04-01T12:00:00",
            "balloon_model": "TA800",
            "gas_type": "Helium",
            "nozzle_lift_kg": 2.0,
            "payload_weight_kg": 0.433,
        },
    )

    assert response.status_code == 200
    assert response.get_json()["forecast"]["source"] == "downloaded"


def test_estimate_sondehub_request_uses_baseline_rates():
    launch_dt = datetime(2026, 4, 1, 12, 0)
    profile = FakeProfile(
        launch_dt=launch_dt,
        time_vector=[0.0, 60.0, 120.0, 180.0, 240.0, 300.0],
        latitude_profile=[18.0, 18.01, 18.02, 18.03, 18.04, 18.05],
        longitude_profile=[-67.0, -66.99, -66.98, -66.97, -66.96, -66.95],
        altitude_profile=[0.0, 300.0, 600.0, 900.0, 600.0, 300.0],
        highest_alt_index=3,
        highest_altitude=900.0,
    )

    request_params = astra_app._estimate_sondehub_request(profile)

    assert request_params["profile"] == "standard_profile"
    assert request_params["launch_longitude"] == pytest.approx(293.0)
    assert request_params["ascent_rate"] == pytest.approx(5.0)
    assert request_params["burst_altitude"] == pytest.approx(900.0)
    assert request_params["descent_rate"] == pytest.approx(5.0)
    assert request_params["launch_datetime"] == "2026-04-01T12:00:00Z"


def test_apply_sondehub_calibration_recenters_path_without_moving_launch():
    launch_dt = datetime(2026, 4, 1, 12, 0)
    profile = FakeProfile(
        launch_dt=launch_dt,
        time_vector=[0.0, 60.0, 120.0, 180.0, 240.0],
        latitude_profile=[18.0, 18.02, 18.04, 18.06, 18.08],
        longitude_profile=[-67.0, -66.98, -66.96, -66.94, -66.92],
        altitude_profile=[0.0, 500.0, 1000.0, 500.0, 0.0],
        highest_alt_index=2,
        highest_altitude=1000.0,
    )
    calibration = {
        "burst_delta": {"lat": 0.2, "lon": -0.1},
        "landing_delta": {"lat": 0.4, "lon": -0.3},
    }

    adjusted_latitudes, adjusted_longitudes = astra_app._apply_sondehub_calibration(profile, calibration)

    assert adjusted_latitudes[0] == pytest.approx(profile.latitudeProfile[0])
    assert adjusted_longitudes[0] == pytest.approx(profile.longitudeProfile[0])
    assert adjusted_latitudes[profile.highestAltIndex] == pytest.approx(profile.latitudeProfile[2] + 0.2)
    assert adjusted_longitudes[profile.highestAltIndex] == pytest.approx(profile.longitudeProfile[2] - 0.1)
    assert adjusted_latitudes[-1] == pytest.approx(profile.latitudeProfile[-1] + 0.4)
    assert adjusted_longitudes[-1] == pytest.approx(profile.longitudeProfile[-1] - 0.3)


def test_build_sondehub_calibration_reports_raw_vs_reference_delta():
    launch_dt = datetime(2026, 4, 1, 12, 0)
    baseline = FakeProfile(
        launch_dt=launch_dt,
        time_vector=[0.0, 60.0, 120.0, 180.0],
        latitude_profile=[18.0, 18.1, 18.2, 18.3],
        longitude_profile=[-67.0, -66.9, -66.8, -66.7],
        altitude_profile=[0.0, 1000.0, 500.0, 0.0],
        highest_alt_index=1,
        highest_altitude=1000.0,
    )
    payload = {
        "prediction": [
            {
                "stage": "ascent",
                "trajectory": [
                    {"latitude": 18.0, "longitude": 293.0, "altitude": 0.0, "datetime": "2026-04-01T12:00:00Z"},
                    {"latitude": 18.25, "longitude": 293.15, "altitude": 1000.0, "datetime": "2026-04-01T12:05:00Z"},
                ],
            },
            {
                "stage": "descent",
                "trajectory": [
                    {"latitude": 18.25, "longitude": 293.15, "altitude": 1000.0, "datetime": "2026-04-01T12:05:00Z"},
                    {"latitude": 18.45, "longitude": 293.45, "altitude": 0.0, "datetime": "2026-04-01T12:20:00Z"},
                ],
            },
        ]
    }

    calibration = astra_app._build_sondehub_calibration(baseline, payload, weight=1.0)

    assert calibration["comparison"]["astra_landing_lat"] == pytest.approx(18.3)
    assert calibration["comparison"]["sondehub_landing_lon"] == pytest.approx(-66.55)
    assert calibration["landing_delta"]["lat"] == pytest.approx(0.15)
    assert calibration["landing_delta"]["lon"] == pytest.approx(0.15)
    assert calibration["comparison"]["landing_delta_km"] > 0
