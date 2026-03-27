# STRATOS MCP Tools Reference

This document provides detailed API reference for all MCP (Model Context Protocol) servers in STRATOS.

---

## Tool: check_notam_airspace

- Server name: `liftoff-notam`
- File: `backend/mcp_servers/notam_server.py`
- Purpose: Query dual-source NOTAM databases (FAA + AviationWeather.gov) to assess airspace clearance status for balloon launch site planning.

### Inputs

- `latitude` (float, required): Launch site latitude (-90 to 90).
- `longitude` (float, required): Launch site longitude (-180 to 180).
- `radius_km` (float, default: 25.0): Search radius in kilometers (recommended 25 km for local balloon ops).
- `launch_datetime` (str, default: ""): ISO 8601 launch datetime for informational context (e.g., "2026-03-15T12:00:00Z").
- `faa_client_id` (str, default: ""): FAA API OAuth client ID (from environment config; FAA source optional).
- `faa_client_secret` (str, default: ""): FAA API OAuth client secret (from environment config; FAA source optional).

### Output

- `total_notams` (int): Count of all deduplicated NOTAMs found across sources.
- `relevant_notams` (list[dict]): NOTAMs matching balloon-relevant keywords. Each entry includes:
  - `id` (str): NOTAM identifier.
  - `text` (str): ICAO NOTAM message text.
  - `source` (str): "faa" or "aviationweather".
  - `keywords_matched` (list[str]): Matched keywords (e.g., ["BALLOON", "RESTRICTED"]).
- `clearance_status` (str): Launch clearance recommendation:
  - `NO_CRITICAL_ALERTS`: No critical NOTAMs found; safe to proceed.
  - `REVIEW_REQUIRED`: Balloon-related NOTAMs found; review before launch.
  - `MANUAL_CHECK_REQUIRED`: Critical keywords (TFR, RESTRICTED, PROHIBITED) detected; manual review mandatory.
- `sources_queried` (list[str]): Sources successfully queried (e.g., ["faa", "aviationweather"]).
- `observation_links` (dict): Reference links for manual review:
  - `faa_notam_search`: FAA NOTAM search portal.
  - `aviationweather`: AviationWeather.gov NOTAM viewer.

### Error behavior

- Both FAA and AviationWeather sources degrade gracefully. If one API fails, the call continues with the other source.
- If both sources fail (network error, API down), empty relevant_notams list is returned with `sources_queried` showing attempted sources.
- Input validation: latitude/longitude bounds are checked; invalid inputs return validation error in response.

### Example

**Request:**

```python
check_notam_airspace(
    latitude=18.3264,
    longitude=-67.1425,
    radius_km=25.0,
    launch_datetime="2026-03-26T14:00:00Z",
    faa_client_id="YOUR_CLIENT_ID",
    faa_client_secret="YOUR_CLIENT_SECRET"
)
```

**Response:**

```json
{
  "total_notams": 3,
  "relevant_notams": [
    {
      "id": "2026-AWN-1234",
      "text": "TFR 14 MAR 00 APR 2026. AIRSPACE RESERVATION ESTABLISHED...",
      "source": "faa",
      "keywords_matched": ["TFR"]
    },
    {
      "id": "2026-AWN-5678",
      "text": "UAS OPERATIONS EXPECTED 20-30K FT MARCHES 20-26 2026",
      "source": "aviationweather",
      "keywords_matched": ["UAS"]
    }
  ],
  "clearance_status": "MANUAL_CHECK_REQUIRED",
  "sources_queried": ["faa", "aviationweather"],
  "observation_links": {
    "faa_notam_search": "https://notams.aim.faa.gov/notamSearch/",
    "aviationweather": "https://aviationweather.gov/notam"
  }
}
```

---

## Tool: get_surface_weather

- Server name: `liftoff-weather`
- File: `backend/mcp_servers/weather_server.py`
- Purpose: Fetch hourly surface weather forecast and compute GO/CAUTION/NO-GO launch windows for a balloon launch site.

### Inputs

- `latitude` (float, required): Launch site latitude (-90 to 90).
- `longitude` (float, required): Launch site longitude (-180 to 180).
- `forecast_hours` (int, default: 24): Forecast duration in hours (clamped 1–72). Default 24 hours.

### Output

- `location` (dict): Search location:
  - `latitude`, `longitude`.
- `forecast_hours` (int): Actual forecast window requested.
- `overall_assessment` (str): Summary status:
  - `GO`: All hours pass thresholds.
  - `CAUTION`: Some hours have caution-level concerns (sub-threshold).
  - `NO-GO`: Some hours exceed NO-GO thresholds.
- `go_windows` (int): Count of hours with "GO" status.
- `caution_windows` (int): Count of hours with "CAUTION" status.
- `no_go_windows` (int): Count of hours with "NO-GO" status.
- `hourly_conditions` (list[dict]): Granular hourly forecast. Each entry includes:
  - `time` (str): ISO 8601 datetime.
  - `temperature_c` (float): Temperature in Celsius.
  - `wind_ms` (float): Wind speed at 10 m in m/s.
  - `gust_ms` (float): wind gust magnitude in m/s.
  - `cloud_pct` (float): Cloud cover percentage.
  - `precip_prob_pct` (float): Precipitation probability.
  - `cape_jkg` (float): CAPE (Convective Available Potential Energy) in J/kg.
  - `visibility_m` (float): Visibility in meters.
  - `assessment` (str): Hour-level GO/CAUTION/NO-GO verdict with reason codes.
- `data_freshness_ms` (float): Open-Meteo generation time in milliseconds.
- `observation_links` (dict): Reference links:
  - `windy`: Interactive wind map.
  - `noaa`: NOAA forecast page.
  - `lightning`: Lightning activity map.

### Error behavior

- Network timeout (>10s): Returns error structure with `{"error": "...", "source": "open-meteo"}`.
- Invalid coordinates: Open-Meteo returns 400 Bad Request; error is caught and returned.
- Latitude/longitude bounds validated before API call.

### Example

**Request:**

```python
get_surface_weather(
    latitude=40.7128,
    longitude=-74.0060,
    forecast_hours=24
)
```

**Response:**

```json
{
  "location": {
    "latitude": 40.7128,
    "longitude": -74.0060
  },
  "forecast_hours": 24,
  "overall_assessment": "CAUTION",
  "go_windows": 18,
  "caution_windows": 5,
  "no_go_windows": 1,
  "hourly_conditions": [
    {
      "time": "2026-03-26T12:00",
      "temperature_c": 8.5,
      "wind_ms": 6.2,
      "gust_ms": 10.1,
      "cloud_pct": 65.0,
      "precip_prob_pct": 15.0,
      "cape_jkg": 120.0,
      "visibility_m": 9999.0,
      "assessment": "GO"
    },
    {
      "time": "2026-03-26T13:00",
      "temperature_c": 9.1,
      "wind_ms": 7.5,
      "gust_ms": 11.8,
      "cloud_pct": 75.0,
      "precip_prob_pct": 25.0,
      "cape_jkg": 180.0,
      "visibility_m": 9500.0,
      "assessment": "CAUTION: surface wind 7.5 m/s (threshold 7.0 m/s); gusts 11.8 m/s > 10.0 m/s"
    }
  ],
  "data_freshness_ms": 2.3,
  "observation_links": {
    "windy": "https://www.windy.com/?40.7128,-74.0060,8",
    "noaa": "https://forecast.weather.gov/MapClick.php?lat=40.7128&lon=-74.0060",
    "lightning": "https://www.lightningmaps.org/?lat=40.7128&lon=-74.0060&zoom=8"
  }
}
```

---

## Tool: get_winds_aloft

- Server name: `liftoff-weather`
- File: `backend/mcp_servers/weather_server.py`
- Purpose: Fetch vertical wind profile at 9 pressure levels and detect jet-stream hazards during balloon ascent.

### Inputs

- `latitude` (float, required): Launch site latitude (-90 to 90).
- `longitude` (float, required): Launch site longitude (-180 to 180).
- `forecast_datetime` (str, required): Forecast time in ISO 8601 format (e.g., "2026-03-26T12:00:00Z").

### Output

- `location` (dict): Search location:
  - `latitude`, `longitude`.
- `forecast_time` (str): ISO 8601 time of the wind profile (time-matched from available forecast grid).
- `wind_profile` (list[dict]): Wind data at 9 pressure levels [1000, 925, 850, 700, 500, 400, 300, 250, 200] hPa. Each entry:
  - `pressure_hPa` (int): Pressure level in hectopascals.
  - `altitude_m` (float): Approximate altitude of pressure level in meters.
  - `wind_speed_ms` (float): Wind speed in m/s.
  - `wind_direction_deg` (float): Wind direction in degrees (0–360).
  - `u_ms` (float): U-component (west/east) of wind in m/s.
  - `v_ms` (float): V-component (south/north) of wind in m/s.
- `jet_stream_alert` (bool): True if any level has wind speed > 40 m/s.
- `jet_stream_message` (str): Human-readable alert (e.g., "Jet stream: 250hPa, 200hPa"); null if no jet stream.
- `observation_links` (dict): Reference links (same as surface weather).

### Error behavior

- Invalid `forecast_datetime`: Returns error with available times in 3-day window.
- Time outside forecast window: Returns error with first 6 available times for user guidance.
- Network timeout or API failure: Returns error structure with `{"error": "...", "source": "open-meteo"}`.
- Latitude/longitude validation performed before API call.

### Example

**Request:**

```python
get_winds_aloft(
    latitude=34.0522,
    longitude=-118.2437,
    forecast_datetime="2026-03-26T12:00:00Z"
)
```

**Response:**

```json
{
  "location": {
    "latitude": 34.0522,
    "longitude": -118.2437
  },
  "forecast_time": "2026-03-26T12:00",
  "wind_profile": [
    {
      "pressure_hPa": 1000,
      "altitude_m": 110.0,
      "wind_speed_ms": 5.2,
      "wind_direction_deg": 240.0,
      "u_ms": 3.21,
      "v_ms": -4.12
    },
    {
      "pressure_hPa": 925,
      "altitude_m": 760.0,
      "wind_speed_ms": 8.4,
      "wind_direction_deg": 250.0,
      "u_ms": 5.52,
      "v_ms": -6.18
    },
    {
      "pressure_hPa": 250,
      "altitude_m": 10370.0,
      "wind_speed_ms": 42.1,
      "wind_direction_deg": 270.0,
      "u_ms": 42.1,
      "v_ms": 0.0
    },
    {
      "pressure_hPa": 200,
      "altitude_m": 11820.0,
      "wind_speed_ms": 45.3,
      "wind_direction_deg": 275.0,
      "u_ms": 43.8,
      "v_ms": -7.92
    }
  ],
  "jet_stream_alert": true,
  "jet_stream_message": "Jet stream: 250hPa, 200hPa",
  "observation_links": {
    "windy": "https://www.windy.com/?34.0522,-118.2437,8",
    "noaa": "https://forecast.weather.gov/MapClick.php?lat=34.0522&lon=-118.2437",
    "lightning": "https://www.lightningmaps.org/?lat=34.0522&lon=-118.2437&zoom=8"
  }
}
```

---

## Tool: predict_standard

- Server name: `trajectory`
- File: `backend/mcp_servers/trajectory/server.py`
- Purpose: Predict high-altitude balloon trajectory using NOAA GFS wind data and Tawhiri numerical weather prediction engine.

### Inputs

- `launch_latitude` (float, required): Launch site latitude (-90 to 90).
- `launch_longitude` (float, required): Launch site longitude (-180 to 180).
- `launch_datetime` (str, required): Launch time in ISO 8601 format (e.g., "2026-03-26T12:00:00Z").
- `ascent_rate` (float, required): Balloon ascent rate in meters per second.
- `burst_altitude` (float, required): Burst altitude in meters (typical 25000–35000 m).
- `descent_rate` (float, required): Parachute descent rate in meters per second.
- `launch_altitude` (float, default: 0.0): Launch site altitude in meters above sea level.

### Output

- `ok` (bool): True if prediction succeeded; false on validation or upstream error.
- `profile` (str): Profile name used (always "standard_profile").
- `request` (dict): Echo of request parameters for audit trail.
- `summary` (dict): High-level trajectory summary:
  - `launch_time` (str): ISO 8601 launch time.
  - `burst_time` (str): ISO 8601 burst time (top-of-trajectory).
  - `landing_time` (str): ISO 8601 recovery landing time.
  - `burst_point` (dict):
    - `lat` (float): Burst latitude.
    - `lon` (float): Burst longitude (-180 to 180).
    - `alt` (float): Burst altitude in meters.
    - `datetime` (str): ISO 8601 burst time.
  - `landing_point` (dict):
    - `lat`, `lon`, `alt`, `datetime`: Landing site coordinates and time.
  - `water_landing` (bool): True if landing prediction is over water.
- `path` (list[dict]): Full flattened trajectory (ascent + descent). Each point:
  - `datetime` (str): ISO 8601 time.
  - `lat` (float): Latitude.
  - `lon` (float): Longitude (-180 to 180).
  - `alt` (float): Altitude in meters.
  - `stage` (str): "ascent" or "descent".
- `raw` (dict): Direct Tawhiri response for detailed analysis (includes full GFS wind fields, model run timestamps, etc.).

### Error behavior

- Validation error (invalid latitude/longitude, missing required fields, invalid datetime): Returns `ok=false` with error type "validation" and error message.
- Upstream Tawhiri error (unavailable GFS data, service down): Returns `ok=false` with error type "upstream" and error message.
- Internal exception: Returns `ok=false` with error type "internal"; logged to stderr.
- Network timeout (>10s on Tawhiri API): Raised as upstream error.

### Example

**Request:**

```python
predict_standard(
    launch_latitude=18.3264,
    launch_longitude=-67.1425,
    launch_datetime="2026-03-26T14:00:00Z",
    launch_altitude=200.0,
    ascent_rate=5.0,
    burst_altitude=32000.0,
    descent_rate=6.0
)
```

**Response:**

```json
{
  "ok": true,
  "profile": "standard_profile",
  "request": {
    "launch_latitude": 18.3264,
    "launch_longitude": -67.1425,
    "launch_datetime": "2026-03-26T14:00:00Z",
    "launch_altitude": 200.0,
    "ascent_rate": 5.0,
    "burst_altitude": 32000.0,
    "descent_rate": 6.0
  },
  "summary": {
    "launch_time": "2026-03-26T14:00:00Z",
    "burst_time": "2026-03-26T15:33:20Z",
    "landing_time": "2026-03-26T17:12:45Z",
    "burst_point": {
      "lat": 18.4521,
      "lon": -66.8932,
      "alt": 32000.0,
      "datetime": "2026-03-26T15:33:20Z"
    },
    "landing_point": {
      "lat": 18.6234,
      "lon": -66.4521,
      "alt": 0.0,
      "datetime": "2026-03-26T17:12:45Z"
    },
    "water_landing": false
  },
  "path": [
    {
      "datetime": "2026-03-26T14:00:00Z",
      "lat": 18.3264,
      "lon": -67.1425,
      "alt": 200.0,
      "stage": "ascent"
    },
    {
      "datetime": "2026-03-26T14:30:15Z",
      "lat": 18.3845,
      "lon": -67.1256,
      "alt": 9500.0,
      "stage": "ascent"
    },
    {
      "datetime": "2026-03-26T15:33:20Z",
      "lat": 18.4521,
      "lon": -66.8932,
      "alt": 32000.0,
      "stage": "ascent"
    },
    {
      "datetime": "2026-03-26T16:15:30Z",
      "lat": 18.5234,
      "lon": -66.6234,
      "alt": 20000.0,
      "stage": "descent"
    },
    {
      "datetime": "2026-03-26T17:12:45Z",
      "lat": 18.6234,
      "lon": -66.4521,
      "alt": 0.0,
      "stage": "descent"
    }
  ],
  "raw": {
    "dataset": "NOAA GFS 0.25°",
    "run_time": "2026-03-26T12:00:00Z",
    "model_data": {}
  }
}
```

---

## Tool: health_check

- Server name: `trajectory`
- File: `backend/mcp_servers/trajectory/server.py`
- Purpose: Verify that the Tawhiri trajectory service is configured and operational.

### Inputs

None.

### Output

- `ok` (bool): True if Tawhiri is configured and ready; false otherwise.
- `tawhiri_url` (str): Configured Tawhiri base URL or "(not configured)".
- `message` (str): Human-readable status message.

### Error behavior

- No network calls are made; only environment variable check (`TAWHIRI_BASE_URL`).
- Always returns success structure; `ok` field indicates actual readiness.

### Example

**Request:**

```python
health_check()
```

**Response (configured):**

```json
{
  "ok": true,
  "tawhiri_url": "https://tawhiri.example.com/v1",
  "message": "Tawhiri wrapper ready"
}
```

**Response (not configured):**

```json
{
  "ok": false,
  "tawhiri_url": "(not configured)",
  "message": "TAWHIRI_BASE_URL not set"
}
```

---

## Tool: get_supported_profiles

- Server name: `trajectory`
- File: `backend/mcp_servers/trajectory/server.py`
- Purpose: List all available trajectory prediction profiles and their input requirements.

### Inputs

None.

### Output

- `profiles` (list[dict]): Array of available profiles. Each entry:
  - `name` (str): Profile identifier (e.g., "standard_profile").
  - `description` (str): Human-readable purpose.
  - `required_fields` (list[str]): Mandatory parameters for this profile.
  - `optional_fields` (list[str]): Optional parameters with defaults.

### Error behavior

- No external dependencies; always returns full profile list.

### Example

**Request:**

```python
get_supported_profiles()
```

**Response:**

```json
{
  "profiles": [
    {
      "name": "standard_profile",
      "description": "Standard ascent-burst-descent balloon trajectory using NOAA GFS winds",
      "required_fields": [
        "launch_latitude",
        "launch_longitude",
        "launch_datetime",
        "ascent_rate",
        "burst_altitude",
        "descent_rate"
      ],
      "optional_fields": [
        "launch_altitude"
      ]
    }
  ]
}
```

---

## Running MCP Servers Locally

From the `backend/` directory:

```bash
# NOTAM server
python -m mcp_servers.notam_server

# Weather server
python -m mcp_servers.weather_server

# Trajectory server
python -m mcp_servers.trajectory.server
```

Each server listens on `stdio` by default and is ready for MCP client connections.

---

## Environment Variables

### Weather & Notam Servers

- No required environment variables (both use public APIs).
- FAA NOTAM access requires credentials passed at call time.

### Trajectory Server

- `TAWHIRI_BASE_URL` (required): Base URL of Tawhiri service (e.g., <https://prediction.cusf.co.uk/api/v1>).

---

## Thresholds & Limits

### Weather Assessment (from PRD §7.1)

| Metric              | CAUTION   | NO-GO      |
|---------------------|-----------|------------|
| Surface wind (10 m) | ≥ 7.0 m/s | > 10.0 m/s |
| Wind gusts (10 m)   | —         | > 12.0 m/s |
| Cloud cover         | > 80%     | —          |
| Precip probability  | > 30%     | —          |
| CAPE                | —         | > 500 J/kg |
| Visibility          | —         | < 3000 m   |

### Winds Aloft

- **Jet stream alert**: Wind speed > 40 m/s at any level.

### Trajectory Limits

- Ascent rate: 0.1–10.0 m/s (typical 4–6 m/s).
- Burst altitude: 15000–40000 m (typical 25000–35000 m).
- Descent rate: 1.0–15.0 m/s (parachute-dependent).

---

## Integration Notes

- All tools return JSON-serializable responses suitable for LLM agents.
- Errors are returned in-band (no exceptions raised); check `ok` field or error structures.
- Timestamps are ISO 8601 UTC unless otherwise noted.
- Coordinates use WGS84 datum; longitude clamped to ±180°.
- All network timeouts set to 10 seconds; circuit-break on repeated failures.
