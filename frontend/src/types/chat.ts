export type MessageRole = "user" | "assistant";

export interface ToolCallRecord {
  name: string;
  args: Record<string, unknown>;
}

export interface TrajectoryArtifactPoint {
  lat: number;
  lon: number;
  alt_m: number;
  time_s?: number | null;
}

export interface RestrictionGeometry {
  type: string;
  coordinates?: unknown;
  geometries?: RestrictionGeometry[];
}

export interface RestrictionIntersection {
  id: string;
  source: string;
  severity: "CAUTION" | "NO_FLIGHT";
  summary: string;
  geometry?: RestrictionGeometry | null;
}

export interface RestrictionOverlay {
  restriction_source_status: "AVAILABLE" | "UNAVAILABLE";
  corridor_geometry?: RestrictionGeometry | null;
  landing_zone_geometry?: RestrictionGeometry | null;
  no_flight_zone_geometry?: RestrictionGeometry | null;
  intersections: RestrictionIntersection[];
}

export interface SondehubRequestSummary {
  profile?: string | null;
  launch_latitude?: number | null;
  launch_longitude?: number | null;
  launch_altitude?: number | null;
  launch_datetime?: string | null;
  ascent_rate?: number | null;
  burst_altitude?: number | null;
  descent_rate?: number | null;
}

export interface SondehubTrajectoryReference {
  provider: "sondehub-tawhiri";
  status: string;
  request?: SondehubRequestSummary | null;
  trajectory: TrajectoryArtifactPoint[];
  burst?: TrajectoryArtifactPoint | null;
  landing?: TrajectoryArtifactPoint | null;
}

export interface TrajectoryArtifact {
  launch: TrajectoryArtifactPoint;
  mean_trajectory: TrajectoryArtifactPoint[];
  mean_burst?: TrajectoryArtifactPoint | null;
  mean_landing?: TrajectoryArtifactPoint | null;
  landing_uncertainty_sigma_m: number;
  sondehub_reference?: SondehubTrajectoryReference | null;
  restriction_overlay?: RestrictionOverlay | null;
}

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  createdAt: Date;
  // Server-generated UI metadata only; never sent back as trusted /chat input.
  toolCalls?: ToolCallRecord[];
  trajectoryArtifact?: TrajectoryArtifact | null;
}
