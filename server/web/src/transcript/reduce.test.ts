import { readFileSync } from "node:fs";
import { expect, it } from "vitest";
import { apply, initialTranscriptState, reduceTranscript } from "./reduce";

const fixture = (name: string) => JSON.parse(readFileSync(`src/transcript/fixtures/${name}.json`, "utf8")) as Record<string, unknown>[];
it("matches Codex assistant and paired tool rows", () =>
  expect(reduceTranscript(fixture("codex"))).toMatchObject([
    { kind: "assistant", text: "Codex response", entity: "msg-1" },
    { kind: "tool", text: "shell", state: "completed", output: "/workspace" },
  ]));
it("matches Claude assistant and paired tool rows", () =>
  expect(reduceTranscript(fixture("claude"))).toMatchObject([
    { kind: "assistant", text: "Claude response", entity: "msg-0" },
    { kind: "tool", text: "Read", state: "completed" },
  ]));
it("matches Pi assistant and paired tool rows", () =>
  expect(reduceTranscript(fixture("pi"))).toMatchObject([
    { kind: "assistant", text: "Pi response", entity: "msg-1" },
    { kind: "tool", text: "toolName", state: "completed", output: "done" },
  ]));
it("matches agy assistant and paired tool rows", () =>
  expect(reduceTranscript(fixture("agy"))).toMatchObject([
    { kind: "assistant", text: "agy response", entity: "msg-1" },
    { kind: "tool", text: "agent tool", state: "completed", output: "done" },
  ]));
it("starts a new assistant row after tool events even when the provider reuses an entity id", () => {
  const rows = reduceTranscript([
    { kind: "assistant.text.delta", entity_id: "msg-1", data: { text: "before" } },
    { kind: "tool.started", entity_id: "t1", data: { tool: "shell" } },
    { kind: "tool.completed", entity_id: "t1", data: { status: "completed" } },
    { kind: "assistant.text.delta", entity_id: "msg-1", data: { text: "after" } },
  ]);
  expect(rows.map((r) => r.kind)).toEqual(["assistant", "tool", "assistant"]);
  expect(rows[2].text).toBe("after");
});
it("shows real unknown kind and safely preserves hostile text", () => {
  const rows = reduceTranscript([
    { kind: "assistant.text.delta", entity_id: "m", data: { text: "<img src=x onerror=alert(1)>" } },
    { kind: "future.kind", data: { value: 1 } },
  ]);
  expect(rows[0].text).toBe("<img src=x onerror=alert(1)>");
  expect(rows[1].kind).toBe("future.kind");
});
it("groups rows by the attempt on the stream envelope even when entity ids repeat across attempts", () => {
  const rows = reduceTranscript([
    {
      seq: 1,
      attempt: 1,
      target_id: "t",
      backend: "codex",
      kind: "assistant.text.delta",
      entity_id: "msg-1",
      data: { text: "first try" },
    },
    {
      seq: 2,
      attempt: 1,
      target_id: "t",
      backend: "codex",
      kind: "tool.started",
      entity_id: "tool-1",
      data: { tool: "shell" },
    },
    {
      seq: 3,
      attempt: 2,
      target_id: "t",
      backend: "codex",
      kind: "assistant.text.delta",
      entity_id: "msg-1",
      data: { text: "second try" },
    },
    {
      seq: 4,
      attempt: 2,
      target_id: "t",
      backend: "codex",
      kind: "tool.started",
      entity_id: "tool-1",
      data: { tool: "shell" },
    },
    {
      seq: 5,
      attempt: 2,
      target_id: "t",
      backend: "codex",
      kind: "tool.completed",
      entity_id: "tool-1",
      data: { status: "completed", output: "ok" },
    },
  ]);
  expect(rows.map((r) => [r.kind, r.attempt, r.text])).toEqual([
    ["assistant", 1, "first try"],
    ["tool", 1, "shell"],
    ["assistant", 2, "second try"],
    ["tool", 2, "shell"],
  ]);
  expect(rows[1].state).toBe("running");
  expect(rows[3]).toMatchObject({ state: "completed", output: "ok" });
});
it("pairs a tool across more than 5000 intervening events", () => {
  const filler = Array.from({ length: 5200 }, (_, i) => ({ kind: "future.kind", data: { text: `row ${i}` } }));
  const rows = reduceTranscript([
    { kind: "tool.started", entity_id: "t1", data: { tool: "shell" } },
    ...filler,
    { kind: "tool.completed", entity_id: "t1", data: { status: "completed", output: "late" } },
  ]);
  expect(rows).toHaveLength(5201);
  expect(rows[0]).toMatchObject({ kind: "tool", text: "shell", state: "completed", output: "late" });
});

function chunk<T>(items: T[], size: number): T[][] {
  const chunks: T[][] = [];
  for (let i = 0; i < items.length; i += size) {
    chunks.push(items.slice(i, i + size));
  }
  return chunks;
}

const fixtures = ["codex", "claude", "pi", "agy"];

for (const name of fixtures) {
  it(`matches reduceTranscript across all two-way splits for ${name}`, () => {
    const events = fixture(name);
    const expected = reduceTranscript(events);
    for (let i = 0; i <= events.length; i++) {
      let state = initialTranscriptState();
      state = apply(state, events.slice(0, i));
      state = apply(state, events.slice(i));
      expect(state.rows).toEqual(expected);
    }
  });

  for (const pageSize of [1, 7, 500]) {
    it(`matches reduceTranscript across pages of ${pageSize} events for ${name}`, () => {
      const events = fixture(name);
      const expected = reduceTranscript(events);
      const pages = chunk(events, pageSize);
      let state = initialTranscriptState();
      for (const page of pages) {
        state = apply(state, page);
      }
      expect(state.rows).toEqual(expected);
    });
  }
}

it("keeps all 6000 rows across pages for a 6000-row transcript", () => {
  const events = Array.from({ length: 6000 }, (_, i) => ({
    kind: "future.kind",
    data: { text: `event ${i}` },
  }));
  const pages = chunk(events, 500);
  let state = initialTranscriptState();
  for (const page of pages) {
    state = apply(state, page);
  }
  expect(state.rows).toHaveLength(6000);
  expect(state.rows[0]?.text).toBe("event 0");
  expect(state.rows[5999]?.text).toBe("event 5999");
  expect(state.rows).toEqual(reduceTranscript(events));
});

it("copies the row array once per batch and only modifies affected rows", () => {
  const initialEvents = [
    { kind: "assistant.text.delta", entity_id: "a1", attempt: 1, data: { text: "hello" } },
    { kind: "tool.started", entity_id: "t1", attempt: 1, data: { tool: "shell" } },
  ];
  const s0 = initialTranscriptState();
  const s1 = apply(s0, initialEvents);
  expect(s1.rows).toHaveLength(2);
  const assistantRowBefore = s1.rows[0];
  const toolRowBefore = s1.rows[1];

  const s2 = apply(s1, [{ kind: "tool.completed", entity_id: "t1", attempt: 1, data: { status: "completed", output: "ok" } }]);
  expect(s2.rows).not.toBe(s1.rows);
  expect(s2.rows[0]).toBe(assistantRowBefore);
  expect(s2.rows[1]).not.toBe(toolRowBefore);
  expect(s2.rows[1]?.state).toBe("completed");
  expect(toolRowBefore?.state).toBe("running");
});
