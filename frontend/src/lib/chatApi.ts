import type { McpToolGroupId, Message, TrajectoryArtifact } from "@/types/chat";

export interface ChatApiResponse {
  response: string;
  source: string;
  tool_calls?: Array<{ name: string; args: Record<string, unknown> }>;
  trajectory_artifact?: TrajectoryArtifact | null;
}

/**
 * Send a message to the STRATOS backend and return the response.
 * Throws an Error with a user-facing message on network or server failure.
 */
export async function sendMessage(
  message: string,
  history: Message[] = [],
  enabledToolGroups?: McpToolGroupId[],
): Promise<ChatApiResponse> {
  let res: Response;

  try {
    const base = process.env.NEXT_PUBLIC_BACKEND_URL ?? "";
    const endpoint = base ? `${base}/chat` : "/api/chat";
    res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        enabled_tool_groups: enabledToolGroups,
        history: history.map((item) => ({
          role: item.role,
          content: item.content,
          tool_calls: item.toolCalls ?? [],
        })),
      }),
    });
  } catch {
    throw new Error(
      "Unable to reach the STRATOS backend. Check that the server is running."
    );
  }

  if (!res.ok) {
    let detail = `Server error ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      // ignore JSON parse failure — keep the status-code message
    }
    throw new Error(detail);
  }

  return res.json() as Promise<ChatApiResponse>;
}
