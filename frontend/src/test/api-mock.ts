import { vi } from "vitest";

// Frontend tests never reach the API: fetch is replaced by a route table keyed by
// "METHOD /path" (the path without the /api prefix).
export type Reply = unknown | { status: number; body: unknown };
export type Handler = Reply | ((body: unknown) => Reply | Promise<Reply>);

export interface Call {
  key: string;
  body: unknown;
}

export function fail(status: number, detail: string) {
  return { status, body: { detail } };
}

function isStatusReply(value: unknown): value is { status: number; body: unknown } {
  return typeof value === "object" && value !== null && "status" in value && "body" in value;
}

export function mockApi(routes: Record<string, Handler>): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const path = decodeURIComponent(String(input).replace(/^\/api/, ""));
      const key = `${method} ${path}`;
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ key, body });
      if (!(key in routes)) return new Response(JSON.stringify({ detail: `no mock for ${key}` }), { status: 404 });
      const handler = routes[key];
      const reply = typeof handler === "function" ? await handler(body) : handler;
      const [status, payload] = isStatusReply(reply) ? [reply.status, reply.body] : [200, reply];
      return new Response(JSON.stringify(payload), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return calls;
}

/** A promise the test resolves by hand, to hold a request open. */
export function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}
