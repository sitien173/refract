import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CardDetailResponse } from "../api";
import { CardDialog } from "./CardDialog";

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

describe("CardDialog", () => {
  it("renders with dialog role and accessible name Card detail", () => {
    render(<CardDialog open={true} detail={mockCardDetail} onClose={vi.fn()} />);
    const dialog = screen.getByRole("dialog", { name: "Card detail" });
    expect(dialog).toBeInTheDocument();
  });

  it("renders card title, state label from COLUMN_LABELS, and project name", () => {
    render(<CardDialog open={true} detail={mockCardDetail} onClose={vi.fn()} />);

    expect(screen.getByRole("heading", { level: 2, name: "Implement coordinator kanban board" })).toBeInTheDocument();
    expect(screen.getByText("IN REVIEW")).toBeInTheDocument();
    expect(screen.getByText("project-alpha")).toBeInTheDocument();
  });

  it("renders body as plain text with preserved line breaks", () => {
    render(<CardDialog open={true} detail={mockCardDetail} onClose={vi.fn()} />);

    const bodyEl = screen.getByText(/Line 1: Detailed description\nLine 2: With preserved breaks/, { normalizer: (s) => s });
    expect(bodyEl).toBeInTheDocument();
    expect(bodyEl.className).toContain("whitespace-pre-wrap");
  });

  it("renders linked jobs using jobLabel: available links to /dashboard/jobs/<id> with title, state, and meta; pruned shows unavailable without a link", () => {
    render(<CardDialog open={true} detail={mockCardDetail} onClose={vi.fn()} />);

    // Available job: title is workflow ("consult"), meta is "gemini-flash · job-1111"
    const jobLink = screen.getByRole("link", { name: /consult/ });
    expect(jobLink).toHaveAttribute("href", "/dashboard/jobs/job-11112222-aaaa");
    expect(jobLink).toHaveTextContent("consult");
    expect(jobLink).toHaveTextContent("succeeded");
    expect(jobLink).toHaveTextContent("gemini-flash");
    expect(jobLink).toHaveTextContent("job-1111");

    // Unavailable / pruned job
    expect(screen.getByText("unavailable")).toBeInTheDocument();
    const unavailableJob = screen.getByText("unavailable").closest("a");
    expect(unavailableJob).toBeNull();
  });

  it("lists creation and each move with its time and note in the timeline", () => {
    render(<CardDialog open={true} detail={mockCardDetail} onClose={vi.fn()} />);

    expect(screen.getByText("Timeline")).toBeInTheDocument();
    expect(screen.getByText("Created")).toBeInTheDocument();
    expect(screen.getByText("Started working on implementation")).toBeInTheDocument();
    expect(screen.getByText("Ready for spec review")).toBeInTheDocument();
  });

  it("calls onClose when Close button is clicked", () => {
    const onClose = vi.fn();
    render(<CardDialog open={true} detail={mockCardDetail} onClose={onClose} />);

    const closeBtn = screen.getByRole("button", { name: /close/i });
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when Escape key is pressed", () => {
    const onClose = vi.fn();
    render(<CardDialog open={true} detail={mockCardDetail} onClose={onClose} />);

    const dialog = screen.getByRole("dialog", { name: "Card detail" });
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when backdrop overlay is clicked", () => {
    const onClose = vi.fn();
    render(<CardDialog open={true} detail={mockCardDetail} onClose={onClose} />);

    const backdrop = document.querySelector('[data-slot="dialog-overlay"]');
    expect(backdrop).toBeInTheDocument();
    fireEvent.click(backdrop as Element);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("renders polite live region inside dialog when announcement text updates after mount", () => {
    const { rerender } = render(<CardDialog open={true} detail={mockCardDetail} announcementText="Initial text" announcementSeq={1} onClose={vi.fn()} />);

    const dialog = screen.getByRole("dialog", { name: "Card detail" });
    const liveRegion = dialog.querySelector('[role="status"]');
    expect(liveRegion).toBeInTheDocument();
    expect(liveRegion).toHaveTextContent("");

    rerender(<CardDialog open={true} detail={mockCardDetail} announcementText="1 card moved" announcementSeq={2} onClose={vi.fn()} />);
    expect(liveRegion).toHaveTextContent("1 card moved");
  });

  it("renders loading and error states", () => {
    const { rerender } = render(<CardDialog open={true} loading={true} onClose={vi.fn()} />);
    expect(screen.getByText("Loading card…")).toBeInTheDocument();

    rerender(<CardDialog open={true} error="Failed to load" onClose={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Failed to load");
  });
});
