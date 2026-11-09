import { randomUUID } from "node:crypto";
import { resolve } from "node:path";
import type { APIRequestContext } from "@playwright/test";

const MCP_HEADERS = { accept: "application/json, text/event-stream", "content-type": "application/json" };
const PROTOCOL_VERSION = "2025-03-26";

function eventData(text: string) {
  const data = text
    .split("\n")
    .find((line) => line.startsWith("data: "))
    ?.slice(6);
  if (!data) throw new Error(`MCP response contained no event data: ${text}`);
  return JSON.parse(data) as { result: { content: { text: string }[] } };
}

/** Submits a consult job through the daemon's MCP endpoint and returns its id. */
export async function submitJob(request: APIRequestContext, prompt: string): Promise<string> {
  const initialized = await request.post("/mcp", {
    headers: MCP_HEADERS,
    data: {
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: { protocolVersion: PROTOCOL_VERSION, capabilities: {}, clientInfo: { name: "playwright-e2e", version: "1.0" } },
    },
  });
  if (!initialized.ok()) throw new Error(`MCP initialize failed: ${initialized.status()}`);
  const sessionId = initialized.headers()["mcp-session-id"];
  if (!sessionId) throw new Error("MCP initialize returned no session id");
  const headers = { ...MCP_HEADERS, "mcp-session-id": sessionId, "mcp-protocol-version": PROTOCOL_VERSION };
  const ready = await request.post("/mcp", { headers, data: { jsonrpc: "2.0", method: "notifications/initialized" } });
  if (!ready.ok()) throw new Error(`MCP initialized notification failed: ${ready.status()}`);
  const submitted = await request.post("/mcp", {
    headers,
    data: {
      jsonrpc: "2.0",
      id: 2,
      method: "tools/call",
      params: {
        name: "submit",
        arguments: { path: resolve(process.cwd(), "../.."), workflow: "consult", prompt, profile: "e2e", session: `playwright-${randomUUID()}`, fresh: true },
      },
    },
  });
  if (!submitted.ok()) throw new Error(`Job submission failed: ${submitted.status()}`);
  const text = eventData(await submitted.text()).result.content[0]?.text;
  if (!text) throw new Error("Job submission returned no result text");
  return (JSON.parse(text) as { job: { id: string } }).job.id;
}

export type CardHandle = string & {
  id: string;
  move: (state: string, note?: string) => Promise<void>;
};

export async function createCard(request: APIRequestContext, title: string, body = "", job_ids: string[] = []): Promise<CardHandle> {
  const initialized = await request.post("/mcp", {
    headers: MCP_HEADERS,
    data: {
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: { protocolVersion: PROTOCOL_VERSION, capabilities: {}, clientInfo: { name: "playwright-e2e", version: "1.0" } },
    },
  });
  if (!initialized.ok()) throw new Error(`MCP initialize failed: ${initialized.status()}`);
  const sessionId = initialized.headers()["mcp-session-id"];
  if (!sessionId) throw new Error("MCP initialize returned no session id");
  const headers = { ...MCP_HEADERS, "mcp-session-id": sessionId, "mcp-protocol-version": PROTOCOL_VERSION };
  const ready = await request.post("/mcp", { headers, data: { jsonrpc: "2.0", method: "notifications/initialized" } });
  if (!ready.ok()) throw new Error(`MCP initialized notification failed: ${ready.status()}`);
  const created = await request.post("/mcp", {
    headers,
    data: {
      jsonrpc: "2.0",
      id: 2,
      method: "tools/call",
      params: {
        name: "card_create",
        arguments: { path: resolve(process.cwd(), "../.."), title, body, job_ids },
      },
    },
  });
  if (!created.ok()) throw new Error(`Card creation failed: ${created.status()}`);
  const text = eventData(await created.text()).result.content[0]?.text;
  if (!text) throw new Error("Card creation returned no result text");
  const cardId = (JSON.parse(text) as { card: { id: string } }).card.id;

  const handle = Object.assign(new String(cardId), {
    id: cardId,
    move: (state: string, note = "") => moveCard(request, cardId, state, note),
  }) as CardHandle;
  return handle;
}

export async function moveCard(request: APIRequestContext, cardId: string, state: string, note = "", job_ids: string[] = []): Promise<void> {
  const initialized = await request.post("/mcp", {
    headers: MCP_HEADERS,
    data: {
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: { protocolVersion: PROTOCOL_VERSION, capabilities: {}, clientInfo: { name: "playwright-e2e", version: "1.0" } },
    },
  });
  if (!initialized.ok()) throw new Error(`MCP initialize failed: ${initialized.status()}`);
  const sessionId = initialized.headers()["mcp-session-id"];
  if (!sessionId) throw new Error("MCP initialize returned no session id");
  const headers = { ...MCP_HEADERS, "mcp-session-id": sessionId, "mcp-protocol-version": PROTOCOL_VERSION };
  const ready = await request.post("/mcp", { headers, data: { jsonrpc: "2.0", method: "notifications/initialized" } });
  if (!ready.ok()) throw new Error(`MCP initialized notification failed: ${ready.status()}`);
  const moved = await request.post("/mcp", {
    headers,
    data: {
      jsonrpc: "2.0",
      id: 2,
      method: "tools/call",
      params: {
        name: "card_move",
        arguments: { card_id: cardId, state, note, job_ids },
      },
    },
  });
  if (!moved.ok()) throw new Error(`Card move failed: ${moved.status()}`);
}

export async function jobState(request: APIRequestContext, jobId: string): Promise<string> {
  const response = await request.get(`/dashboard/api/jobs/${encodeURIComponent(jobId)}`);
  return ((await response.json()) as { state: string }).state;
}
