"use client";

import { useEffect, useMemo } from "react";
import L from "leaflet";
import type { LatLngBoundsExpression, LatLngExpression } from "leaflet";
import {
  Circle,
  CircleMarker,
  GeoJSON,
  MapContainer,
  Polyline,
  TileLayer,
  Tooltip,
  useMap,
} from "react-leaflet";
import type {
  RestrictionGeometry,
  TrajectoryArtifact,
  TrajectoryArtifactPoint,
} from "@/types/chat";
import styles from "./MessageList.module.css";

function formatPoint(point: TrajectoryArtifactPoint): string {
  return `${point.lat.toFixed(4)}, ${point.lon.toFixed(4)} | ${point.alt_m.toFixed(0)} m`;
}

function formatDebugNumber(value: number | null | undefined, unit: string): string {
  return value == null ? "n/a" : `${value.toFixed(1)} ${unit}`;
}

function TrajectoryFitBounds({ bounds }: { bounds: LatLngBoundsExpression }) {
  const map = useMap();

  useEffect(() => {
    map.fitBounds(bounds, { padding: [24, 24], maxZoom: 11 });
  }, [bounds, map]);

  return null;
}

function overlayStyle(color: string, fillOpacity: number, dashed = false) {
  return {
    color,
    fillColor: color,
    fillOpacity,
    opacity: 0.9,
    weight: 2,
    dashArray: dashed ? "8 6" : undefined,
  };
}

function geometryPositions(geometry?: RestrictionGeometry | null): Array<[number, number]> {
  if (!geometry) {
    return [];
  }
  if (geometry.type === "GeometryCollection" && Array.isArray(geometry.geometries)) {
    return geometry.geometries.flatMap((child) => geometryPositions(child));
  }

  const points: Array<[number, number]> = [];
  const visit = (node: unknown) => {
    if (
      Array.isArray(node)
      && node.length >= 2
      && typeof node[0] === "number"
      && typeof node[1] === "number"
    ) {
      points.push([node[1], node[0]]);
      return;
    }
    if (Array.isArray(node)) {
      node.forEach(visit);
    }
  };
  visit(geometry.coordinates);
  return points;
}

function RestrictionGeometryLayer({
  geometry,
  color,
  fillOpacity,
  tooltipTitle,
  tooltipBody,
  dashed = false,
}: {
  geometry?: RestrictionGeometry | null;
  color: string;
  fillOpacity: number;
  tooltipTitle: string;
  tooltipBody?: string;
  dashed?: boolean;
}) {
  if (!geometry) {
    return null;
  }

  return (
    <GeoJSON
      key={`${tooltipTitle}-${geometry.type}`}
      data={geometry as never}
      style={() => overlayStyle(color, fillOpacity, dashed)}
      pointToLayer={(_feature, latlng) => (
        new L.CircleMarker(latlng, overlayStyle(color, fillOpacity, dashed))
      )}
      onEachFeature={(_feature, layer) => {
        layer.bindTooltip(
          `<div class="${styles.trajectoryTooltip}"><strong>${tooltipTitle}</strong>${
            tooltipBody ? `<div>${tooltipBody}</div>` : ""
          }</div>`,
          { sticky: true },
        );
      }}
    />
  );
}

export default function TrajectoryArtifactMap({
  artifact,
}: {
  artifact: TrajectoryArtifact;
}) {
  const overlay = artifact.restriction_overlay;
  const pathPoints = useMemo(
    () => artifact.mean_trajectory ?? [],
    [artifact.mean_trajectory],
  );
  const sondehubPoints = useMemo(
    () => artifact.sondehub_reference?.trajectory ?? [],
    [artifact.sondehub_reference?.trajectory],
  );
  const sondehubPositions = useMemo<LatLngExpression[]>(
    () => sondehubPoints.map((point) => [point.lat, point.lon]),
    [sondehubPoints],
  );

  const bounds = useMemo<LatLngBoundsExpression>(() => {
    const points = [
      artifact.launch,
      ...pathPoints,
      ...sondehubPoints,
      artifact.mean_burst,
      artifact.mean_landing,
      artifact.sondehub_reference?.burst,
      artifact.sondehub_reference?.landing,
    ].filter(Boolean) as TrajectoryArtifactPoint[];

    const overlayPositions = [
      ...geometryPositions(overlay?.corridor_geometry),
      ...geometryPositions(overlay?.landing_zone_geometry),
      ...geometryPositions(overlay?.no_flight_zone_geometry),
      ...(overlay?.intersections ?? []).flatMap((intersection) =>
        geometryPositions(intersection.geometry),
      ),
    ];

    if (!points.length && !overlayPositions.length) {
      return [[0, 0], [0, 0]];
    }

    return [
      ...points.map((point) => [point.lat, point.lon]),
      ...overlayPositions,
    ] as LatLngBoundsExpression;
  }, [
    artifact.launch,
    artifact.mean_burst,
    artifact.mean_landing,
    artifact.sondehub_reference?.burst,
    artifact.sondehub_reference?.landing,
    overlay,
    pathPoints,
    sondehubPoints,
  ]);

  const center: LatLngExpression = [
    artifact.mean_landing?.lat ?? artifact.launch.lat,
    artifact.mean_landing?.lon ?? artifact.launch.lon,
  ];

  return (
    <div className={styles.trajectoryArtifact}>
      <div className={styles.trajectoryHeader}>
        <span className={styles.trajectoryTitle}>
          {overlay ? "Balloon No-Flight Zone" : "SondeHub Trajectory"}
        </span>
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

        {overlay?.corridor_geometry && (
          <RestrictionGeometryLayer
            geometry={overlay.corridor_geometry}
            color="#60a5fa"
            fillOpacity={0.06}
            tooltipTitle="Corridor search area"
            tooltipBody="Buffered balloon corridor used for restriction evaluation."
            dashed
          />
        )}

        {overlay?.landing_zone_geometry && (
          <RestrictionGeometryLayer
            geometry={overlay.landing_zone_geometry}
            color="#f59e0b"
            fillOpacity={0.08}
            tooltipTitle="Landing uncertainty zone"
            tooltipBody="Terminal footprint used to widen the no-flight-zone check."
          />
        )}

        {overlay?.no_flight_zone_geometry && (
          <RestrictionGeometryLayer
            geometry={overlay.no_flight_zone_geometry}
            color="#ef4444"
            fillOpacity={0.14}
            tooltipTitle="Intersecting restriction zone"
            tooltipBody={
              overlay.restriction_source_status === "AVAILABLE"
                ? "Restriction geometry intersecting the predicted balloon corridor."
                : "Restriction result is unverified."
            }
          />
        )}

        {overlay?.intersections.map((intersection) => (
          <RestrictionGeometryLayer
            key={intersection.id}
            geometry={intersection.geometry}
            color={intersection.severity === "NO_FLIGHT" ? "#ef4444" : "#f97316"}
            fillOpacity={0.12}
            tooltipTitle={`${intersection.severity} · ${intersection.source}`}
            tooltipBody={intersection.summary}
          />
        ))}

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
                  <strong>SondeHub mean path</strong>
                  <div>{formatPoint(nextPoint)}</div>
                  {nextPoint.time_s != null && (
                    <div>T+{Math.round(nextPoint.time_s)} s</div>
                  )}
                </div>
              </Tooltip>
            </Polyline>
          );
        })}

        {sondehubPositions.length > 1 && (
          <Polyline
            positions={sondehubPositions}
            pathOptions={{
              color: "#22d3ee",
              dashArray: "8 8",
              lineCap: "round",
              opacity: 0.9,
              weight: 3,
            }}
          >
            <Tooltip sticky>
              <div className={styles.trajectoryTooltip}>
                <strong>SondeHub reference</strong>
                <div>{formatPoint(sondehubPoints[sondehubPoints.length - 1])}</div>
                {artifact.sondehub_reference?.request && (
                  <>
                    <div>
                      Ascent{" "}
                      {formatDebugNumber(
                        artifact.sondehub_reference.request.ascent_rate,
                        "m/s",
                      )}
                    </div>
                    <div>
                      Descent{" "}
                      {formatDebugNumber(
                        artifact.sondehub_reference.request.descent_rate,
                        "m/s",
                      )}
                    </div>
                    <div>
                      Burst{" "}
                      {formatDebugNumber(
                        artifact.sondehub_reference.request.burst_altitude,
                        "m",
                      )}
                    </div>
                    {artifact.sondehub_reference.request.launch_datetime && (
                      <div>{artifact.sondehub_reference.request.launch_datetime}</div>
                    )}
                  </>
                )}
              </div>
            </Tooltip>
          </Polyline>
        )}

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
