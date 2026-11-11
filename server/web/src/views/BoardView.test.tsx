import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Profiler } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CardSummary } from "../api";
import { settle } from "../test/async";
import { mockMotion } from "../test/motion";
import { BoardView } from "./BoardView";

const choose = (option: HTMLElement) => {
  fireEvent.pointerDown(option);
  fireEvent.mouseDown(option);
  fireEvent.pointerUp(option);
  fireEvent.mouseUp(option);
  fireEvent.click(option);
};

const sampleCards: CardSummary[] = [
  {
    id: "card-12345678-abcd",
    project_id: "p1",
    project_root: "/home/user/project-alpha",
    title: "Implement coordinator kanban board",
    state: "todo",
    job_ids: ["j1", "j2"],
    created_at: "2026-11-08T01:00:00Z",
    updated_at: "2026-11-08T02:00:00Z",
  },
  {
    id: "card-87654321-wxyz",
    project_id: "p2",
    project_root: "/home/user/project-beta",
    title: "Review changes in progress",
    state: "in_progress",
    job_ids: ["j3"],
    created_at: "2026-11-08T01:30:00Z",
    updated_at: "2026-11-08T02:30:00Z",
  },
];

const defaultOptions = {
  projects: [
    { id: "p1", root: "/home/user/project-alpha" },
    { id: "p2", root: "/home/user/project-beta" },
  ],
};

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(document, "startViewTransition");
  Object.defineProperty(document, "hidden", { value: false, configurable: true });
  vi.useRealTimers();
});

describe("BoardView", () => {
  it("renders page header with h1 named Board and ViewNav", () => {
    render(<BoardView cards={[]} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
    expect(screen.getByRole("heading", { level: 1, name: "Board" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Views" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Board" })).toHaveAttribute("aria-current", "page");
  });

  it("renders five sections with aria-labelledby pointing to h2s holding labels and counts in column-major order when a project is selected", () => {
    const p1Cards = sampleCards.filter((c) => c.project_id === "p1");
    const { container } = render(<BoardView cards={p1Cards} options={defaultOptions} project="p1" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);

    const sections = container.querySelectorAll("section");
    expect(sections).toHaveLength(5);

    const expectedLabels = [
      { label: "TODO", count: 1 },
      { label: "IN PROGRESS", count: 0 },
      { label: "IN REVIEW", count: 0 },
      { label: "DONE", count: 0 },
      { label: "CANCELLED", count: 0 },
    ];

    sections.forEach((section, index) => {
      const labelledBy = section.getAttribute("aria-labelledby");
      expect(labelledBy).toBeTruthy();
      const heading = container.querySelector(`#${labelledBy}`);
      expect(heading).toBeTruthy();
      expect(heading?.tagName.toLowerCase()).toBe("h2");
      expect(heading?.textContent).toContain(expectedLabels[index].label);
      expect(heading?.textContent).toContain(String(expectedLabels[index].count));

      const ol = section.querySelector("ol");
      expect(ol).toBeTruthy();
    });
  });

  it("renders collapsible swimlanes ordered by newest updated_at with unique heading ids when no project is selected", () => {
    const { container } = render(<BoardView cards={sampleCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);

    const details = container.querySelectorAll("details");
    expect(details).toHaveLength(2);

    // project-beta has updated_at 02:30, project-alpha has 02:00
    const summaries = container.querySelectorAll("summary");
    expect(summaries[0]).toHaveTextContent("project-beta");
    expect(summaries[0]).toHaveTextContent("1 card");
    expect(summaries[1]).toHaveTextContent("project-alpha");
    expect(summaries[1]).toHaveTextContent("1 card");

    const rootSpan = summaries[0].querySelector("span[title='/home/user/project-beta']");
    expect(rootSpan).toBeInTheDocument();
    expect(rootSpan?.textContent).toBe("/home/user/project-beta");

    // All swimlanes start open
    for (const d of details) {
      expect(d).toHaveAttribute("open");
    }

    // Check heading ids are unique across all sections
    const sections = container.querySelectorAll("section");
    expect(sections).toHaveLength(10);
    const headingIds = new Set<string>();
    for (const section of sections) {
      const labelledBy = section.getAttribute("aria-labelledby");
      expect(labelledBy).toBeTruthy();
      if (labelledBy) {
        expect(headingIds.has(labelledBy)).toBe(false);
        headingIds.add(labelledBy);
      }
    }

    // Per-card project-name line is dropped inside swimlanes
    const cardLinks = container.querySelectorAll("li a");
    expect(cardLinks).toHaveLength(2);
    for (const link of cardLinks) {
      expect(link.querySelector(".truncate")).toBeNull();
    }
  });

  it("renders card content: clamped title, 8-char short ID, relative time, and linked job count", () => {
    render(<BoardView cards={sampleCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);

    const titleEl = screen.getByText("Implement coordinator kanban board");
    expect(titleEl).toBeInTheDocument();
    expect(titleEl.className).toContain("line-clamp-2");

    // 8-character short ID
    expect(screen.getByText("card-123")).toBeInTheDocument();

    // Linked job count
    expect(screen.getByText(/2 jobs/)).toBeInTheDocument();

    // Project name under All projects (last segment of project_root)
    expect(screen.getByText("project-alpha")).toBeInTheDocument();
  });

  it("hides project name when a specific project is selected", () => {
    render(<BoardView cards={sampleCards} options={defaultOptions} project="p1" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
    expect(screen.queryByText("project-alpha")).not.toBeInTheDocument();
    expect(screen.queryByText("project-beta")).not.toBeInTheDocument();
  });

  it("links card to /dashboard/board?card=<id> and navigates via onNavigate with default prevented", () => {
    const onNavigate = vi.fn();
    render(<BoardView cards={sampleCards} options={defaultOptions} onNavigate={onNavigate} onProjectChange={vi.fn()} />);

    const cardLink = screen.getByRole("link", { name: /Implement coordinator kanban board/ });
    expect(cardLink).toHaveAttribute("href", "/dashboard/board?card=card-12345678-abcd");

    const clickEvent = new MouseEvent("click", { bubbles: true, cancelable: true });
    cardLink.dispatchEvent(clickEvent);
    expect(clickEvent.defaultPrevented).toBe(true);
    expect(onNavigate).toHaveBeenCalledWith("/dashboard/board?card=card-12345678-abcd");
  });

  it("renders empty state message while preserving five columns with zero counts", () => {
    const { container } = render(<BoardView cards={[]} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);

    expect(screen.getByText("No cards yet. The Coordinator creates cards through MCP.")).toBeInTheDocument();

    const sections = container.querySelectorAll("section");
    expect(sections).toHaveLength(5);
    sections.forEach((section) => {
      const heading = section.querySelector("h2");
      expect(heading?.textContent).toContain("0");
    });
  });

  it("shows loading indicator with role status", () => {
    render(<BoardView cards={[]} options={defaultOptions} loading={true} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
    const loadingEl = screen.getByText("Loading board…");
    expect(loadingEl).toBeInTheDocument();
    expect(loadingEl).toHaveAttribute("role", "status");
  });

  it("clears previous cards and shows alert and empty state when a project fetch errors", () => {
    const { rerender } = render(<BoardView cards={sampleCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
    expect(screen.getByText("Implement coordinator kanban board")).toBeInTheDocument();

    rerender(<BoardView cards={[]} options={defaultOptions} error="Failed to load cards" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);

    expect(screen.queryByText("Implement coordinator kanban board")).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Failed to load cards");
    expect(screen.getByText("No cards yet. The Coordinator creates cards through MCP.")).toBeInTheDocument();
  });

  it("shows cards and error alert when rendered with cards and an error", () => {
    render(<BoardView cards={sampleCards} options={defaultOptions} error="Failed to load cards" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
    expect(screen.getByText("Implement coordinator kanban board")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Failed to load cards");
  });

  it("shows truncated banner when older cards are hidden", () => {
    render(<BoardView cards={sampleCards} options={defaultOptions} truncated={true} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
    expect(screen.getByText("Older DONE and CANCELLED cards are hidden.")).toBeInTheDocument();
  });

  it("lists options.projects in project select and calls onProjectChange on selection", async () => {
    const onProjectChange = vi.fn();
    render(<BoardView cards={sampleCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={onProjectChange} />);

    const trigger = screen.getByRole("combobox", { name: "Filter by project" });
    expect(trigger).toBeInTheDocument();

    fireEvent.click(trigger);
    await settle(300);
    choose(screen.getByRole("option", { name: "/home/user/project-alpha" }));
    expect(onProjectChange).toHaveBeenCalledWith("p1");

    fireEvent.click(trigger);
    await settle(300);
    choose(screen.getByRole("option", { name: "All projects" }));
    expect(onProjectChange).toHaveBeenCalledWith("");
  });

  it("preserves project in card link when a project is selected", () => {
    const onNavigate = vi.fn();
    render(<BoardView cards={sampleCards} options={defaultOptions} project="p1" onNavigate={onNavigate} onProjectChange={vi.fn()} />);

    const cardLink = screen.getByRole("link", { name: /Implement coordinator kanban board/ });
    expect(cardLink).toHaveAttribute("href", "/dashboard/board?project=p1&card=card-12345678-abcd");

    const clickEvent = new MouseEvent("click", { bubbles: true, cancelable: true });
    cardLink.dispatchEvent(clickEvent);
    expect(clickEvent.defaultPrevented).toBe(true);
    expect(onNavigate).toHaveBeenCalledWith("/dashboard/board?project=p1&card=card-12345678-abcd");
  });

  it("mounts CardDialog when cardId is set and closes it when Close button is clicked", () => {
    const onNavigate = vi.fn();
    render(<BoardView cards={sampleCards} options={defaultOptions} cardId="card-12345678-abcd" project="p1" onNavigate={onNavigate} onProjectChange={vi.fn()} />);

    const dialog = screen.getByRole("dialog", { name: "Card detail" });
    expect(dialog).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(onNavigate).toHaveBeenCalledTimes(1);
    expect(onNavigate).toHaveBeenCalledWith("/dashboard/board?project=p1");
  });

  it("closes CardDialog on Escape key", () => {
    const onNavigate = vi.fn();
    render(<BoardView cards={sampleCards} options={defaultOptions} cardId="card-12345678-abcd" project="p1" onNavigate={onNavigate} onProjectChange={vi.fn()} />);

    const dialog = screen.getByRole("dialog", { name: "Card detail" });
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(onNavigate).toHaveBeenCalledTimes(1);
    expect(onNavigate).toHaveBeenCalledWith("/dashboard/board?project=p1");
  });

  it("holds move announcement in the BoardView live region in closed state", async () => {
    mockMotion();
    const { container, rerender } = render(<BoardView cards={sampleCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);

    const boardRegion = container.querySelector('[role="status"][aria-label="Announcements"]');
    expect(boardRegion).toBeInTheDocument();
    expect(boardRegion).toHaveTextContent("");

    const updatedCards: CardSummary[] = [{ ...sampleCards[0], state: "in_review" }, sampleCards[1]];
    rerender(<BoardView cards={updatedCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
    await settle(0);

    expect(boardRegion).toHaveTextContent("'Implement coordinator kanban board' moved to IN REVIEW");
  });

  it("starts dialog region empty even with an earlier announcement, then shows a new move announcement in open state", async () => {
    mockMotion();
    const { rerender } = render(
      <BoardView cards={sampleCards} options={defaultOptions} cardId="card-12345678-abcd" announcement="Earlier announcement" onNavigate={vi.fn()} onProjectChange={vi.fn()} />,
    );

    const dialog = screen.getByRole("dialog", { name: "Card detail" });
    const dialogRegion = dialog.querySelector('[role="status"][aria-label="Announcements"]');
    expect(dialogRegion).toBeInTheDocument();
    expect(dialogRegion).toHaveTextContent("");

    const updatedCards: CardSummary[] = [{ ...sampleCards[0], state: "in_review" }, sampleCards[1]];
    rerender(<BoardView cards={updatedCards} options={defaultOptions} cardId="card-12345678-abcd" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
    await settle(0);

    expect(dialogRegion).toHaveTextContent("'Implement coordinator kanban board' moved to IN REVIEW");
  });

  it("holds the new announcement in the BoardView region on open-to-close rerender with cardId removed", async () => {
    const { container, rerender } = render(<BoardView cards={sampleCards} options={defaultOptions} cardId="card-12345678-abcd" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);

    const boardRegion = container.querySelector('[role="status"][aria-label="Announcements"]');
    expect(boardRegion).toBeInTheDocument();

    rerender(<BoardView cards={sampleCards} options={defaultOptions} cardId={null} announcement="Card not found" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);

    expect(boardRegion).toHaveTextContent("Card not found");
  });

  describe("View transitions", () => {
    it("calls startViewTransition once on card move and sets/clears view-transition-name on moving card", async () => {
      let capturedName: string | undefined;
      let nonMovingName: string | undefined;

      const start = vi.fn((update: () => void) => {
        update();
        const movingEl = document.getElementById("card-card-12345678-abcd");
        const otherEl = document.getElementById("card-card-87654321-wxyz");
        capturedName = movingEl?.style.getPropertyValue("view-transition-name");
        nonMovingName = otherEl?.style.getPropertyValue("view-transition-name");
        return { finished: Promise.resolve() };
      });
      vi.stubGlobal("matchMedia", (q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} }));
      Object.assign(document, { startViewTransition: start });

      const { rerender } = render(<BoardView cards={sampleCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);

      expect(start).not.toHaveBeenCalled();

      const updatedCards: CardSummary[] = [{ ...sampleCards[0], state: "in_progress", updated_at: "2026-11-08T03:00:00Z" }, sampleCards[1]];

      rerender(<BoardView cards={updatedCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);

      await settle(0);

      expect(start).toHaveBeenCalledTimes(1);
      expect(capturedName).toBe("card-card-12345678-abcd");
      expect(nonMovingName).toBeFalsy();

      await settle(0);
      const movingEl = document.getElementById("card-card-12345678-abcd");
      expect(movingEl?.style.getPropertyValue("view-transition-name")).toBe("");
    });

    it("skips startViewTransition when no card moved", async () => {
      const start = mockMotion();
      const { rerender } = render(<BoardView cards={sampleCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      start.mockClear();

      rerender(<BoardView cards={[...sampleCards]} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      await settle(0);

      expect(start).not.toHaveBeenCalled();
    });

    it("skips startViewTransition on project filter change and resets snapshot directly", async () => {
      const start = mockMotion();
      const { rerender } = render(<BoardView cards={sampleCards} options={defaultOptions} project="p1" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      start.mockClear();

      const otherProjectCards: CardSummary[] = [{ ...sampleCards[0], project_id: "p2", state: "in_progress" }];

      rerender(<BoardView cards={otherProjectCards} options={defaultOptions} project="p2" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      await settle(0);

      expect(start).not.toHaveBeenCalled();
    });

    it("skips startViewTransition when tab is hidden", async () => {
      const start = mockMotion();
      Object.defineProperty(document, "hidden", { value: true, configurable: true });

      const { rerender } = render(<BoardView cards={sampleCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      start.mockClear();

      const updatedCards: CardSummary[] = [{ ...sampleCards[0], state: "in_progress" }, sampleCards[1]];

      rerender(<BoardView cards={updatedCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      await settle(0);

      expect(start).not.toHaveBeenCalled();
    });

    it("skips startViewTransition under reduced motion", async () => {
      const start = mockMotion({ reduced: true });
      const { rerender } = render(<BoardView cards={sampleCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      start.mockClear();

      const updatedCards: CardSummary[] = [{ ...sampleCards[0], state: "in_progress" }, sampleCards[1]];

      rerender(<BoardView cards={updatedCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      await settle(0);

      expect(start).not.toHaveBeenCalled();
    });

    it("skips startViewTransition when startViewTransition is missing", async () => {
      mockMotion({ transitions: false });
      const { rerender } = render(<BoardView cards={sampleCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);

      const updatedCards: CardSummary[] = [{ ...sampleCards[0], state: "in_progress" }, sampleCards[1]];

      rerender(<BoardView cards={updatedCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      await settle(0);

      expect(screen.getByText("Implement coordinator kanban board")).toBeInTheDocument();
    });

    it("skips startViewTransition when a transition is already in flight", async () => {
      let finishFirst: () => void = () => {};
      const firstFinished = new Promise<void>((resolve) => {
        finishFirst = resolve;
      });

      const start = vi.fn((update: () => void) => {
        update();
        return { finished: firstFinished };
      });
      vi.stubGlobal("matchMedia", (q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} }));
      Object.assign(document, { startViewTransition: start });

      const { rerender } = render(<BoardView cards={sampleCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      start.mockClear();

      const move1Cards: CardSummary[] = [{ ...sampleCards[0], state: "in_progress" }, sampleCards[1]];
      rerender(<BoardView cards={move1Cards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      await settle(0);
      expect(start).toHaveBeenCalledTimes(1);

      const move2Cards: CardSummary[] = [{ ...sampleCards[0], state: "done" }, sampleCards[1]];
      rerender(<BoardView cards={move2Cards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      await settle(0);

      expect(start).toHaveBeenCalledTimes(1);

      finishFirst();
      await settle(0);
    });

    it("does not overwrite project B cards when a pending transition update from project A executes", async () => {
      let capturedUpdate: (() => void) | undefined;
      const start = vi.fn((update: () => void) => {
        capturedUpdate = update;
        return { finished: Promise.resolve() };
      });
      vi.stubGlobal("matchMedia", (q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} }));
      Object.assign(document, { startViewTransition: start });

      const projectACards: CardSummary[] = [
        {
          id: "card-a",
          project_id: "p1",
          project_root: "/path/to/p1",
          title: "Card A in Project A",
          state: "todo",
          job_ids: [],
          created_at: "2026-11-08T01:00:00Z",
          updated_at: "2026-11-08T01:00:00Z",
        },
      ];

      const { rerender } = render(<BoardView cards={projectACards} options={defaultOptions} project="p1" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);

      const projectACardsMoved: CardSummary[] = [{ ...projectACards[0], state: "in_progress", updated_at: "2026-11-08T02:00:00Z" }];
      rerender(<BoardView cards={projectACardsMoved} options={defaultOptions} project="p1" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      await settle(0);
      expect(start).toHaveBeenCalledTimes(1);
      expect(capturedUpdate).toBeDefined();

      const projectBCards: CardSummary[] = [
        {
          id: "card-b",
          project_id: "p2",
          project_root: "/path/to/p2",
          title: "Card B in Project B",
          state: "todo",
          job_ids: [],
          created_at: "2026-11-08T01:00:00Z",
          updated_at: "2026-11-08T01:00:00Z",
        },
      ];
      rerender(<BoardView cards={projectBCards} options={defaultOptions} project="p2" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      await settle(0);

      capturedUpdate?.();
      await settle(0);

      expect(screen.getByText("Card B in Project B")).toBeInTheDocument();
      expect(screen.queryByText("Card A in Project A")).not.toBeInTheDocument();
    });

    it("does not overwrite newer snapshot when newer callback runs first and older callback runs after", async () => {
      const capturedUpdates: Array<() => void> = [];
      const start = vi.fn((update: () => void) => {
        capturedUpdates.push(update);
        return { finished: Promise.resolve() };
      });
      vi.stubGlobal("matchMedia", (q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} }));
      Object.assign(document, { startViewTransition: start });

      const cardBase: CardSummary = {
        id: "card-f6",
        project_id: "p1",
        project_root: "/path/to/p1",
        title: "Card F6 Task",
        state: "todo",
        job_ids: [],
        created_at: "2026-11-08T01:00:00Z",
        updated_at: "2026-11-08T01:00:00Z",
      };

      const todoCards: CardSummary[] = [cardBase];
      const inProgressCards: CardSummary[] = [{ ...cardBase, state: "in_progress", updated_at: "2026-11-08T02:00:00Z" }];
      const doneCards: CardSummary[] = [{ ...cardBase, state: "done", updated_at: "2026-11-08T03:00:00Z" }];

      const { rerender } = render(<BoardView cards={todoCards} options={defaultOptions} project="p1" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);

      rerender(<BoardView cards={inProgressCards} options={defaultOptions} project="p1" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      await settle(0);
      expect(capturedUpdates.length).toBe(1);

      rerender(<BoardView cards={doneCards} options={defaultOptions} project="p1" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      await settle(0);
      expect(capturedUpdates.length).toBe(2);

      // Run newer callback first (moves to DONE)
      capturedUpdates[1]();
      await settle(0);

      const doingColumn = screen.getByRole("region", { name: /in progress/i });
      const doneColumn = screen.getByRole("region", { name: /done/i });

      expect(doneColumn).toHaveTextContent("Card F6 Task");
      expect(doingColumn).not.toHaveTextContent("Card F6 Task");

      // Run older callback after (would restore IN PROGRESS)
      capturedUpdates[0]();
      await settle(0);

      expect(doneColumn).toHaveTextContent("Card F6 Task");
      expect(doingColumn).not.toHaveTextContent("Card F6 Task");
    });

    it("does not overwrite newer snapshot when older callback runs against displayed snapshot (reviewer reproduction)", async () => {
      const capturedUpdates: Array<() => void> = [];
      const start = vi.fn((update: () => void) => {
        capturedUpdates.push(update);
        return { finished: new Promise(() => {}) };
      });
      vi.stubGlobal("matchMedia", (q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} }));
      Object.assign(document, { startViewTransition: start });

      const cardBase: CardSummary = {
        id: "card-f6-rev",
        project_id: "p1",
        project_root: "/path/to/p1",
        title: "Card F6 Reviewer",
        state: "todo",
        job_ids: [],
        created_at: "2026-11-08T01:00:00Z",
        updated_at: "2026-11-08T01:00:00Z",
      };

      const todoCards: CardSummary[] = [cardBase];
      const inProgressCards: CardSummary[] = [{ ...cardBase, state: "in_progress", updated_at: "2026-11-08T02:00:00Z" }];
      const doneCards: CardSummary[] = [{ ...cardBase, state: "done", updated_at: "2026-11-08T03:00:00Z" }];

      const { rerender } = render(<BoardView cards={todoCards} options={defaultOptions} project="p1" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);

      // Move to in_progress -> schedules transition, captured in capturedUpdates[0]
      rerender(<BoardView cards={inProgressCards} options={defaultOptions} project="p1" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      await settle(0);
      expect(capturedUpdates.length).toBe(1);

      // Move to done while transition is in flight -> displayed directly
      rerender(<BoardView cards={doneCards} options={defaultOptions} project="p1" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      await settle(0);

      const doingColumn = screen.getByRole("region", { name: /in progress/i });
      const doneColumn = screen.getByRole("region", { name: /done/i });

      expect(doneColumn).toHaveTextContent("Card F6 Reviewer");
      expect(doingColumn).not.toHaveTextContent("Card F6 Reviewer");

      // Run older callback (the one that would restore IN PROGRESS)
      capturedUpdates[0]();
      await settle(0);

      // Card must remain in DONE and not in IN PROGRESS
      expect(doneColumn).toHaveTextContent("Card F6 Reviewer");
      expect(doingColumn).not.toHaveTextContent("Card F6 Reviewer");
    });

    it("does not overwrite newer snapshot when older callback runs first, then newer callback runs", async () => {
      const capturedUpdates: Array<() => void> = [];
      const start = vi.fn((update: () => void) => {
        capturedUpdates.push(update);
        return { finished: Promise.resolve() };
      });
      vi.stubGlobal("matchMedia", (q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} }));
      Object.assign(document, { startViewTransition: start });

      const cardBase: CardSummary = {
        id: "card-f6-two",
        project_id: "p1",
        project_root: "/path/to/p1",
        title: "Card F6 Two Callbacks",
        state: "todo",
        job_ids: [],
        created_at: "2026-11-08T01:00:00Z",
        updated_at: "2026-11-08T01:00:00Z",
      };

      const todoCards: CardSummary[] = [cardBase];
      const inProgressCards: CardSummary[] = [{ ...cardBase, state: "in_progress", updated_at: "2026-11-08T02:00:00Z" }];
      const doneCards: CardSummary[] = [{ ...cardBase, state: "done", updated_at: "2026-11-08T03:00:00Z" }];

      const { rerender } = render(<BoardView cards={todoCards} options={defaultOptions} project="p1" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);

      rerender(<BoardView cards={inProgressCards} options={defaultOptions} project="p1" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      await settle(0);

      rerender(<BoardView cards={doneCards} options={defaultOptions} project="p1" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      await settle(0);

      expect(capturedUpdates.length).toBe(2);

      const doingColumn = screen.getByRole("region", { name: /in progress/i });
      const doneColumn = screen.getByRole("region", { name: /done/i });

      // Run older callback first: should be ignored (stale revision), not setting card to in_progress
      capturedUpdates[0]();
      await settle(0);
      expect(doingColumn).not.toHaveTextContent("Card F6 Two Callbacks");

      // Run newer callback
      capturedUpdates[1]();
      await settle(0);
      expect(doneColumn).toHaveTextContent("Card F6 Two Callbacks");
      expect(doingColumn).not.toHaveTextContent("Card F6 Two Callbacks");
    });

    it("deferred callback does not overwrite newer snapshot when original array reference is reused", async () => {
      const capturedUpdates: Array<() => void> = [];
      const start = vi.fn((update: () => void) => {
        capturedUpdates.push(update);
        return { finished: Promise.resolve() };
      });
      vi.stubGlobal("matchMedia", (q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} }));
      Object.assign(document, { startViewTransition: start });

      const cardBase: CardSummary = {
        id: "card-f7-deferred",
        project_id: "p1",
        project_root: "/path/to/p1",
        title: "Card F7 Deferred",
        state: "todo",
        job_ids: [],
        created_at: "2026-11-08T01:00:00Z",
        updated_at: "2026-11-08T01:00:00Z",
      };

      const arrayA: CardSummary[] = [cardBase];
      const arrayB: CardSummary[] = [{ ...cardBase, state: "in_progress", updated_at: "2026-11-08T02:00:00Z" }];

      const { rerender } = render(<BoardView cards={arrayA} options={defaultOptions} project="p1" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);

      rerender(<BoardView cards={arrayB} options={defaultOptions} project="p1" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      await settle(0);
      expect(capturedUpdates.length).toBe(1);

      // Rerender with the original array A (identical object reference)
      rerender(<BoardView cards={arrayA} options={defaultOptions} project="p1" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      await settle(0);

      // Invoke captured callback from B
      capturedUpdates[0]();
      await settle(0);

      const todoColumn = screen.getByRole("region", { name: /todo/i });
      const doingColumn = screen.getByRole("region", { name: /in progress/i });

      expect(todoColumn).toHaveTextContent("Card F7 Deferred");
      expect(doingColumn).not.toHaveTextContent("Card F7 Deferred");
    });

    it("queued microtask is skipped when original array reference is reused without await", async () => {
      const capturedUpdates: Array<() => void> = [];
      const start = vi.fn((update: () => void) => {
        capturedUpdates.push(update);
        update();
        return { finished: Promise.resolve() };
      });
      vi.stubGlobal("matchMedia", (q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} }));
      Object.assign(document, { startViewTransition: start });

      const cardBase: CardSummary = {
        id: "card-f7-microtask",
        project_id: "p1",
        project_root: "/path/to/p1",
        title: "Card F7 Microtask",
        state: "todo",
        job_ids: [],
        created_at: "2026-11-08T01:00:00Z",
        updated_at: "2026-11-08T01:00:00Z",
      };

      const arrayA: CardSummary[] = [cardBase];
      const arrayB: CardSummary[] = [{ ...cardBase, state: "in_progress", updated_at: "2026-11-08T02:00:00Z" }];

      const { rerender } = render(<BoardView cards={arrayA} options={defaultOptions} project="p1" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);

      // Rerender B then rerender A with NO await between them
      rerender(<BoardView cards={arrayB} options={defaultOptions} project="p1" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      rerender(<BoardView cards={arrayA} options={defaultOptions} project="p1" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);

      await settle(0);

      const todoColumn = screen.getByRole("region", { name: /todo/i });
      const doingColumn = screen.getByRole("region", { name: /in progress/i });

      expect(todoColumn).toHaveTextContent("Card F7 Microtask");
      expect(doingColumn).not.toHaveTextContent("Card F7 Microtask");
      expect(start).not.toHaveBeenCalled();
    });
  });

  describe("Announcements", () => {
    it("announces one move with title and target column label in the polite region", async () => {
      mockMotion();
      const { rerender } = render(<BoardView cards={sampleCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);

      const liveRegion = document.querySelector('[aria-live="polite"]');
      expect(liveRegion).toHaveTextContent("");

      const updatedCards: CardSummary[] = [{ ...sampleCards[0], state: "in_review" }, sampleCards[1]];
      rerender(<BoardView cards={updatedCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      await settle(0);

      expect(liveRegion).toHaveTextContent("'Implement coordinator kanban board' moved to IN REVIEW");
    });

    it("announces several moves with card count in the polite region", async () => {
      mockMotion();
      const { rerender } = render(<BoardView cards={sampleCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);

      const liveRegion = document.querySelector('[aria-live="polite"]');

      const updatedCards: CardSummary[] = [
        { ...sampleCards[0], state: "done" },
        { ...sampleCards[1], state: "done" },
      ];
      rerender(<BoardView cards={updatedCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      await settle(0);

      expect(liveRegion).toHaveTextContent("2 cards moved");
    });

    it("announces moves even when transition is skipped", async () => {
      mockMotion({ reduced: true });
      const { rerender } = render(<BoardView cards={sampleCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);

      const liveRegion = document.querySelector('[aria-live="polite"]');

      const updatedCards: CardSummary[] = [{ ...sampleCards[0], state: "in_progress" }, sampleCards[1]];
      rerender(<BoardView cards={updatedCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      await settle(0);

      expect(liveRegion).toHaveTextContent("'Implement coordinator kanban board' moved to IN PROGRESS");
    });

    it("does not restore earlier move text when App clears announcement to empty string", async () => {
      mockMotion();
      const { rerender } = render(<BoardView cards={sampleCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);

      const liveRegion = document.querySelector('[aria-live="polite"]');
      expect(liveRegion).toHaveTextContent("");

      const updatedCards: CardSummary[] = [{ ...sampleCards[0], state: "in_review" }, sampleCards[1]];
      rerender(<BoardView cards={updatedCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      await settle(0);
      expect(liveRegion).toHaveTextContent("'Implement coordinator kanban board' moved to IN REVIEW");

      rerender(<BoardView cards={updatedCards} options={defaultOptions} announcement="Card not found" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      expect(liveRegion).toHaveTextContent("Card not found");

      rerender(<BoardView cards={updatedCards} options={defaultOptions} announcement="" onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      expect(liveRegion).not.toHaveTextContent("'Implement coordinator kanban board' moved to IN REVIEW");
    });

    it("updates the live region when two consecutive move batches produce identical announcement text", async () => {
      mockMotion();
      const initialCards: CardSummary[] = [
        { ...sampleCards[0], id: "c1", state: "todo" },
        { ...sampleCards[0], id: "c2", state: "todo" },
        { ...sampleCards[0], id: "c3", state: "todo" },
        { ...sampleCards[0], id: "c4", state: "todo" },
      ];

      const { rerender } = render(<BoardView cards={initialCards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      const liveRegion = document.querySelector('[aria-live="polite"]');
      expect(liveRegion).toHaveTextContent("");

      const batch1Cards: CardSummary[] = [{ ...initialCards[0], state: "in_progress" }, { ...initialCards[1], state: "in_progress" }, initialCards[2], initialCards[3]];
      rerender(<BoardView cards={batch1Cards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      await settle(0);
      expect(liveRegion).toHaveTextContent("2 cards moved");
      const firstMessageNode = liveRegion?.firstElementChild;

      const batch2Cards: CardSummary[] = [batch1Cards[0], batch1Cards[1], { ...initialCards[2], state: "in_progress" }, { ...initialCards[3], state: "in_progress" }];
      rerender(<BoardView cards={batch2Cards} options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />);
      await settle(0);
      expect(liveRegion).toHaveTextContent("2 cards moved");
      const secondMessageNode = liveRegion?.firstElementChild;

      expect(secondMessageNode).toBeTruthy();
      expect(secondMessageNode).not.toBe(firstMessageNode);
    });
  });

  it("keeps render commits bounded when cards prop is omitted", async () => {
    const onRender = vi.fn();

    const { rerender } = render(
      <Profiler id="board" onRender={onRender}>
        <BoardView options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />
      </Profiler>,
    );

    rerender(
      <Profiler id="board" onRender={onRender}>
        <BoardView options={defaultOptions} onNavigate={vi.fn()} onProjectChange={vi.fn()} />
      </Profiler>,
    );

    await settle(100);

    expect(onRender.mock.calls.length).toBeLessThan(10);
  });
});
