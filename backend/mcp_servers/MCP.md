# STRATOS MCP Tools Reference

This document describes the MCP tools currently exposed by STRATOS.

---

## Tool: check_notam_airspace

- Server name: `liftoff-notam`
- File: `backend/mcp_servers/notam_server.py`
- Purpose: Query FAA and AviationWeather NOTAM feeds and summarize launch-airspace risk.

### Inputs

- `latitude` (float, required): Launch site latitude.
- `longitude` (float, required): Launch site longitude.
- `radius_km` (float, default: 25.0): Search radius in kilometers.
- `launch_datetime` (str, optional): ISO 8601 launch datetime.
- `faa_client_id` (str, optional): FAA OAuth client ID.
- `faa_client_secret` (str, optional): FAA OAuth client secret.

### Output

- `total_notams`: Total deduplicated NOTAM count.
- `relevant_notams`: Balloon-relevant NOTAMs with matched keywords.
- `clearance_status`: `NO_CRITICAL_ALERTS`, `REVIEW_REQUIRED`, or `MANUAL_CHECK_REQUIRED`.
- `sources_queried`: Sources successfully queried.
- `observation_links`: Reference links for manual review.

### Error behavior

- Degrades gracefully when one upstream source fails.
- Returns a validation error structure for invalid coordinates.

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

## Tool: astra_list_balloons

- Server name: `astra_mcp`
- File: `backend/mcp_servers/astra_server.py`
- Purpose: List HAB_Predictor/ASTRA-supported balloon models and their physical specs.

### Inputs

- `response_format` (str, default: `json`): `json` or `markdown`.

### Output

- JSON object keyed by balloon model when `response_format=json`.
- Markdown catalog when `response_format=markdown`.

### Error behavior

- Validation fails if `response_format` is not supported.

---

## Tool: astra_list_parachutes

- Server name: `astra_mcp`
- File: `backend/mcp_servers/astra_server.py`
- Purpose: List HAB_Predictor/ASTRA-supported parachute models.

### Inputs

- `response_format` (str, default: `json`): `json` or `markdown`.

### Output

- JSON object keyed by parachute model when `response_format=json`.
- Markdown table when `response_format=markdown`.

### Error behavior

- Validation fails if `response_format` is not supported.

---

## Tool: astra_calculate_nozzle_lift

- Server name: `astra_mcp`
- File: `backend/mcp_servers/astra_server.py`
- Purpose: Estimate the nozzle lift needed to achieve a target ascent rate using
  the vendored HAB_Predictor simulator code.

### Inputs

- `balloon_model` (str, required): ASTRA balloon model name.
- `gas_type` (str, required): `Helium` or `Hydrogen`.
- `payload_weight_kg` (float, required): Payload train weight in kilograms.
- `ascent_rate_ms` (float, default: 5.0): Desired ascent rate in m/s.

### Output

- `nozzle_lift_kg`
- `gas_mass_kg`
- `balloon_volume_m3`
- `balloon_diameter_m`
- `balloon_mass_kg`
- `note`

### Error behavior

- STRATOS converts ASTRA string failures into structured error responses.

---

## Tool: astra_calculate_balloon_volume

- Server name: `astra_mcp`
- File: `backend/mcp_servers/astra_server.py`
- Purpose: Estimate fill volume, gas mass, and free lift from a known nozzle lift
  using the vendored HAB_Predictor simulator code.

### Inputs

- `balloon_model` (str, required): ASTRA balloon model name.
- `gas_type` (str, required): `Helium` or `Hydrogen`.
- `nozzle_lift_kg` (float, required): Nozzle lift in kilograms.
- `payload_weight_kg` (float, required): Payload train weight in kilograms.

### Output

- `gas_mass_kg`
- `balloon_volume_m3`
- `balloon_diameter_m`
- `free_lift_kg`
- `free_lift_fraction`
- `note`

### Error behavior

- STRATOS converts ASTRA string failures into structured error responses.

---

## Tool: astra_run_simulation

- Server name: `astra_mcp`
- File: `backend/mcp_servers/astra_server.py`
- Purpose: Run a HAB_Predictor/ASTRA Monte Carlo balloon flight simulation in-process
  using NOAA GFS forecasts, cache fallback, and SondeHub calibration.

### Inputs

- `launch_lat` (float, required): Launch latitude.
- `launch_lon` (float, required): Launch longitude.
- `launch_elevation_m` (float, required): Launch elevation in metres.
- `launch_datetime` (str, required): ISO 8601 launch time.
- `balloon_model` (str, required): ASTRA balloon model.
- `gas_type` (str, required): `Helium` or `Hydrogen`.
- `nozzle_lift_kg` (float, required): Nozzle lift in kilograms.
- `payload_weight_kg` (float, required): Payload train weight in kilograms.
- `parachute_model` (str, optional): ASTRA parachute model.
- `num_runs` (int, default: 5): Number of Monte Carlo runs.
- `floating_flight` (bool, default: false): Whether to simulate a floating flight.
- `floating_altitude_m` (float, optional): Target float altitude.
- `cutdown` (bool, default: false): Whether to enable cutdown.
- `cutdown_altitude_m` (float, optional): Cudown trigger altitude.
- `force_low_res` (bool, default: false): Use lower-resolution GFS data for faster runs.

### Output

- `status`: `success` on a valid ASTRA run.
- `num_runs`: Number of completed simulations.
- `forecast`: Forecast cache metadata and source.
- `runs`: Per-run landing and duration summaries.
- `aggregate`: Aggregate landing, altitude, duration, and burst statistics.
- `trajectory_run1`: Sampled trajectory points for the first simulation.
- `trajectory_artifact`: Mean resampled trajectory, launch/burst/landing markers,
  and one-sigma landing uncertainty for STRATOS chat rendering.

### Error behavior

- STRATOS converts ASTRA string failures and non-JSON output into structured error responses.

---

## Running MCP Servers Locally

From the `backend/` directory:

```bash
python -m mcp_servers.notam_server
python -m mcp_servers.weather_server
```

`astra_mcp` is imported in-process by the STRATOS backend, so a separate ASTRA/HAB
server process is not required for normal chat usage. `python -m mcp_servers.astra_server`
remains available only as an optional standalone stdio MCP entrypoint.

---

## Environment Variables

- `FAA_CLIENT_ID` / `FAA_CLIENT_SECRET`: Optional FAA NOTAM credentials.
- `ASTRA_GFS_CACHE_DIR`: Optional override for the ASTRA GFS forecast cache directory.
