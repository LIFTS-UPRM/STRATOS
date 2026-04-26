import type { Message, TrajectoryArtifact } from "@/types/chat";

export interface ChatApiResponse {
  response: string;
  source: string;
  tool_calls?: Array<{ name: string; args: Record<string, unknown> }>;
  trajectory_artifact?: TrajectoryArtifact | null;
}

function getChatEndpoint(): string {
  const configuredBase = process.env.NEXT_PUBLIC_BACKEND_URL?.trim();
  if (configuredBase) {
    return `${configuredBase.replace(/\/$/, "")}/chat`;
  }

  if (typeof window !== "undefined") {
    const { protocol, hostname } = window.location;
    const isLocalDevHost = hostname === "localhost" || hostname === "127.0.0.1";

    if (isLocalDevHost && (protocol === "http:" || protocol === "https:")) {
      return "http://127.0.0.1:8000/chat";
    }
  }

  return "/api/chat";
}

/**
 * Send a message to the STRATOS backend and return the response.
 * Throws an Error with a user-facing message on network or server failure.
 */
export async function sendMessage(
  message: string,
  history: Message[] = [],
): Promise<ChatApiResponse> {
  let res: Response;

  try {
    const endpoint = getChatEndpoint();
    res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        history: history.map((item) => ({
          role: item.role,
          content: item.content,
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
