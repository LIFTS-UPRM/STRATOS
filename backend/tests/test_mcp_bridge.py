from __future__ import annotations

import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vendor.hab_predictor import mcp_bridge


def test_dispatch_simulation_preserves_trajectory_artifact(monkeypatch) -> None:
    def fake_run_simulation(_: dict[str, object]) -> dict[str, object]:
        return {
            "status": "success",
            "num_runs": 2,
            "trajectory_run1": [
                {"lat": 18.2, "lon": -67.1, "alt_m": 12.0, "time_s": 0.0},
                {"lat": 18.25, "lon": -67.05, "alt_m": 5000.0, "time_s": 600.0},
                {"lat": 18.4, "lon": -66.9, "alt_m": 8.0, "time_s": 5000.0},
            ],
            "sondehub": {
                "status": "applied",
                "provider": "sondehub-tawhiri",
                "reference": {
                    "landing": {
                        "lat": 18.4,
                        "lon": -66.9,
                        "alt_m": 8.0,
                        "datetime": "2026-04-01T13:23:20Z",
                    },
                    "trajectory": [
                        {
                            "stage": "ascent",
                            "lat": 18.2,
                            "lon": -67.1,
                            "alt_m": 12.0,
                            "datetime": "2026-04-01T12:00:00Z",
                        },
                        {
                            "stage": "descent",
                            "lat": 18.4,
                            "lon": -66.9,
                            "alt_m": 8.0,
                            "datetime": "2026-04-01T13:23:20Z",
                        },
                    ],
                },
            },
            "trajectory_artifact": {
                "launch": {
                    "lat": 18.2,
                    "lon": -67.1,
                    "alt_m": 12.0,
                    "time_s": 0.0,
                },
                "mean_trajectory": [
                    {"lat": 18.2, "lon": -67.1, "alt_m": 12.0, "time_s": 0.0},
                    {"lat": 18.3, "lon": -67.0, "alt_m": 30000.0, "time_s": 2000.0},
                ],
                "mean_burst": {
                    "lat": 18.3,
                    "lon": -67.0,
                    "alt_m": 30000.0,
                    "time_s": 2000.0,
                },
                "mean_landing": {
                    "lat": 18.4,
                    "lon": -66.9,
                    "alt_m": 8.0,
                    "time_s": 5000.0,
                },
                "landing_uncertainty_sigma_m": 1200.0,
                "sondehub_reference": {
                    "provider": "sondehub-tawhiri",
                    "status": "compared",
                    "request": {
                        "profile": "standard_profile",
                        "launch_datetime": "2026-04-01T12:00:00Z",
                        "ascent_rate": 5.0,
                        "burst_altitude": 30000.0,
                        "descent_rate": 6.0,
                    },
                    "trajectory": [
                        {"lat": 18.2, "lon": -67.1, "alt_m": 12.0, "time_s": 0.0},
                        {"lat": 18.4, "lon": -66.9, "alt_m": 8.0, "time_s": 5000.0},
                    ],
                    "landing": {
                        "lat": 18.4,
                        "lon": -66.9,
                        "alt_m": 8.0,
                        "time_s": 5000.0,
                    },
                },
            },
        }

    monkeypatch.setattr(mcp_bridge.hab_app, "run_simulation", fake_run_simulation)

    payload = json.loads(
        mcp_bridge._dispatch(
            "astra_run_simulation",
            {"launch_lat": 18.2, "launch_lon": -67.1},
        )
    )

    assert payload["status"] == "success"
    assert payload["num_runs"] == 2
    assert payload["trajectory_run1"][1]["lon"] == -67.05
    assert payload["sondehub"]["reference"]["landing"]["lon"] == -66.9
    assert payload["sondehub"]["reference"]["trajectory"][0]["stage"] == "ascent"
    assert payload["trajectory_artifact"]["mean_landing"]["lat"] == 18.4
    assert payload["trajectory_artifact"]["landing_uncertainty_sigma_m"] == 1200.0
    assert payload["trajectory_artifact"]["sondehub_reference"]["trajectory"][1]["lat"] == 18.4
    assert payload["trajectory_artifact"]["sondehub_reference"]["request"]["ascent_rate"] == 5.0
