import { render, screen, fireEvent } from "@testing-library/react";
import { expect, it } from "vitest";
import { TranscriptView } from "./TranscriptView";
it("renders hostile event text literally and allows earlier transcript rows", () => {
  const events = [
    { kind: "assistant.text.delta", entity_id: "m", data: { text: "<img src=x onerror=alert(1)>" } },
    { kind: "future.notice", data: { text: "a future event" } },
    ...Array.from({ length: 45 }, (_, i) => ({ kind: "unknown", data: { text: `row ${i}` } })),
  ];
  const { container } = render(<TranscriptView events={events} initialWindow={10} />);
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
  const { container } = render(<TranscriptView events={events} initialWindow={50} />);
  const items = () => container.querySelectorAll("li");
  expect(items()).toHaveLength(50);
  expect(container.textContent).not.toContain("early shell");
  for (let button = container.querySelector("button"); button; button = container.querySelector("button"))
    fireEvent.click(button);
  expect(items()).toHaveLength(121);
  expect(items()[0]).toHaveTextContent("early shell");
  expect(items()[0]).toHaveTextContent("completed");
  expect(items()[0]).toHaveTextContent("late output");
});
