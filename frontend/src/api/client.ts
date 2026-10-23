import type {
  Action,
  Audit,
  CaseDetail,
  Context,
  Ingest,
  Outcome,
  Passage,
  Queue,
  RecipientRole,
} from "./types";

// The dev server forwards /api to the API without the prefix (vite.config.ts).
export const API_BASE = "/api";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(`${status}: ${detail}`);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // keep the status text
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  context: () => request<Context>("/context"),
  queue: () => request<Queue>("/queue"),
  ingest: (weekEnding: string) => post<Ingest>("/ingest", { week_ending: weekEnding }),
  caseDetail: (id: string) => request<CaseDetail>(`/cases/${encodeURIComponent(id)}`),
  audit: (id: string) => request<Audit>(`/cases/${encodeURIComponent(id)}/audit`),
  passage: (key: string) => request<Passage>(`/passages/${encodeURIComponent(key)}`),
  // Interrupt 1 (ADR-018): approve executes; return and escalate wait for one LLM call.
  decide: (id: string, action: Action, actor: string) =>
    post<Outcome>(`/cases/${encodeURIComponent(id)}/decide`, { action, actor }),
  // Interrupt 2: the confirmed message from the actor who chose the action, or a cancel.
  confirmMessage: (id: string, actor: string, message: string, recipientRole: RecipientRole) =>
    post<Outcome>(`/cases/${encodeURIComponent(id)}/message`, {
      actor,
      message,
      recipient_role: recipientRole,
    }),
  cancelMessage: (id: string, actor: string) =>
    post<Outcome>(`/cases/${encodeURIComponent(id)}/message`, { actor, cancel: true }),
};

export function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.detail || `request failed (${error.status})`;
  if (error instanceof Error) return error.message;
  return String(error);
}
