"""Airspace MCP server — balloon-specific no-flight-zone evaluation."""
from __future__ import annotations

import math
from typing import Any

import httpx
from fastmcp import FastMCP

from app.config import get_settings
from mcp_servers.sondehub_server import SondehubSimulationInput, _run_simulation


mcp = FastMCP("liftoff-airspace")

_AW_SIGMET_URL = "https://aviationweather.gov/api/data/sigmet"
_AW_GAIRMET_URL = "https://aviationweather.gov/api/data/gairmet"
_LAMINAR_NOTAMS_URL = "https://api.laminardata.aero/v2/notams"

_EARTH_RADIUS_KM = 6371.0
_PATH_BUFFER_KM = 5.0
_MIN_TERMINAL_BUFFER_KM = 5.0
_MAX_RESTRICTIONS_RETURNED = 50
_MAX_INTERSECTIONS_RETURNED = 20
_BLOCKING_KEYWORDS = {"TFR", "RESTRICTED", "PROHIBITED"}
_CAUTION_KEYWORDS = {
    "BALLOON",
    "UAS",
    "DRONE",
    "AIRSPACE",
    "TEMPORARY FLIGHT",
    "SIGMET",
    "AIRMET",
    "IFR",
    "TURB",
    "CONVECTIVE",
}


def _summarize_http_error(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code is not None:
        if status_code == 401:
            return "authentication failed"
        if status_code == 403:
            return "authorization failed"
        return f"http {status_code}"
    return exc.__class__.__name__


def _record_source_failure(
    failures: list[dict[str, str]],
    source: str,
    exc: Exception,
) -> None:
    failures.append({"source": source, "reason": _summarize_http_error(exc)})


def _clip_summary(text: str, max_len: int = 180) -> str:
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= max_len:
        return cleaned
    return f"{cleaned[:max_len - 1].rstrip()}…"


def _coerce_coordinate(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _normalize_longitude_delta_deg(lon_a: float, lon_b: float) -> float:
    return ((lon_b - lon_a + 180.0) % 360.0) - 180.0


def _point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i, point in enumerate(ring):
        xi, yi = point
        xj, yj = ring[j]
        intersects = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def _point_in_geometry(
    latitude: float,
    longitude: float,
    geometry: dict[str, Any] | None,
) -> bool:
    if not isinstance(geometry, dict):
        return False
    geom_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geom_type == "Polygon" and isinstance(coordinates, list):
        outer_ring = coordinates[0] if coordinates else []
        return bool(outer_ring) and _point_in_ring(longitude, latitude, outer_ring)
    if geom_type == "MultiPolygon" and isinstance(coordinates, list):
        for polygon in coordinates:
            outer_ring = polygon[0] if polygon else []
            if outer_ring and _point_in_ring(longitude, latitude, outer_ring):
                return True
    return False


def _extract_geometry_points(geometry: dict[str, Any] | None) -> list[tuple[float, float]]:
    if not isinstance(geometry, dict):
        return []

    geom_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geom_type == "Point" and isinstance(coordinates, list) and len(coordinates) >= 2:
        lon = _coerce_coordinate(coordinates[0])
        lat = _coerce_coordinate(coordinates[1])
        return [(lat, lon)] if lat is not None and lon is not None else []

    points: list[tuple[float, float]] = []

    def visit(node: Any) -> None:
        if isinstance(node, list) and len(node) >= 2 and not isinstance(node[0], list):
            lon = _coerce_coordinate(node[0])
            lat = _coerce_coordinate(node[1])
            if lat is not None and lon is not None:
                points.append((lat, lon))
            return
        if isinstance(node, list):
            for child in node:
                visit(child)
            return
        if isinstance(node, dict) and node.get("type") == "GeometryCollection":
            for child in node.get("geometries", []):
                visit(child.get("coordinates"))

    if geom_type == "GeometryCollection":
        for child in geometry.get("geometries", []):
            if isinstance(child, dict):
                points.extend(_extract_geometry_points(child))
    else:
        visit(coordinates)
    return points


def _geometry_bbox(geometry: dict[str, Any] | None) -> dict[str, float] | None:
    points = _extract_geometry_points(geometry)
    if not points:
        return None
    lats = [point[0] for point in points]
    lons = [point[1] for point in points]
    return {
        "min_lat": min(lats),
        "max_lat": max(lats),
        "min_lon": min(lons),
        "max_lon": max(lons),
    }


def _bbox_intersects(
    left: dict[str, float] | None,
    right: dict[str, float] | None,
) -> bool:
    if left is None or right is None:
        return False
    return not (
        left["max_lat"] < right["min_lat"]
        or left["min_lat"] > right["max_lat"]
        or left["max_lon"] < right["min_lon"]
        or left["min_lon"] > right["max_lon"]
    )


def _km_to_latitude_degrees(radius_km: float) -> float:
    return radius_km / 111.32


def _km_to_longitude_degrees(radius_km: float, latitude: float) -> float:
    cos_lat = math.cos(math.radians(latitude))
    if abs(cos_lat) < 1e-6:
        return 180.0
    return radius_km / (111.32 * abs(cos_lat))


def _circle_polygon(latitude: float, longitude: float, radius_km: float) -> dict[str, Any]:
    coordinates: list[list[float]] = []
    lat_delta = _km_to_latitude_degrees(radius_km)
    lon_delta = _km_to_longitude_degrees(radius_km, latitude)
    for step in range(0, 25):
        angle = (2.0 * math.pi * step) / 24.0
        coordinates.append(
            [
                longitude + math.cos(angle) * lon_delta,
                latitude + math.sin(angle) * lat_delta,
            ]
        )
    coordinates.append(coordinates[0])
    return {"type": "Polygon", "coordinates": [coordinates]}


def _bbox_polygon(
    points: list[dict[str, float]],
    buffer_km: float,
) -> tuple[dict[str, Any], dict[str, float]]:
    lats = [point["lat"] for point in points]
    lons = [point["lon"] for point in points]
    center_lat = sum(lats) / len(lats)
    lat_delta = _km_to_latitude_degrees(buffer_km)
    lon_delta = _km_to_longitude_degrees(buffer_km, center_lat)
    bbox = {
        "min_lat": min(lats) - lat_delta,
        "max_lat": max(lats) + lat_delta,
        "min_lon": min(lons) - lon_delta,
        "max_lon": max(lons) + lon_delta,
    }
    polygon = {
        "type": "Polygon",
        "coordinates": [[
            [bbox["min_lon"], bbox["min_lat"]],
            [bbox["max_lon"], bbox["min_lat"]],
            [bbox["max_lon"], bbox["max_lat"]],
            [bbox["min_lon"], bbox["max_lat"]],
            [bbox["min_lon"], bbox["min_lat"]],
        ]],
    }
    return polygon, bbox


def _distance_point_to_segment_km(
    latitude: float,
    longitude: float,
    start: dict[str, float],
    end: dict[str, float],
) -> float:
    reference_lat = math.radians((start["lat"] + end["lat"] + latitude) / 3.0)
    start_x = start["lon"] * math.cos(reference_lat) * 111.32
    start_y = start["lat"] * 111.32
    end_x = (start["lon"] + _normalize_longitude_delta_deg(start["lon"], end["lon"])) * math.cos(reference_lat) * 111.32
    end_y = end["lat"] * 111.32
    point_x = (start["lon"] + _normalize_longitude_delta_deg(start["lon"], longitude)) * math.cos(reference_lat) * 111.32
    point_y = latitude * 111.32

    dx = end_x - start_x
    dy = end_y - start_y
    if dx == 0.0 and dy == 0.0:
        return math.hypot(point_x - start_x, point_y - start_y)

    projection = ((point_x - start_x) * dx + (point_y - start_y) * dy) / (dx * dx + dy * dy)
    projection = max(0.0, min(1.0, projection))
    closest_x = start_x + projection * dx
    closest_y = start_y + projection * dy
    return math.hypot(point_x - closest_x, point_y - closest_y)


def _distance_point_to_route_km(
    latitude: float,
    longitude: float,
    route_points: list[dict[str, float]],
) -> float:
    if not route_points:
        return float("inf")
    if len(route_points) == 1:
        return _haversine_km(latitude, longitude, route_points[0]["lat"], route_points[0]["lon"])
    distances = [
        _distance_point_to_segment_km(latitude, longitude, route_points[index], route_points[index + 1])
        for index in range(len(route_points) - 1)
    ]
    return min(distances) if distances else float("inf")


def _geometry_from_aviationweather_coords(coords: Any) -> dict[str, Any] | None:
    if not isinstance(coords, list):
        return None
    points: list[list[float]] = []
    for point in coords:
        if not isinstance(point, dict):
            continue
        lat = _coerce_coordinate(point.get("lat"))
        lon = _coerce_coordinate(point.get("lon"))
        if lat is None or lon is None:
            continue
        points.append([lon, lat])
    if not points:
        return None
    if len(points) == 1:
        return {"type": "Point", "coordinates": points[0]}
    if len(points) == 2:
        return {"type": "LineString", "coordinates": points}
    if points[0] != points[-1]:
        points.append(points[0])
    return {"type": "Polygon", "coordinates": [points]}


def _extract_notam_text(properties: dict[str, Any]) -> str:
    text = properties.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    translations = properties.get("translations")
    if isinstance(translations, list):
        for translation in translations:
            if not isinstance(translation, dict):
                continue
            simple_text = translation.get("simpleText")
            if isinstance(simple_text, str) and simple_text.strip():
                return simple_text.strip()
    return ""


def _classify_restriction_severity(text: str, qcode: str | None = None) -> str:
    upper_text = text.upper()
    if any(keyword in upper_text for keyword in _BLOCKING_KEYWORDS):
        return "NO_FLIGHT"
    if isinstance(qcode, str) and qcode.upper().startswith("QRT"):
        return "NO_FLIGHT"
    if any(keyword in upper_text for keyword in _CAUTION_KEYWORDS):
        return "CAUTION"
    return "CAUTION"


def _normalize_laminar_restriction(feature: dict[str, Any]) -> dict[str, Any]:
    properties = feature.get("properties", {})
    text = _extract_notam_text(properties) or str(feature)
    severity = _classify_restriction_severity(text, properties.get("qcode"))
    return {
        "id": str(feature.get("id") or abs(hash(str(feature)))),
        "source": "laminar_notam",
        "severity": severity,
        "summary": _clip_summary(text),
        "geometry": feature.get("geometry"),
        "effective_start": properties.get("effectiveStart"),
        "effective_end": properties.get("effectiveEnd"),
        "raw_text": text,
    }


def _normalize_sigmet(item: dict[str, Any]) -> dict[str, Any]:
    text = item.get("rawAirSigmet") or item.get("hazard") or str(item)
    return {
        "id": str(item.get("airsigmetId") or item.get("id") or abs(hash(str(item)))),
        "source": "aviationweather_sigmet",
        "severity": "CAUTION",
        "summary": _clip_summary(text),
        "geometry": _geometry_from_aviationweather_coords(item.get("coords")),
        "effective_start": item.get("creationTime"),
        "effective_end": item.get("validTimeTo"),
        "raw_text": text,
    }


def _normalize_gairmet(item: dict[str, Any]) -> dict[str, Any]:
    text = item.get("rawText") or item.get("due_to") or item.get("hazard") or str(item)
    return {
        "id": str(item.get("airmetId") or item.get("tag") or item.get("id") or abs(hash(str(item)))),
        "source": "aviationweather_gairmet",
        "severity": "CAUTION",
        "summary": _clip_summary(text),
        "geometry": _geometry_from_aviationweather_coords(item.get("coords")),
        "effective_start": item.get("issueTime"),
        "effective_end": item.get("expireTime"),
        "raw_text": text,
    }


async def _call_laminar_restrictions(
    user_key: str,
    search_geometry: dict[str, Any],
) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            _LAMINAR_NOTAMS_URL,
            params={"user_key": user_key},
            headers={
                "Accept": "application/geo+json",
                "Content-Type": "application/geo+json",
            },
            json=search_geometry,
        )
        response.raise_for_status()

    payload = response.json()
    features = payload.get("features", []) if isinstance(payload, dict) else []
    return [
        _normalize_laminar_restriction(feature)
        for feature in features
        if isinstance(feature, dict)
    ]


async def _call_sigmet() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(_AW_SIGMET_URL, params={"format": "json"})
        response.raise_for_status()

    payload = response.json()
    items = payload if isinstance(payload, list) else payload.get("data", [])
    return [
        _normalize_sigmet(item)
        for item in items
        if isinstance(item, dict)
    ]


async def _call_gairmet() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(_AW_GAIRMET_URL, params={"format": "json"})
        response.raise_for_status()

    payload = response.json()
    items = payload if isinstance(payload, list) else payload.get("data", [])
    return [
        _normalize_gairmet(item)
        for item in items
        if isinstance(item, dict)
    ]


def _restriction_intersects_corridor(
    restriction: dict[str, Any],
    route_points: list[dict[str, float]],
    landing_point: dict[str, float] | None,
    route_bbox: dict[str, float] | None,
    path_buffer_km: float,
    terminal_buffer_km: float,
) -> bool:
    geometry = restriction.get("geometry")
    if not isinstance(geometry, dict):
        return False

    geometry_bbox = _geometry_bbox(geometry)
    if geometry_bbox is not None and route_bbox is not None and not _bbox_intersects(route_bbox, geometry_bbox):
        return False

    for point in route_points:
        if _point_in_geometry(point["lat"], point["lon"], geometry):
            return True
    if landing_point and _point_in_geometry(landing_point["lat"], landing_point["lon"], geometry):
        return True

    for lat, lon in _extract_geometry_points(geometry):
        if _distance_point_to_route_km(lat, lon, route_points) <= path_buffer_km:
            return True
        if landing_point and _haversine_km(lat, lon, landing_point["lat"], landing_point["lon"]) <= terminal_buffer_km:
            return True
    return False


def _build_corridor_context(trajectory_artifact: dict[str, Any]) -> dict[str, Any]:
    route_points = [
        point
        for point in trajectory_artifact.get("mean_trajectory", [])
        if isinstance(point, dict) and point.get("lat") is not None and point.get("lon") is not None
    ]
    launch = trajectory_artifact.get("launch")
    if isinstance(launch, dict) and launch.get("lat") is not None and launch.get("lon") is not None:
        if not route_points or route_points[0] != launch:
            route_points.insert(0, launch)

    landing_point = trajectory_artifact.get("mean_landing")
    landing_sigma_km = max(
        float(trajectory_artifact.get("landing_uncertainty_sigma_m", 0.0)) / 1000.0,
        _MIN_TERMINAL_BUFFER_KM,
    )
    if isinstance(landing_point, dict) and landing_point.get("lat") is not None and landing_point.get("lon") is not None:
        geometry_points = route_points + [landing_point]
    else:
        geometry_points = route_points

    buffer_km = max(_PATH_BUFFER_KM, landing_sigma_km)
    corridor_geometry, route_bbox = _bbox_polygon(geometry_points, buffer_km)
    landing_zone_geometry = None
    if isinstance(landing_point, dict) and landing_point.get("lat") is not None and landing_point.get("lon") is not None:
        landing_zone_geometry = _circle_polygon(
            float(landing_point["lat"]),
            float(landing_point["lon"]),
            landing_sigma_km,
        )

    return {
        "route_points": route_points,
        "landing_point": landing_point if isinstance(landing_point, dict) else None,
        "path_buffer_km": _PATH_BUFFER_KM,
        "terminal_buffer_km": landing_sigma_km,
        "corridor_geometry": corridor_geometry,
        "landing_zone_geometry": landing_zone_geometry,
        "route_bbox": route_bbox,
    }


def _restriction_brief(restriction: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": restriction["id"],
        "source": restriction["source"],
        "severity": restriction["severity"],
        "summary": restriction["summary"],
        "effective_start": restriction.get("effective_start"),
        "effective_end": restriction.get("effective_end"),
    }


def _intersection_payload(restriction: dict[str, Any]) -> dict[str, Any]:
    payload = _restriction_brief(restriction)
    payload["geometry"] = restriction.get("geometry")
    return payload


def _build_no_flight_zone_geometry(intersections: list[dict[str, Any]]) -> dict[str, Any] | None:
    geometries = [
        intersection.get("geometry")
        for intersection in intersections
        if isinstance(intersection.get("geometry"), dict)
    ]
    if not geometries:
        return None
    if len(geometries) == 1:
        return geometries[0]
    return {"type": "GeometryCollection", "geometries": geometries}


def _derive_status(
    restriction_source_status: str,
    intersections: list[dict[str, Any]],
) -> str:
    if restriction_source_status != "AVAILABLE":
        return "UNVERIFIED"
    if any(intersection["severity"] == "NO_FLIGHT" for intersection in intersections):
        return "NO_FLIGHT"
    if intersections:
        return "CAUTION"
    return "CLEAR"


def _build_summary(
    status: str,
    restriction_source_status: str,
    intersections: list[dict[str, Any]],
    failed_sources: list[dict[str, str]],
) -> str:
    if restriction_source_status != "AVAILABLE":
        failure_summary = ", ".join(
            f"{failure['source']} ({failure['reason']})"
            for failure in failed_sources
        ) or "restriction data unavailable"
        return (
            "Restriction lookup is incomplete for the balloon corridor. "
            f"Source issues: {failure_summary}. Manual review is required."
        )
    if status == "CLEAR":
        return "No intersecting no-flight restrictions were found along the predicted balloon corridor."
    if status == "NO_FLIGHT":
        return (
            "Blocking airspace restrictions intersect the predicted balloon corridor. "
            "Do not treat this launch as clear."
        )
    return (
        "Advisory or ambiguous airspace restrictions intersect the predicted balloon corridor. "
        "Use caution and complete manual review before launch."
    )


async def _compute_balloon_no_flight_zone(payload: dict[str, Any]) -> dict[str, Any]:
    params = SondehubSimulationInput.model_validate(payload)
    simulation = await _run_simulation(params)
    trajectory_artifact = simulation["trajectory_artifact"]
    corridor = _build_corridor_context(trajectory_artifact)

    settings = get_settings()
    laminar_user_key = settings.laminar_user_key.strip()

    sources_queried: list[str] = []
    failed_sources: list[dict[str, str]] = []
    successful_restriction_sources: list[str] = []
    restrictions: list[dict[str, Any]] = []

    if laminar_user_key:
        try:
            laminar_restrictions = await _call_laminar_restrictions(
                laminar_user_key,
                corridor["corridor_geometry"],
            )
            restrictions.extend(laminar_restrictions)
            sources_queried.append("laminar_notam")
            successful_restriction_sources.append("laminar_notam")
        except httpx.HTTPError as exc:
            _record_source_failure(failed_sources, "laminar_notam", exc)

    try:
        sigmets = await _call_sigmet()
        restrictions.extend(sigmets)
        sources_queried.append("aviationweather_sigmet")
    except httpx.HTTPError as exc:
        _record_source_failure(failed_sources, "aviationweather_sigmet", exc)

    try:
        gairmets = await _call_gairmet()
        restrictions.extend(gairmets)
        sources_queried.append("aviationweather_gairmet")
    except httpx.HTTPError as exc:
        _record_source_failure(failed_sources, "aviationweather_gairmet", exc)

    restrictions_checked = [
        restriction
        for restriction in restrictions
        if _restriction_intersects_corridor(
            restriction,
            corridor["route_points"],
            corridor["landing_point"],
            corridor["route_bbox"],
            corridor["path_buffer_km"],
            corridor["terminal_buffer_km"],
        )
    ]
    intersections = restrictions_checked[:_MAX_INTERSECTIONS_RETURNED]
    restriction_source_status = (
        "AVAILABLE" if successful_restriction_sources else "UNAVAILABLE"
    )
    status = _derive_status(restriction_source_status, intersections)

    trajectory_artifact["restriction_overlay"] = {
        "restriction_source_status": restriction_source_status,
        "corridor_geometry": corridor["corridor_geometry"],
        "landing_zone_geometry": corridor["landing_zone_geometry"],
        "no_flight_zone_geometry": _build_no_flight_zone_geometry(intersections),
        "intersections": [_intersection_payload(intersection) for intersection in intersections],
    }

    return {
        "status": status,
        "summary": _build_summary(
            status,
            restriction_source_status,
            intersections,
            failed_sources,
        ),
        "trajectory_artifact": trajectory_artifact,
        "restriction_source_status": restriction_source_status,
        "restrictions_checked": [
            _restriction_brief(restriction)
            for restriction in restrictions_checked[:_MAX_RESTRICTIONS_RETURNED]
        ],
        "failed_sources": failed_sources,
        "intersections": [_intersection_payload(intersection) for intersection in intersections],
        "sources_queried": sources_queried,
        "manual_review_required": True,
        "observation_links": {
            "faa_notam_search": "https://notams.aim.faa.gov/notamSearch/",
            "laminar_notam_docs": "https://developer.laminardata.aero/documentation/notamdata/v2",
            "aviationweather_sigmet": "https://aviationweather.gov/",
            "aviationweather_gairmet": "https://aviationweather.gov/",
        },
    }


@mcp.tool(name="get_balloon_no_flight_zone")
async def get_balloon_no_flight_zone(
    launch_lat: float | None = None,
    launch_lon: float | None = None,
    launch_elevation_m: float | None = None,
    launch_datetime: str | None = None,
    ascent_rate_ms: float | None = None,
    burst_altitude_m: float | None = None,
    descent_rate_ms: float | None = None,
    num_runs: int | None = None,
    seed: int | None = None,
    ascent_rate_stddev_pct: float = 5.0,
    burst_altitude_stddev_m: float = 1000.0,
    descent_rate_stddev_pct: float = 10.0,
    launch_time_stddev_min: float = 10.0,
) -> dict[str, Any]:
    """Return the balloon-specific no-flight-zone result for a predicted corridor."""
    try:
        return await _compute_balloon_no_flight_zone(
            {
                "launch_lat": launch_lat,
                "launch_lon": launch_lon,
                "launch_elevation_m": launch_elevation_m,
                "launch_datetime": launch_datetime,
                "ascent_rate_ms": ascent_rate_ms,
                "burst_altitude_m": burst_altitude_m,
                "descent_rate_ms": descent_rate_ms,
                "num_runs": num_runs,
                "seed": seed,
                "ascent_rate_stddev_pct": ascent_rate_stddev_pct,
                "burst_altitude_stddev_m": burst_altitude_stddev_m,
                "descent_rate_stddev_pct": descent_rate_stddev_pct,
                "launch_time_stddev_min": launch_time_stddev_min,
            }
        )
    except Exception as exc:
        return {
            "status": "UNVERIFIED",
            "summary": f"Unable to compute the balloon no-flight zone: {exc}",
            "trajectory_artifact": None,
            "restriction_source_status": "UNAVAILABLE",
            "restrictions_checked": [],
            "failed_sources": [{"source": "balloon_no_flight_zone", "reason": str(exc)}],
            "intersections": [],
            "sources_queried": [],
            "manual_review_required": True,
        }


async def check_airspace_hazards(
    latitude: float,
    longitude: float,
    radius_km: float = 25.0,
    launch_datetime: str = "",
) -> dict[str, Any]:
    """Compatibility helper retained for legacy callers.

    This compatibility path no longer performs a trajectory-aware restriction
    lookup and should not be exposed to the chat model.
    """
    del radius_km
    return {
        "hazard_status": "MANUAL_CHECK_REQUIRED",
        "summary": (
            "Legacy launch-radius airspace checks are no longer authoritative. "
            "Use get_balloon_no_flight_zone with a full trajectory profile."
        ),
        "latitude": latitude,
        "longitude": longitude,
        "launch_datetime": launch_datetime,
        "manual_notam_check_required": True,
    }


if __name__ == "__main__":
    mcp.run()
