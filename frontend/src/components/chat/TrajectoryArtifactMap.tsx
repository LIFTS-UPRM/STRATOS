"use client";

import { useEffect, useMemo } from "react";
import type { LatLngBoundsExpression, LatLngExpression } from "leaflet";
import {
  Circle,
  CircleMarker,
  MapContainer,
  Polyline,
  TileLayer,
  Tooltip,
  useMap,
} from "react-leaflet";
import type {
  TrajectoryArtifact,
  TrajectoryArtifactPoint,
} from "@/types/chat";
import styles from "./MessageList.module.css";

function formatPoint(point: TrajectoryArtifactPoint): string {
  return `${point.lat.toFixed(4)}, ${point.lon.toFixed(4)} | ${point.alt_m.toFixed(0)} m`;
}

function TrajectoryFitBounds({ bounds }: { bounds: LatLngBoundsExpression }) {
  const map = useMap();

  useEffect(() => {
    map.fitBounds(bounds, { padding: [24, 24], maxZoom: 11 });
  }, [bounds, map]);

  return null;
}

export default function TrajectoryArtifactMap({
  artifact,
}: {
  artifact: TrajectoryArtifact;
}) {
  const pathPoints = useMemo(
    () => artifact.mean_trajectory ?? [],
    [artifact.mean_trajectory],
  );
  const pathPositions = useMemo<LatLngExpression[]>(
    () => pathPoints.map((point) => [point.lat, point.lon]),
    [pathPoints],
  );

  const bounds = useMemo<LatLngBoundsExpression>(() => {
    const points = [
      artifact.launch,
      ...pathPoints,
      artifact.mean_burst,
      artifact.mean_landing,
    ].filter(Boolean) as TrajectoryArtifactPoint[];

    if (!points.length) {
      return [[0, 0], [0, 0]];
    }

    return points.map((point) => [point.lat, point.lon]) as LatLngBoundsExpression;
  }, [artifact.launch, artifact.mean_burst, artifact.mean_landing, pathPoints]);

  const center: LatLngExpression = [
    artifact.mean_landing?.lat ?? artifact.launch.lat,
    artifact.mean_landing?.lon ?? artifact.launch.lon,
  ];

  return (
    <div className={styles.trajectoryArtifact}>
      <div className={styles.trajectoryHeader}>
        <span className={styles.trajectoryTitle}>Trajectory Artifact</span>
        {artifact.mean_landing && (
          <span className={styles.trajectoryMeta}>
            Landing {artifact.mean_landing.lat.toFixed(4)},{" "}
            {artifact.mean_landing.lon.toFixed(4)}
          </span>
        )}
      </div>

      <MapContainer
        className={styles.trajectoryMap}
        center={center}
        zoom={8}
        scrollWheelZoom={false}
        attributionControl={false}
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution="&copy; OpenStreetMap contributors"
        />
        <TrajectoryFitBounds bounds={bounds} />

        {artifact.mean_landing && artifact.landing_uncertainty_sigma_m > 0 && (
          <Circle
            center={[artifact.mean_landing.lat, artifact.mean_landing.lon]}
            radius={artifact.landing_uncertainty_sigma_m}
            pathOptions={{
              color: "#f97316",
              fillColor: "#f97316",
              fillOpacity: 0.12,
              weight: 2,
            }}
          />
        )}

        {pathPoints.slice(0, -1).map((point, index) => {
          const nextPoint = pathPoints[index + 1];
          return (
            <Polyline
              key={`${point.time_s ?? index}-${index}`}
              positions={[
                [point.lat, point.lon],
                [nextPoint.lat, nextPoint.lon],
              ]}
              pathOptions={{
                color: "#4f8ef7",
                opacity: 0.95,
                weight: 4,
              }}
            >
              <Tooltip sticky>
                <div className={styles.trajectoryTooltip}>
                  <strong>Mean path</strong>
                  <div>{formatPoint(nextPoint)}</div>
                  {nextPoint.time_s != null && (
                    <div>T+{Math.round(nextPoint.time_s)} s</div>
                  )}
                </div>
              </Tooltip>
            </Polyline>
          );
        })}

        <CircleMarker
          center={[artifact.launch.lat, artifact.launch.lon]}
          radius={8}
          pathOptions={{
            color: "#34d399",
            fillColor: "#34d399",
            fillOpacity: 0.95,
            weight: 2,
          }}
        >
          <Tooltip direction="top" offset={[0, -8]}>
            <div className={styles.trajectoryTooltip}>
              <strong>Launch</strong>
              <div>{formatPoint(artifact.launch)}</div>
            </div>
          </Tooltip>
        </CircleMarker>

        {artifact.mean_burst && (
          <CircleMarker
            center={[artifact.mean_burst.lat, artifact.mean_burst.lon]}
            radius={7}
            pathOptions={{
              color: "#facc15",
              fillColor: "#facc15",
              fillOpacity: 0.95,
              weight: 2,
            }}
          >
            <Tooltip direction="top" offset={[0, -8]}>
              <div className={styles.trajectoryTooltip}>
                <strong>Mean burst</strong>
                <div>{formatPoint(artifact.mean_burst)}</div>
              </div>
            </Tooltip>
          </CircleMarker>
        )}

        {artifact.mean_landing && (
          <CircleMarker
            center={[artifact.mean_landing.lat, artifact.mean_landing.lon]}
            radius={8}
            pathOptions={{
              color: "#fb7185",
              fillColor: "#fb7185",
              fillOpacity: 0.95,
              weight: 2,
            }}
          >
            <Tooltip direction="top" offset={[0, -8]}>
              <div className={styles.trajectoryTooltip}>
                <strong>Mean landing</strong>
                <div>{formatPoint(artifact.mean_landing)}</div>
                <div>
                  Sigma {(artifact.landing_uncertainty_sigma_m / 1000).toFixed(2)} km
                </div>
              </div>
            </Tooltip>
          </CircleMarker>
        )}
      </MapContainer>
    </div>
  );
}
