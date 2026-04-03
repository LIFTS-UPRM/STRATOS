export type MessageRole = "user" | "assistant";

export type McpToolGroupId = "trajectory" | "weather" | "airspace";

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

export interface TrajectoryArtifact {
  launch: TrajectoryArtifactPoint;
  mean_trajectory: TrajectoryArtifactPoint[];
  mean_burst?: TrajectoryArtifactPoint | null;
  mean_landing?: TrajectoryArtifactPoint | null;
  landing_uncertainty_sigma_m: number;
}

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  createdAt: Date;
  toolCalls?: ToolCallRecord[];
  trajectoryArtifact?: TrajectoryArtifact | null;
}
