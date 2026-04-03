const state = {
  map: null,
  launchMarker: null,
  trajectoryLayer: null,
  trajectoryGlowLayer: null,
  referenceTrajectoryLayer: null,
  landingLayer: null,
  landingSpreadLayer: null,
  peakMarker: null,
  landingMarkers: [],
  result: null,
  selectedRunIndex: null,
  elevationRequestToken: 0,
  elevationDebounceId: null,
  elevationManualOverride: false,
  nozzleLiftDebounceId: null,
  nozzleLiftManualOverride: false,
  userTimeZone: Intl.DateTimeFormat().resolvedOptions().timeZone || "Local time",
};

const DEFAULT_LAUNCH = {
  lat: 18.2116,
  lon: -67.1396,
  zoom: 15,
};

function $(id) {
  return document.getElementById(id);
}

function on(id, eventName, handler) {
  const element = $(id);
  if (!element) {
    console.warn(`ASTRA UI: missing element #${id} for ${eventName}`);
    return null;
  }
  element.addEventListener(eventName, handler);
  return element;
}

function formatDateTimeLocal(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function formatDateLocal(date) {
  return formatDateTimeLocal(date).slice(0, 10);
}

function formatTimeLocal(date) {
  return formatDateTimeLocal(date).slice(11, 16);
}

function getLaunchLocalDate() {
  const dateValue = $("launch_date").value;
  const timeValue = $("launch_time").value;
  if (!dateValue || !timeValue) {
    return null;
  }
  const launchDate = new Date(`${dateValue}T${timeValue}`);
  return Number.isNaN(launchDate.getTime()) ? null : launchDate;
}

function setDefaultLaunchTime() {
  const now = new Date();
  now.setSeconds(0, 0);
  $("launch_date").value = formatDateLocal(now);
  $("launch_time").value = formatTimeLocal(now);
  updateTimeZoneNote();
}

function formatDuration(seconds) {
  const hours = seconds / 3600;
  if (hours >= 1) {
    return `${hours.toFixed(1)} h`;
  }
  return `${Math.round(seconds / 60)} min`;
}

function formatCoords(lat, lon) {
  return `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
}

function formatForecastSource(source) {
  return (source || "unknown").replaceAll("-", " ");
}

function formatDistanceKm(distanceKm) {
  if (!Number.isFinite(distanceKm)) {
    return "n/a";
  }
  return `${distanceKm.toFixed(1)} km`;
}

function formatClock(dateValue) {
  const date = new Date(dateValue);
  return date.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

function updateStatus(label, text, mode = "") {
  const pill = $("forecast-pill");
  pill.textContent = label;
  pill.className = `status-pill ${mode}`.trim();
  $("status-copy").textContent = text;
}

function createDivIcon(className) {
  return L.divIcon({
    className: "",
    html: `<div class="${className}"></div>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });
}

function updateLocationNote(text) {
  const note = $("location-note");
  if (note) {
    note.textContent = text;
  }
}

function updateTimeZoneNote() {
  const note = $("timezone-note");
  if (!note) {
    return;
  }

  const launchDate = getLaunchLocalDate();
  if (!launchDate) {
    note.textContent = `Shown in ${state.userTimeZone}. Backend receives UTC.`;
    return;
  }

  const utcLabel = launchDate.toISOString().slice(0, 16).replace("T", " ");
  note.textContent = `Shown in ${state.userTimeZone}. Backend receives ${utcLabel} UTC.`;
}

function setElevationNote(text) {
  const note = $("elevation-note");
  if (note) {
    note.textContent = text;
  }
}

function setLiftNote(text) {
  const note = $("lift-note");
  if (note) {
    note.textContent = text;
  }
}

function setManualElevationOverride() {
  state.elevationManualOverride = true;
  const field = $("launch_elevation_m");
  if (!field.value.trim()) {
    setElevationNote("Manual elevation cleared. The backend will fetch terrain if needed.");
    return;
  }
  setElevationNote(`Manual elevation override · ${field.value.trim()} m will be used until terrain is requested again.`);
}

function syncProfileFields() {
  const floatingEnabled = $("floating_flight").checked;
  const cutdownEnabled = $("cutdown").checked;
  $("floating_altitude_m").disabled = !floatingEnabled;
  $("cutdown_altitude_m").disabled = !cutdownEnabled;
}

function setManualNozzleOverride() {
  state.nozzleLiftManualOverride = true;
  const value = $("nozzle_lift_kg").value.trim();
  if (value) {
    setLiftNote(`Manual nozzle lift override · ${value} kg will be used until you recalculate.`);
  } else {
    setLiftNote("Nozzle lift will be recalculated from ascent before the next run.");
  }
}

function syncLaunchInputs(latlng) {
  $("launch_lat").value = latlng.lat.toFixed(6);
  $("launch_lon").value = latlng.lng.toFixed(6);
  updateMissionMeta();
  scheduleElevationRefresh();
}

function ensureLaunchMarker(latlng) {
  if (!state.launchMarker) {
    state.launchMarker = L.marker(latlng, {
      draggable: true,
      icon: createDivIcon("launch-marker"),
    }).addTo(state.map);
    state.launchMarker.on("dragend", () => syncLaunchInputs(state.launchMarker.getLatLng()));
  } else {
    state.launchMarker.setLatLng(latlng);
  }
  syncLaunchInputs(latlng);
}

async function fetchJson(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(url, {
    headers,
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed.");
  }
  return payload;
}

async function refreshElevation({ force = false } = {}) {
  const lat = Number($("launch_lat").value);
  const lon = Number($("launch_lon").value);
  const refreshButton = $("refresh-elevation");

  if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
    return;
  }
  if (state.elevationManualOverride && !force) {
    return;
  }

  const requestToken = ++state.elevationRequestToken;
  setElevationNote("Fetching terrain elevation...");
  if (refreshButton) {
    setButtonBusy(refreshButton, "Fetching...", "Use terrain", true);
  }

  try {
    const payload = await fetchJson(`/api/elevation?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`);
    if (requestToken !== state.elevationRequestToken) {
      return;
    }
    state.elevationManualOverride = false;
    $("launch_elevation_m").value = Math.round(payload.elevation_m);
    setElevationNote(`Auto terrain fill · ${Math.round(payload.elevation_m)} m from ${payload.dataset}`);
  } catch (error) {
    if (requestToken !== state.elevationRequestToken) {
      return;
    }
    setElevationNote(`Elevation lookup unavailable · ${error.message}`);
  } finally {
    if (refreshButton) {
      setButtonBusy(refreshButton, "Fetching...", "Use terrain", false);
    }
  }
}

function scheduleElevationRefresh() {
  clearTimeout(state.elevationDebounceId);
  state.elevationDebounceId = setTimeout(() => {
    refreshElevation().catch(() => {});
  }, 320);
}

function updateMissionMeta() {
  const balloon = $("balloon_model").value || "Balloon";
  const gas = $("gas_type").value || "Gas";
  const lat = Number($("launch_lat").value || 0);
  const lon = Number($("launch_lon").value || 0);
  const floating = $("floating_flight").checked;
  const cutdown = $("cutdown").checked;

  $("mission-badge").textContent = `${balloon} · ${gas}`;
  $("launch-badge").textContent = formatCoords(lat, lon);
  $("mode-badge").textContent = floating
    ? "Floating profile"
    : cutdown
      ? "Cutdown profile"
      : "Burst profile";
}

function buildUtcLaunchTimestamp() {
  const launchDate = getLaunchLocalDate();
  if (launchDate) {
    return launchDate.toISOString();
  }
  const dateValue = $("launch_date").value;
  const timeValue = $("launch_time").value;
  return dateValue && timeValue ? `${dateValue}T${timeValue}` : "";
}

async function populateHardware() {
  const payload = await fetchJson("/api/hardware");

  $("balloon_model").innerHTML = payload.balloons
    .map((item) => `<option value="${item.name}">${item.name} · ${(item.mass_kg * 1000).toFixed(0)} g</option>`)
    .join("");

  $("parachute_model").innerHTML = payload.parachutes
    .map((item) => `<option value="${item.name}">${item.name} · ${item.approx_diameter_m.toFixed(2)} m</option>`)
    .join("");

  $("balloon_model").value = "TA800";
  $("parachute_model").value = "SPH36";
  updateMissionMeta();
}

function currentFormPayload() {
  const launchElevationValue = $("launch_elevation_m").value.trim();
  return {
    launch_lat: Number($("launch_lat").value),
    launch_lon: Number($("launch_lon").value),
    launch_elevation_m: launchElevationValue ? Number(launchElevationValue) : null,
    launch_datetime: buildUtcLaunchTimestamp(),
    launch_timezone: state.userTimeZone,
    balloon_model: $("balloon_model").value,
    gas_type: $("gas_type").value,
    payload_weight_kg: Number($("payload_weight_kg").value),
    ascent_rate_ms: Number($("ascent_rate_ms").value),
    nozzle_lift_kg: Number($("nozzle_lift_kg").value),
    parachute_model: $("parachute_model").value,
    num_runs: Number($("num_runs").value),
    force_low_res: $("force_low_res").checked,
    floating_flight: $("floating_flight").checked,
    floating_altitude_m: $("floating_altitude_m").value ? Number($("floating_altitude_m").value) : null,
    cutdown: $("cutdown").checked,
    cutdown_altitude_m: $("cutdown_altitude_m").value ? Number($("cutdown_altitude_m").value) : null,
  };
}

function renderDetailGrid(title, rows) {
  return `
    <h3>${title}</h3>
    <div class="detail-grid">
      ${rows.map(([label, value]) => `
        <div class="detail-row">
          <span>${label}</span>
          <strong>${value}</strong>
        </div>
      `).join("")}
    </div>
  `;
}

function renderCalcSummary(title, details) {
  $("calc-summary").innerHTML = `
    <div class="inline-summary__grid" aria-label="${title}">
      ${details.map(([label, value]) => `
        <div class="inline-summary__item">
          <span>${label}</span>
          <strong>${value}</strong>
        </div>
      `).join("")}
    </div>
  `;
}

function setButtonBusy(button, busyText, idleText, isBusy) {
  button.disabled = isBusy;
  button.textContent = isBusy ? busyText : idleText;
}

async function estimateLift() {
  const button = $("estimate-lift");
  if (button) {
    setButtonBusy(button, "Estimating...", "Recalculate", true);
  }

  try {
    const result = await fetchJson("/api/nozzle-lift", {
      method: "POST",
      body: JSON.stringify(currentFormPayload()),
    });

    $("nozzle_lift_kg").value = result.nozzle_lift_kg.toFixed(2);
    state.nozzleLiftManualOverride = false;
    setLiftNote(`Auto nozzle lift · ${result.nozzle_lift_kg.toFixed(2)} kg from your ascent target.`);
    renderCalcSummary("Preflight numbers", [
      ["Nozzle lift", `${result.nozzle_lift_kg.toFixed(2)} kg`],
      ["Fill volume", `${result.balloon_volume_m3.toFixed(2)} m³`],
      ["Balloon diameter", `${result.balloon_diameter_m.toFixed(2)} m`],
      ["Gas mass", `${result.gas_mass_kg.toFixed(2)} kg`],
    ]);
  } finally {
    if (button) {
      setButtonBusy(button, "Estimating...", "Recalculate", false);
    }
  }
}

function scheduleLiftEstimate() {
  if (state.nozzleLiftManualOverride) {
    return;
  }
  clearTimeout(state.nozzleLiftDebounceId);
  state.nozzleLiftDebounceId = setTimeout(() => {
    estimateLift().catch(() => {
      setLiftNote("Automatic nozzle lift estimate is unavailable. You can set it manually in advanced options.");
    });
  }, 260);
}

function locateUser({ recenter = true } = {}) {
  const locationButton = $("use-device-location");

  if (!navigator.geolocation) {
    updateLocationNote("Browser location is unavailable. Using the UPRM default launch site.");
    return Promise.resolve(false);
  }

  if (locationButton) {
    setButtonBusy(locationButton, "Locating...", "Use my location", true);
  }

  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const latlng = {
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        };
        ensureLaunchMarker(latlng);
        if (recenter && state.map) {
          state.map.setView([latlng.lat, latlng.lng], Math.max(state.map.getZoom(), 13));
        }
        updateLocationNote(`Using browser location at ${formatCoords(latlng.lat, latlng.lng)}. You can still click the map to move the launch point.`);
        if (locationButton) {
          setButtonBusy(locationButton, "Locating...", "Use my location", false);
        }
        resolve(true);
      },
      () => {
        updateLocationNote("Location permission was not granted. Using the UPRM default launch site until you move the marker.");
        if (locationButton) {
          setButtonBusy(locationButton, "Locating...", "Use my location", false);
        }
        resolve(false);
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 },
    );
  });
}

async function estimateVolume() {
  const button = $("estimate-volume");
  setButtonBusy(button, "Estimating...", "Estimate volume", true);
  updateStatus("Computing", "Estimating fill volume for the current nozzle lift.");

  try {
    const result = await fetchJson("/api/balloon-volume", {
      method: "POST",
      body: JSON.stringify(currentFormPayload()),
    });

    renderCalcSummary("Fill estimate", [
      ["Volume", `${result.balloon_volume_m3.toFixed(2)} m³`],
      ["Balloon diameter", `${result.balloon_diameter_m.toFixed(2)} m`],
      ["Gas mass", `${result.gas_mass_kg.toFixed(2)} kg`],
      ["Free lift", `${result.free_lift_kg.toFixed(2)} kg`],
    ]);
    updateStatus("Ready", "Volume estimate updated. Use the telemetry panel to compare runs.");
  } finally {
    setButtonBusy(button, "Estimating...", "Estimate volume", false);
  }
}

function landingMarkerClass(index) {
  return index === state.selectedRunIndex
    ? "landing-marker landing-marker--active"
    : "landing-marker";
}

function updateMarkerSelection() {
  state.landingMarkers.forEach((marker, index) => {
    marker.setIcon(createDivIcon(landingMarkerClass(index)));
  });
}

function renderRunList(result) {
  const runList = $("run-list");
  runList.innerHTML = result.runs.map((run, index) => `
    <button type="button" class="run-chip ${index === state.selectedRunIndex ? "is-selected" : ""}" data-run-index="${index}">
      <div class="run-chip__top">
        <span class="run-chip__label">Run ${run.run}</span>
        <span class="run-chip__burst">${run.burst ? "Burst" : "Float"}</span>
      </div>
      <div class="run-chip__coords">${formatCoords(run.landing_lat, run.landing_lon)}</div>
      <div class="run-chip__bottom">
        <span>${run.max_altitude_m.toFixed(0)} m</span>
        <span class="run-chip__time">${formatDuration(run.flight_duration_s)}</span>
      </div>
    </button>
  `).join("");

  [...runList.querySelectorAll(".run-chip")].forEach((button) => {
    button.addEventListener("click", () => selectRun(Number(button.dataset.runIndex)));
  });
}

function selectRun(index, panToMarker = true) {
  if (!state.result || !state.result.runs[index]) {
    return;
  }

  state.selectedRunIndex = index;
  updateMarkerSelection();
  renderRunList(state.result);

  const run = state.result.runs[index];
  const sondehub = state.result.sondehub || {};
  const predictorRows = [];
  if (sondehub.status === "applied" && sondehub.comparison) {
    predictorRows.push(["Predictor reference", "SondeHub Tawhiri"]);
    predictorRows.push(["Landing correction", formatDistanceKm(sondehub.comparison.landing_delta_km)]);
    predictorRows.push(["Burst correction", formatDistanceKm(sondehub.comparison.burst_delta_km)]);
  } else if (sondehub.status === "compared") {
    predictorRows.push(["Predictor reference", "SondeHub compared"]);
  } else if (sondehub.status === "error") {
    predictorRows.push(["Predictor reference", "SondeHub unavailable"]);
  }
  const launchDate = new Date(state.result.launch.datetime);
  const peakEta = new Date(launchDate.getTime() + (run.peak_time_s * 1000));
  const landingEta = new Date(launchDate.getTime() + (run.flight_duration_s * 1000));
  $("flight-summary").innerHTML = renderDetailGrid("Trajectory summary", [
    ["Selected run", `Run ${run.run}`],
    ["Apex", `${run.max_altitude_m.toFixed(0)} m at ${formatClock(peakEta)}`],
    ["Apex point", formatCoords(run.peak_lat, run.peak_lon)],
    ["Landing", formatCoords(run.landing_lat, run.landing_lon)],
    ["Landing ETA", formatClock(landingEta)],
    ["Flight time", formatDuration(run.flight_duration_s)],
    ["Weather source", formatForecastSource(state.result.forecast.source)],
    ["Forecast cycle", state.result.forecast.actual_cycle_utc || "Fallback profile"],
    ...predictorRows,
  ]);

  if (state.peakMarker) {
    state.peakMarker.setLatLng([run.peak_lat, run.peak_lon]).bindPopup(
      `<strong>Run ${run.run} apex</strong><br>` +
      `${run.max_altitude_m.toFixed(0)} m<br>` +
      `${formatCoords(run.peak_lat, run.peak_lon)}`
    );
  }

  if (state.landingMarkers[index]) {
    state.landingMarkers[index].openPopup();
    if (panToMarker) {
      state.map.panTo(state.landingMarkers[index].getLatLng(), { animate: true, duration: 0.6 });
    }
  }
}

function renderFlightSummary(result) {
  const aggregate = result.aggregate;
  const forecastSource = result.forecast.source || "unknown";
  const sondehub = result.sondehub || {};
  const modeClass = forecastSource === "open-meteo" || forecastSource === "cache-fallback"
    ? "is-fallback"
    : "is-live";
  const predictorCopy = sondehub.status === "applied"
    ? ` SondeHub reference applied with a ${formatDistanceKm(sondehub.comparison?.landing_delta_km || 0)} landing correction.`
    : sondehub.status === "compared"
      ? " SondeHub reference loaded for comparison."
      : sondehub.status === "error"
        ? " SondeHub comparison was unavailable for this run."
        : "";

  updateStatus(
    formatForecastSource(forecastSource),
    `Forecast loaded via ${forecastSource}. ${result.num_runs} run${result.num_runs === 1 ? "" : "s"} completed.${predictorCopy}`,
    modeClass,
  );

  $("metric-altitude").textContent = `${aggregate.max_altitude_m_mean.toFixed(0)} m`;
  $("metric-duration").textContent = formatDuration(aggregate.flight_duration_s_mean);
  $("metric-spread").textContent = `${aggregate.landing_spread_km.toFixed(1)} km`;
  $("metric-burst").textContent = `${Math.round(aggregate.burst_rate * 100)}%`;
  $("run-copy").textContent = `Mean landing ${formatCoords(aggregate.landing_lat_mean, aggregate.landing_lon_mean)} · spread ${aggregate.landing_spread_km.toFixed(1)} km`;

  state.result = result;
  state.selectedRunIndex = 0;
  renderRunList(result);
  selectRun(0, false);
}

function drawSimulation(result) {
  const launchLatLng = [result.launch.lat, result.launch.lon];
  ensureLaunchMarker({ lat: result.launch.lat, lng: result.launch.lon });

  if (state.trajectoryLayer) {
    state.map.removeLayer(state.trajectoryLayer);
  }
  if (state.trajectoryGlowLayer) {
    state.map.removeLayer(state.trajectoryGlowLayer);
  }
  if (state.referenceTrajectoryLayer) {
    state.map.removeLayer(state.referenceTrajectoryLayer);
  }
  if (state.landingLayer) {
    state.map.removeLayer(state.landingLayer);
  }
  if (state.landingSpreadLayer) {
    state.map.removeLayer(state.landingSpreadLayer);
  }
  if (state.peakMarker) {
    state.map.removeLayer(state.peakMarker);
  }

  const path = result.trajectory_run1.map((point) => [point.lat, point.lon]);
  const referencePath = (result.sondehub?.reference?.trajectory || []).map((point) => [point.lat, point.lon]);
  const peakPoint = result.trajectory_run1.reduce((best, point) => (
    !best || point.alt_m > best.alt_m ? point : best
  ), null);

  state.trajectoryGlowLayer = L.polyline(path, {
    color: "rgba(255, 143, 67, 0.25)",
    weight: 11,
    opacity: 1,
  }).addTo(state.map);

  state.trajectoryLayer = L.polyline(path, {
    color: "#ff8f43",
    weight: 4,
    opacity: 0.95,
  }).addTo(state.map);

  if (referencePath.length > 1) {
    state.referenceTrajectoryLayer = L.polyline(referencePath, {
      color: "#3ba4c4",
      weight: 3,
      opacity: 0.95,
      dashArray: "8 8",
    }).addTo(state.map);
  } else {
    state.referenceTrajectoryLayer = null;
  }

  state.landingMarkers = result.runs.map((run, index) =>
    L.marker([run.landing_lat, run.landing_lon], {
      icon: createDivIcon(landingMarkerClass(index)),
    }).bindPopup(
      `<strong>Run ${run.run}</strong><br>` +
      `Landing ${formatCoords(run.landing_lat, run.landing_lon)}<br>` +
      `Peak ${run.max_altitude_m.toFixed(0)} m<br>` +
      `${run.burst ? "Burst descent" : "Float profile"}`
    )
  );

  state.landingLayer = L.layerGroup(state.landingMarkers).addTo(state.map);
  state.landingSpreadLayer = L.circle(
    [result.aggregate.landing_lat_mean, result.aggregate.landing_lon_mean],
    {
      radius: result.aggregate.landing_spread_km * 1000,
      color: "rgba(255, 143, 67, 0.6)",
      weight: 1,
      fillColor: "rgba(255, 143, 67, 0.12)",
      fillOpacity: 1,
    }
  ).addTo(state.map);
  if (peakPoint) {
    state.peakMarker = L.marker([peakPoint.lat, peakPoint.lon], {
      icon: createDivIcon("peak-marker"),
    }).bindPopup(
      `<strong>Predicted apex</strong><br>` +
      `${peakPoint.alt_m.toFixed(0)} m<br>` +
      `${formatCoords(peakPoint.lat, peakPoint.lon)}`
    ).addTo(state.map);
  }

  const bounds = L.latLngBounds([
    launchLatLng,
    ...path,
    ...referencePath,
    ...result.runs.map((run) => [run.landing_lat, run.landing_lon]),
  ]);
  state.map.fitBounds(bounds.pad(0.18));
  updateMarkerSelection();
}

async function runSimulation(event) {
  event.preventDefault();
  const runButton = $("run-button");
  setButtonBusy(runButton, "Running...", "Run simulation", true);
  updateStatus("Loading", "Fetching weather and running Monte Carlo trajectories.");

  try {
    if (!state.nozzleLiftManualOverride || !$("nozzle_lift_kg").value.trim()) {
      await estimateLift();
    }
    const result = await fetchJson("/api/simulate", {
      method: "POST",
      body: JSON.stringify(currentFormPayload()),
    });
    renderFlightSummary(result);
    drawSimulation(result);
  } catch (error) {
    updateStatus("Error", error.message, "is-fallback");
    $("flight-summary").innerHTML = `<h3>Trajectory summary</h3><p>${error.message}</p>`;
    $("run-list").innerHTML = `<div class="run-empty">${error.message}</div>`;
  } finally {
    setButtonBusy(runButton, "Running...", "Run simulation", false);
  }
}

function initMap() {
  state.map = L.map("map", {
    zoomControl: false,
    preferCanvas: true,
  }).setView([DEFAULT_LAUNCH.lat, DEFAULT_LAUNCH.lon], DEFAULT_LAUNCH.zoom);

  L.control.zoom({ position: "topright" }).addTo(state.map);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(state.map);

  ensureLaunchMarker({ lat: DEFAULT_LAUNCH.lat, lng: DEFAULT_LAUNCH.lon });
  state.map.on("click", (event) => ensureLaunchMarker(event.latlng));
}

function wireMissionMetaInputs() {
  [
    "launch_lat",
    "launch_lon",
    "balloon_model",
    "gas_type",
    "floating_flight",
    "cutdown",
  ].forEach((id) => {
    on(id, "change", updateMissionMeta);
    on(id, "input", updateMissionMeta);
  });
}

function wireEvents() {
  on("use-map", "click", () => syncLaunchInputs(state.map.getCenter()));
  on("use-device-location", "click", () => {
    locateUser({ recenter: true }).catch(() => {
      updateLocationNote("Location lookup failed. You can still place launch manually on the map.");
    });
  });
  on("estimate-lift", "click", () => estimateLift().catch((error) => updateStatus("Error", error.message, "is-fallback")));
  on("refresh-elevation", "click", () => refreshElevation({ force: true }).catch((error) => {
    setElevationNote(`Elevation lookup unavailable · ${error.message}`);
  }));
  on("sim-form", "submit", runSimulation);
  on("launch_lat", "change", () => ensureLaunchMarker({ lat: Number($("launch_lat").value), lng: Number($("launch_lon").value) }));
  on("launch_lon", "change", () => ensureLaunchMarker({ lat: Number($("launch_lat").value), lng: Number($("launch_lon").value) }));
  on("launch_lat", "input", scheduleElevationRefresh);
  on("launch_lon", "input", scheduleElevationRefresh);
  on("launch_date", "input", updateTimeZoneNote);
  on("launch_date", "change", updateTimeZoneNote);
  on("launch_time", "input", updateTimeZoneNote);
  on("launch_time", "change", updateTimeZoneNote);
  on("launch_elevation_m", "input", setManualElevationOverride);
  on("launch_elevation_m", "change", setManualElevationOverride);
  on("nozzle_lift_kg", "input", setManualNozzleOverride);
  on("nozzle_lift_kg", "change", setManualNozzleOverride);
  on("floating_flight", "change", syncProfileFields);
  on("cutdown", "change", syncProfileFields);
  ["balloon_model", "gas_type", "payload_weight_kg", "ascent_rate_ms"].forEach((id) => {
    on(id, "change", scheduleLiftEstimate);
    on(id, "input", scheduleLiftEstimate);
  });
  wireMissionMetaInputs();
}

async function boot() {
  setDefaultLaunchTime();
  initMap();
  wireEvents();
  syncProfileFields();
  await populateHardware();
  await locateUser({ recenter: true });
  scheduleElevationRefresh();
  renderCalcSummary("Preflight numbers", [
    ["Nozzle lift", "Calculating"],
    ["Fill volume", "Calculating"],
    ["Balloon diameter", "Calculating"],
    ["Gas mass", "Calculating"],
  ]);
  scheduleLiftEstimate();
}

boot().catch((error) => {
  updateStatus("Error", error.message, "is-fallback");
});
