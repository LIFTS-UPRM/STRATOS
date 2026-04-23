export type MissionStatus = "in-progress" | "upcoming" | "completed";

export interface Mission {
  id: string;
  title: string;
  status: MissionStatus;
}
