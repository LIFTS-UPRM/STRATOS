# STRATOS MCP Tools Reference

This document describes the MCP tools currently exposed by STRATOS.

---

## Tool: get_balloon_no_flight_zone

- Server name: `liftoff-airspace`
- File: `backend/mcp_servers/notam_server.py`
- Purpose: Run a SondeHub corridor prediction, overlay dynamic restriction
  geometry, and return the balloon-specific no-flight-zone result.

### Inputs

- `launch_lat` (float, required): Launch latitude.
- `launch_lon` (float, required): Launch longitude.
- `launch_elevation_m` (float, required): Launch elevation in metres.
- `launch_datetime` (str, required): ISO 8601 launch time.
- `ascent_rate_ms` (float, required): Nominal ascent rate in m/s.
- `burst_altitude_m` (float, required): Nominal burst altitude in metres.
- `descent_rate_ms` (float, required): Nominal descent rate in m/s.
- `num_runs` (int, required): Number of Monte Carlo runs.
- `seed` (int, optional): Deterministic Monte Carlo seed.
- `ascent_rate_stddev_pct` (float, default: 5): Ascent-rate spread.
- `burst_altitude_stddev_m` (float, default: 1000): Burst-altitude spread.
- `descent_rate_stddev_pct` (float, default: 10): Descent-rate spread.
- `launch_time_stddev_min` (float, default: 10): Launch-time spread.

### Output

- `status`: `CLEAR`, `CAUTION`, `NO_FLIGHT`, or `UNVERIFIED`.
- `summary`: Human-readable no-flight-zone conclusion.
- `trajectory_artifact`: Existing trajectory artifact plus restriction overlays for map rendering.
- `restriction_source_status`: `AVAILABLE` or `UNAVAILABLE`.
- `restrictions_checked`: Restriction records intersecting the corridor.
- `failed_sources`: Upstream source failures, including auth/authorization issues.
- `intersections`: Restriction geometries intersecting the corridor.
- `sources_queried`: Sources successfully queried.
- `manual_review_required`: Always `true`.
- `observation_links`: Reference links for manual review.

### Error behavior

- Returns `UNVERIFIED` when no restriction source completes successfully.
- Validation errors and upstream SondeHub failures are surfaced through the tool result.

---

## Tool: get_surface_weather

- Server name: `liftoff-weather`
- File: `backend/mcp_servers/weather_server.py`
- Purpose: Fetch hourly surface forecast data and compute launch GO/CAUTION/NO-GO windows.

### Inputs

- `latitude` (float, required): Launch site latitude.
- `longitude` (float, required): Launch site longitude.
- `forecast_hours` (int, default: 24): Forecast horizon in hours.

### Output

- `overall_assessment`: Launch readiness summary.
- `go_windows`, `caution_windows`, `no_go_windows`: Window counts by severity.
- `hourly_conditions`: Detailed hourly forecast breakdown.
- `observation_links`: External forecast links.

### Error behavior

- Returns an error structure when Open-Meteo is unavailable or parameters are invalid.

---

## Tool: get_winds_aloft

- Server name: `liftoff-weather`
- File: `backend/mcp_servers/weather_server.py`
- Purpose: Fetch a vertical wind profile and detect jet-stream hazards.

### Inputs

- `latitude` (float, required): Launch site latitude.
- `longitude` (float, required): Launch site longitude.
- `forecast_datetime` (str, required): ISO 8601 forecast time.

### Output

- `forecast_time`: Forecast grid time used.
- `wind_profile`: Winds by pressure level.
- `jet_stream_alert`: Whether any level exceeds jet-stream threshold.
- `jet_stream_message`: Human-readable alert summary.
- `observation_links`: External forecast links.

### Error behavior

- Returns an error structure when time selection or the upstream weather API fails.

---

## Tool: sondehub_run_simulation

- Server name: `sondehub_mcp`
- File: `backend/mcp_servers/sondehub_server.py`
- Purpose: Run a SondeHub Tawhiri Monte Carlo trajectory prediction using
  supplied flight profile rates.

### Inputs

- `launch_lat` (float, required): Launch latitude.
- `launch_lon` (float, required): Launch longitude.
- `launch_elevation_m` (float, required): Launch elevation in metres.
- `launch_datetime` (str, required): ISO 8601 launch time.
- `ascent_rate_ms` (float, required): Nominal ascent rate in m/s.
- `burst_altitude_m` (float, required): Nominal burst altitude in metres.
- `descent_rate_ms` (float, required): Nominal descent rate in m/s.
- `num_runs` (int, required): Number of Monte Carlo runs.
- `seed` (int, optional): Deterministic Monte Carlo seed.
- `ascent_rate_stddev_pct` (float, default: 5): Ascent-rate spread.
- `burst_altitude_stddev_m` (float, default: 1000): Burst-altitude spread.
- `descent_rate_stddev_pct` (float, default: 10): Descent-rate spread.
- `launch_time_stddev_min` (float, default: 10): Launch-time spread.

### Output

- `status`: `success` on a valid SondeHub run.
- `num_runs`: Number of completed simulations.
- `forecast`: SondeHub Tawhiri source metadata.
- `runs`: Per-run landing and duration summaries.
- `aggregate`: Aggregate landing, altitude, duration, and burst statistics.
- `trajectory_run1`: Sampled trajectory points for the first simulation.
- `trajectory_artifact`: Mean resampled trajectory, launch/burst/landing markers,
  and one-sigma landing uncertainty for STRATOS chat rendering.

### Error behavior

- Missing flight profile rates return a structured `missing_profile` error.
- Balloon, nozzle, payload, gas, and parachute fields are rejected as unsupported
  trajectory inputs.
- Upstream SondeHub failures are returned as structured tool errors.

---

## Running MCP Servers Locally

From the `backend/` directory:

```bash
python -m mcp_servers.notam_server
python -m mcp_servers.weather_server
python -m mcp_servers.sondehub_server
```

`sondehub_mcp` is imported in-process by the STRATOS backend, so a separate
server process is not required for normal chat usage. `python -m
mcp_servers.sondehub_server` remains available as an optional standalone stdio
MCP entrypoint.

---

## Environment Variables

- `LAMINAR_USER_KEY`: Optional Laminar Data Hub user key for restriction overlay lookup.
- `SONDEHUB_TAWHIRI_ENDPOINT`: Optional override for the SondeHub Tawhiri API.
