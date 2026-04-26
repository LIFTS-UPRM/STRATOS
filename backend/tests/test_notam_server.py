from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_servers import notam_server  # noqa: E402


def _simulation_payload() -> dict[str, object]:
    return {
        "status": "success",
        "trajectory_artifact": {
            "launch": {"lat": 18.2, "lon": -67.1, "alt_m": 12.0, "time_s": 0.0},
            "mean_trajectory": [
                {"lat": 18.2, "lon": -67.1, "alt_m": 12.0, "time_s": 0.0},
                {"lat": 18.3, "lon": -67.0, "alt_m": 10000.0, "time_s": 1200.0},
                {"lat": 18.4, "lon": -66.9, "alt_m": 8.0, "time_s": 5000.0},
            ],
            "mean_burst": {"lat": 18.3, "lon": -67.0, "alt_m": 30000.0, "time_s": 2000.0},
            "mean_landing": {"lat": 18.4, "lon": -66.9, "alt_m": 8.0, "time_s": 5000.0},
            "landing_uncertainty_sigma_m": 1200.0,
            "sondehub_reference": None,
        },
    }


def test_get_balloon_no_flight_zone_returns_clear_when_sources_succeed(monkeypatch) -> None:
    async def fake_run_simulation(_params):
        return _simulation_payload()

    async def fake_laminar_restrictions(*_args, **_kwargs):
        return []

    async def fake_sigmets():
        return []

    async def fake_gairmets():
        return []

    monkeypatch.setattr(notam_server, "_run_simulation", fake_run_simulation)
    monkeypatch.setattr(notam_server, "_call_laminar_restrictions", fake_laminar_restrictions)
    monkeypatch.setattr(notam_server, "_call_sigmet", fake_sigmets)
    monkeypatch.setattr(notam_server, "_call_gairmet", fake_gairmets)
    monkeypatch.setattr(
        notam_server,
        "get_settings",
        lambda: SimpleNamespace(laminar_user_key="laminar-key"),
    )

    result = asyncio.run(
        notam_server.get_balloon_no_flight_zone(
            launch_lat=18.2,
            launch_lon=-67.1,
            launch_elevation_m=12.0,
            launch_datetime="2026-04-01T12:00:00Z",
            ascent_rate_ms=5.0,
            burst_altitude_m=30000.0,
            descent_rate_ms=6.0,
            num_runs=3,
        )
    )

    assert result["status"] == "CLEAR"
    assert result["restriction_source_status"] == "AVAILABLE"
    assert result["manual_review_required"] is True
    assert result["restrictions_checked"] == []
    assert result["trajectory_artifact"]["restriction_overlay"]["corridor_geometry"]["type"] == "Polygon"
    assert result["trajectory_artifact"]["restriction_overlay"]["intersections"] == []


def test_get_balloon_no_flight_zone_returns_no_flight_for_blocking_intersection(
    monkeypatch,
) -> None:
    async def fake_run_simulation(_params):
        return _simulation_payload()

    async def fake_laminar_restrictions(*_args, **_kwargs):
        return [
            {
                "id": "notam-1",
                "source": "laminar_notam",
                "severity": "NO_FLIGHT",
                "summary": "TFR active on corridor",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-67.05, 18.24],
                        [-66.95, 18.24],
                        [-66.95, 18.34],
                        [-67.05, 18.34],
                        [-67.05, 18.24],
                    ]],
                },
            }
        ]

    monkeypatch.setattr(notam_server, "_run_simulation", fake_run_simulation)
    monkeypatch.setattr(notam_server, "_call_laminar_restrictions", fake_laminar_restrictions)
    monkeypatch.setattr(notam_server, "_call_sigmet", lambda: asyncio.sleep(0, result=[]))
    monkeypatch.setattr(notam_server, "_call_gairmet", lambda: asyncio.sleep(0, result=[]))
    monkeypatch.setattr(
        notam_server,
        "get_settings",
        lambda: SimpleNamespace(laminar_user_key="laminar-key"),
    )

    result = asyncio.run(
        notam_server.get_balloon_no_flight_zone(
            launch_lat=18.2,
            launch_lon=-67.1,
            launch_elevation_m=12.0,
            launch_datetime="2026-04-01T12:00:00Z",
            ascent_rate_ms=5.0,
            burst_altitude_m=30000.0,
            descent_rate_ms=6.0,
            num_runs=3,
        )
    )

    assert result["status"] == "NO_FLIGHT"
    assert result["restriction_source_status"] == "AVAILABLE"
    assert result["intersections"][0]["id"] == "notam-1"
    assert result["trajectory_artifact"]["restriction_overlay"]["no_flight_zone_geometry"] is not None


def test_get_balloon_no_flight_zone_returns_unverified_when_restriction_source_fails(
    monkeypatch,
) -> None:
    class FakeHttpError(Exception):
        def __init__(self, status_code: int) -> None:
            self.response = SimpleNamespace(status_code=status_code)

    async def fake_run_simulation(_params):
        return _simulation_payload()

    async def fake_laminar_restrictions(*_args, **_kwargs):
        raise FakeHttpError(403)

    async def fake_sigmets():
        return []

    async def fake_gairmets():
        return []

    monkeypatch.setattr(notam_server, "_run_simulation", fake_run_simulation)
    monkeypatch.setattr(notam_server, "_call_laminar_restrictions", fake_laminar_restrictions)
    monkeypatch.setattr(notam_server, "_call_sigmet", fake_sigmets)
    monkeypatch.setattr(notam_server, "_call_gairmet", fake_gairmets)
    monkeypatch.setattr(notam_server.httpx, "HTTPError", FakeHttpError)
    monkeypatch.setattr(
        notam_server,
        "get_settings",
        lambda: SimpleNamespace(laminar_user_key="laminar-key"),
    )

    result = asyncio.run(
        notam_server.get_balloon_no_flight_zone(
            launch_lat=18.2,
            launch_lon=-67.1,
            launch_elevation_m=12.0,
            launch_datetime="2026-04-01T12:00:00Z",
            ascent_rate_ms=5.0,
            burst_altitude_m=30000.0,
            descent_rate_ms=6.0,
            num_runs=3,
        )
    )

    assert result["status"] == "UNVERIFIED"
    assert result["restriction_source_status"] == "UNAVAILABLE"
    assert result["failed_sources"] == [
        {"source": "laminar_notam", "reason": "authorization failed"}
    ]
    assert result["intersections"] == []
