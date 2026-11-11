import { ChevronRight } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { CardDetailResponse, CardOptions, CardSummary } from "../api";
import { ViewNav } from "../components/ViewNav";
import { BOARD_COLUMNS, COLUMN_LABELS, diffCardMoves, formatMoveAnnouncement, formatRelativeTime, shortCardId, sortCards } from "../lib/board";
import { groupByProject } from "../lib/jobs";
import { CardDialog } from "./CardDialog";

export type BoardViewProps = {
  cards?: readonly CardSummary[];
  options?: CardOptions;
  loading?: boolean;
  error?: string | null;
  project?: string;
  truncated?: boolean;
  onProjectChange: (project: string) => void;
  onNavigate: (path: string) => void;
  cardId?: string | null;
  cardDetail?: CardDetailResponse | null;
  cardLoading?: boolean;
  cardError?: { status?: number; message?: string } | string | null;
  announcement?: string;
};

const FIELD_LABEL = "text-[0.8125rem] font-medium text-muted-foreground";
const DEFAULT_CARDS: readonly CardSummary[] = [];

type BoardColumnsProps = {
  cards: readonly CardSummary[];
  laneKey?: string;
  project?: string;
  onNavigate: (path: string) => void;
};

function BoardColumns({ cards, laneKey, project, onNavigate }: BoardColumnsProps) {
  return (
    <>
      {BOARD_COLUMNS.map((column) => {
        const columnCards = cards.filter((c) => c.state === column);
        const sorted = sortCards(columnCards, column);
        const headingId = laneKey ? `column-${laneKey}-${column}-heading` : `column-${column}-heading`;

        return (
          <section key={column} aria-labelledby={headingId} className="flex w-72 shrink-0 flex-col rounded-lg bg-muted/40 p-3">
            <h2 id={headingId} className="flex items-center justify-between pb-2 text-sm font-semibold">
              <span>{COLUMN_LABELS[column]}</span>
              <span className="text-muted-foreground font-normal">{sorted.length}</span>
            </h2>
            <ol className="flex flex-1 flex-col gap-2 overflow-y-auto">
              {sorted.map((card) => {
                const cardHref = project
                  ? `/dashboard/board?project=${encodeURIComponent(project)}&card=${encodeURIComponent(card.id)}`
                  : `/dashboard/board?card=${encodeURIComponent(card.id)}`;

                return (
                  <li key={card.id} id={`card-${card.id}`}>
                    <a
                      href={cardHref}
                      onClick={(e) => {
                        e.preventDefault();
                        onNavigate(cardHref);
                      }}
                      className="block flex flex-col gap-2 rounded-md bg-card p-3 shadow-card transition-shadow hover:shadow-md"
                    >
                      <h3 className="line-clamp-2 text-sm font-medium tracking-tight text-foreground">{card.title}</h3>
                      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <span>{shortCardId(card.id)}</span>
                        <span>•</span>
                        <span>{formatRelativeTime(card.updated_at)}</span>
                        <span>•</span>
                        <span>
                          {card.job_ids.length} {card.job_ids.length === 1 ? "job" : "jobs"}
                        </span>
                      </div>
                    </a>
                  </li>
                );
              })}
            </ol>
          </section>
        );
      })}
    </>
  );
}

export function BoardView({
  cards = DEFAULT_CARDS,
  options = { projects: [] },
  loading = false,
  error = null,
  project = "",
  truncated = false,
  onProjectChange,
  onNavigate,
  cardId = null,
  cardDetail = null,
  cardLoading = false,
  cardError = null,
  announcement = "",
}: BoardViewProps) {
  const projectChoices = [{ value: null, label: "All projects" }, ...(options.projects ?? []).map((p) => ({ value: p.id, label: p.root }))];
  const closeHref = project ? `/dashboard/board?project=${encodeURIComponent(project)}` : "/dashboard/board";

  const [displayedCards, setDisplayedCards] = useState(cards);
  const [announcementText, setAnnouncementText] = useState(announcement);
  const [announcementSeq, setAnnouncementSeq] = useState(0);
  const prevAnnouncementRef = useRef(announcement);
  const snapshotRef = useRef(cards);
  const projectRef = useRef(project);
  const inFlightRef = useRef(false);
  const revisionRef = useRef(0);

  useEffect(() => {
    if (announcement !== prevAnnouncementRef.current) {
      prevAnnouncementRef.current = announcement;
      setAnnouncementText(announcement);
      setAnnouncementSeq((seq) => seq + 1);
    }
  }, [announcement]);

  useEffect(() => {
    if (project !== projectRef.current) {
      projectRef.current = project;
      revisionRef.current += 1;
      snapshotRef.current = cards;
      setDisplayedCards(cards);
      setAnnouncementText("");
      setAnnouncementSeq((seq) => seq + 1);
      return;
    }

    revisionRef.current += 1;

    const moves = diffCardMoves(snapshotRef.current, cards);
    if (moves.length > 0) {
      setAnnouncementText(formatMoveAnnouncement(moves));
      setAnnouncementSeq((seq) => seq + 1);
    }

    const noMoves = moves.length === 0;
    const isHidden = typeof document !== "undefined" && Boolean(document.hidden);
    const reducedMotion = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    const noTransitionApi = typeof document?.startViewTransition !== "function";
    const isInFlight = inFlightRef.current;

    if (noMoves || isHidden || reducedMotion || noTransitionApi || isInFlight) {
      snapshotRef.current = cards;
      setDisplayedCards(cards);
      return;
    }

    const movingCardIds = moves.map((m) => m.card.id);
    const capturedRevision = revisionRef.current;

    queueMicrotask(() => {
      if (revisionRef.current !== capturedRevision) {
        return;
      }
      if (inFlightRef.current) {
        revisionRef.current += 1;
        snapshotRef.current = cards;
        setDisplayedCards(cards);
        return;
      }
      inFlightRef.current = true;

      for (const id of movingCardIds) {
        const el = document.getElementById(`card-${id}`);
        el?.style.setProperty("view-transition-name", `card-${id}`);
      }

      try {
        const transition = document.startViewTransition(() => {
          if (revisionRef.current !== capturedRevision) {
            return;
          }
          flushSync(() => {
            snapshotRef.current = cards;
            setDisplayedCards(cards);
          });
          for (const id of movingCardIds) {
            const el = document.getElementById(`card-${id}`);
            el?.style.setProperty("view-transition-name", `card-${id}`);
          }
        });

        transition.finished.finally(() => {
          inFlightRef.current = false;
          for (const id of movingCardIds) {
            const el = document.getElementById(`card-${id}`);
            el?.style.removeProperty("view-transition-name");
          }
        });
      } catch {
        inFlightRef.current = false;
        if (revisionRef.current === capturedRevision) {
          snapshotRef.current = cards;
          setDisplayedCards(cards);
        }
        for (const id of movingCardIds) {
          const el = document.getElementById(`card-${id}`);
          el?.style.removeProperty("view-transition-name");
        }
      }
    });
  }, [cards, project]);

  const projectGroups = useMemo(
    () =>
      groupByProject(
        [...displayedCards].sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
        (c) => c.project_root,
      ),
    [displayedCards],
  );

  return (
    <main className="board-view mx-auto flex min-h-screen max-w-[1600px] flex-col gap-4 p-6">
      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only" aria-label="Announcements">
        <span key={announcementSeq}>{announcementText}</span>
      </div>

      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Board</h1>
        <ViewNav current="board" onNavigate={onNavigate} />
      </header>

      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-col gap-1">
          <span className={FIELD_LABEL}>Project</span>
          <Select items={projectChoices} value={project || null} onValueChange={(val) => onProjectChange(val ?? "")}>
            <SelectTrigger aria-label="Filter by project">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {projectChoices.map((item) => (
                <SelectItem key={item.value === null ? "none" : `value:${item.value}`} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {truncated && <p className="text-xs text-muted-foreground">Older DONE and CANCELLED cards are hidden.</p>}
      </div>

      {error && (
        <div className="callout callout-error" role="alert">
          {error}
        </div>
      )}

      {loading && (
        <p role="status" className="text-sm text-muted-foreground">
          Loading board…
        </p>
      )}

      {displayedCards.length === 0 && !loading && <p className="text-sm text-muted-foreground">No cards yet. The Coordinator creates cards through MCP.</p>}

      <div className="flex flex-1 gap-4 overflow-hidden">
        {project || displayedCards.length === 0 ? (
          <div className="flex flex-1 gap-4 overflow-x-auto pb-4">
            <BoardColumns cards={displayedCards} project={project} onNavigate={onNavigate} />
          </div>
        ) : (
          <div className="flex flex-1 flex-col gap-6 overflow-y-auto">
            {projectGroups.map((group, index) => {
              const laneKey = `lane-${index}`;
              return (
                <details key={group.root || "no-project"} open className="group space-y-2">
                  <summary className="flex cursor-pointer select-none items-center gap-2 list-none px-1 py-1 text-sm font-semibold text-foreground [&::-webkit-details-marker]:hidden">
                    <ChevronRight aria-hidden="true" className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-90" />
                    <span>{group.name}</span>
                    {group.root ? (
                      <span title={group.root} className="truncate font-normal text-muted-foreground text-xs">
                        {group.root}
                      </span>
                    ) : null}
                    <span className="ml-auto font-normal text-muted-foreground text-xs">
                      {group.items.length}
                      <span className="sr-only">{group.items.length === 1 ? " card" : " cards"}</span>
                    </span>
                  </summary>
                  <div className="flex gap-4 overflow-x-auto pb-4">
                    <BoardColumns cards={group.items} laneKey={laneKey} onNavigate={onNavigate} />
                  </div>
                </details>
              );
            })}
          </div>
        )}
        <CardDialog
          open={Boolean(cardId)}
          detail={cardDetail}
          loading={cardLoading}
          error={cardError}
          onClose={() => onNavigate(closeHref)}
          announcementText={announcementText}
          announcementSeq={announcementSeq}
        />
      </div>
    </main>
  );
}
