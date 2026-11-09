import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CardDetailResponse } from "../api";
import { CardPanel } from "./CardPanel";

const mockCardDetail: CardDetailResponse = {
  card: {
    id: "card-12345678-abcd",
    project_id: "p1",
    project_root: "/home/user/project-alpha",
    title: "Implement coordinator kanban board",
    state: "in_review",
    body: "Line 1: Detailed description\nLine 2: With preserved breaks",
    job_ids: ["job-11112222-aaaa", "job-33334444-bbbb"],
    created_at: "2026-11-08T01:00:00Z",
    updated_at: "2026-11-08T02:00:00Z",
  },
  moves: [
    {
      from_state: "todo",
      to_state: "in_progress",
      note: "Started working on implementation",
      at: "2026-11-08T01:30:00Z",
    },
    {
      from_state: "in_progress",
      to_state: "in_review",
      note: "Ready for spec review",
      at: "2026-11-08T02:00:00Z",
    },
  ],
  jobs: [
    {
      id: "job-11112222-aaaa",
      workflow: "consult",
      state: "succeeded",
      target: "gemini-flash",
      available: true,
    },
    {
      id: "job-33334444-bbbb",
      workflow: "exec",
      state: "failed",
      target: "claude-haiku",
      available: false,
    },
  ],
};

beforeEach(() => {
  vi.useFakeTimers({ now: new Date("2026-11-08T02:30:00Z") });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("CardPanel", () => {
  it("renders card title, state label from COLUMN_LABELS, and project name", () => {
    render(<CardPanel detail={mockCardDetail} onClose={vi.fn()} />);

    expect(screen.getByRole("heading", { level: 2, name: "Implement coordinator kanban board" })).toBeInTheDocument();
    expect(screen.getByText("IN REVIEW")).toBeInTheDocument();
    expect(screen.getByText("project-alpha")).toBeInTheDocument();
  });

  it("renders body as plain text with preserved line breaks", () => {
    render(<CardPanel detail={mockCardDetail} onClose={vi.fn()} />);

    const bodyEl = screen.getByText(/Line 1: Detailed description\nLine 2: With preserved breaks/, { normalizer: (s) => s });
    expect(bodyEl).toBeInTheDocument();
    expect(bodyEl.className).toContain("whitespace-pre-wrap");
  });

  it("renders linked jobs: available links to /dashboard/jobs/<id> with short ID, workflow, state, and target; pruned shows unavailable without a link", () => {
    render(<CardPanel detail={mockCardDetail} onClose={vi.fn()} />);

    // Available job
    const jobLink = screen.getByRole("link", { name: /job-1111/ });
    expect(jobLink).toHaveAttribute("href", "/dashboard/jobs/job-11112222-aaaa");
    expect(jobLink).toHaveTextContent("job-1111");
    expect(jobLink).toHaveTextContent("consult");
    expect(jobLink).toHaveTextContent("succeeded");
    expect(jobLink).toHaveTextContent("gemini-flash");

    // Unavailable / pruned job
    expect(screen.getByText("unavailable")).toBeInTheDocument();
    const unavailableJob = screen.getByText("unavailable").closest("a");
    expect(unavailableJob).toBeNull();
  });

  it("lists creation and each move with its time and note in the timeline", () => {
    render(<CardPanel detail={mockCardDetail} onClose={vi.fn()} />);

    expect(screen.getByText("Timeline")).toBeInTheDocument();
    expect(screen.getByText("Created")).toBeInTheDocument();
    expect(screen.getByText("Started working on implementation")).toBeInTheDocument();
    expect(screen.getByText("Ready for spec review")).toBeInTheDocument();
  });

  it("calls onClose when Close button is clicked", () => {
    const onClose = vi.fn();
    render(<CardPanel detail={mockCardDetail} onClose={onClose} />);

    const closeBtn = screen.getByRole("button", { name: /close/i });
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when Escape key is pressed", () => {
    const onClose = vi.fn();
    render(<CardPanel detail={mockCardDetail} onClose={onClose} />);

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
