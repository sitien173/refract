import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { reduceTranscript, type TranscriptRow } from "../transcript/reduce";
import { TranscriptView } from "./TranscriptView";

it("accepts readonly TranscriptRow[] for rows prop without cast", () => {
  const row: TranscriptRow = { id: "assistant-0", attempt: 0, kind: "assistant", text: "hello rows" };
  const readonlyRows: readonly TranscriptRow[] = [row];
  render(<TranscriptView rows={readonlyRows} />);
  expect(screen.getByText("hello rows")).toBeInTheDocument();
});

it("renders hostile event text literally and allows earlier transcript rows", () => {
  const events = [
    { kind: "assistant.text.delta", entity_id: "m", data: { text: "<img src=x onerror=alert(1)>" } },
    { kind: "future.notice", data: { text: "a future event" } },
    ...Array.from({ length: 45 }, (_, i) => ({ kind: "unknown", data: { text: `row ${i}` } })),
  ];
  const rows = reduceTranscript(events);
  const { container } = render(<TranscriptView rows={rows} initialWindow={10} />);
  expect(screen.getByText("Show earlier events")).toBeInTheDocument();
  expect(container.querySelector("img")).toBeNull();
  for (let i = 0; i < 4; i++) fireEvent.click(screen.getByText("Show earlier events"));
  expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
  expect(screen.getByText("future.notice")).toBeInTheDocument();
});

it("keeps a tool pair that spans the window boundary as one row once earlier rows are revealed", () => {
  const filler = Array.from({ length: 120 }, (_, i) => ({ kind: "future.kind", data: { text: `row ${i}` } }));
  const events = [
    { kind: "tool.started", entity_id: "t1", data: { tool: "early shell" } },
    ...filler,
    { kind: "tool.completed", entity_id: "t1", data: { status: "completed", output: "late output" } },
  ];
  const rows = reduceTranscript(events);
  const { container } = render(<TranscriptView rows={rows} initialWindow={50} />);
  const items = () => container.querySelectorAll("li");
  expect(items()).toHaveLength(50);
  expect(container.textContent).not.toContain("early shell");
  for (let button = container.querySelector("button"); button; button = container.querySelector("button")) fireEvent.click(button);
  expect(items()).toHaveLength(121);
  expect(items()[0]).toHaveTextContent("early shell");
  expect(items()[0]).toHaveTextContent("completed");
  expect(items()[0]).toHaveTextContent("late output");
});

it("re-renders only new or changed rows when one event is appended", () => {
  const renders: Record<string, number> = {};
  const counted = (row: TranscriptRow): TranscriptRow => {
    const text = row.text;
    return Object.defineProperty({ ...row }, "text", {
      enumerable: true,
      get() {
        renders[row.id] = (renders[row.id] ?? 0) + 1;
        return text;
      },
    });
  };
  const base = Array.from({ length: 5 }, (_, i) => counted({ id: `assistant-${i}`, attempt: 1, kind: "assistant", text: `row ${i}` }));
  const { rerender } = render(<TranscriptView rows={base} />);
  expect(Object.values(renders).every((n) => n === 1)).toBe(true);
  const changed = counted({ id: "assistant-4", attempt: 1, kind: "assistant", text: "row 4 changed" });
  const added = counted({ id: "assistant-5", attempt: 1, kind: "assistant", text: "row 5" });
  for (const k of Object.keys(renders)) renders[k] = 0;
  rerender(<TranscriptView rows={[...base.slice(0, 4), changed, added]} />);
  expect(renders).toEqual({ "assistant-0": 0, "assistant-1": 0, "assistant-2": 0, "assistant-3": 0, "assistant-4": 1, "assistant-5": 1 });
});

it("keeps the Show earlier state across rerenders", () => {
  const rows = Array.from({ length: 30 }, (_, i): TranscriptRow => ({ id: `unknown-${i}`, attempt: 1, kind: "unknown", text: `row ${i}` }));
  const { container, rerender } = render(<TranscriptView rows={rows} initialWindow={10} />);
  fireEvent.click(screen.getByText("Show earlier events"));
  expect(container.querySelectorAll("li")).toHaveLength(20);
  act(() => rerender(<TranscriptView rows={[...rows]} initialWindow={10} />));
  expect(container.querySelectorAll("li")).toHaveLength(20);
});
