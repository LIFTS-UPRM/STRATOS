export interface ChatApiResponse {
  response: string;
  source: string;
}

/**
 * Send a message to the STRATOS backend and return the response.
 * Throws an Error with a user-facing message on network or server failure.
 */
export async function sendMessage(message: string): Promise<ChatApiResponse> {
  let res: Response;

  try {
    res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
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
