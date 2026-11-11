import type { CardState, CardSummary } from "../api";

export const BOARD_COLUMNS: readonly CardState[] = ["todo", "in_progress", "in_review", "done", "cancelled"] as const;

export const COLUMN_LABELS: Record<CardState, string> = {
  todo: "TODO",
  in_progress: "IN PROGRESS",
  in_review: "IN REVIEW",
  done: "DONE",
  cancelled: "CANCELLED",
};

export function sortCards(cards: readonly CardSummary[], state: CardState): CardSummary[] {
  const copy = [...cards];
  if (state === "todo") {
    copy.sort((a, b) => a.created_at.localeCompare(b.created_at));
  } else {
    copy.sort((a, b) => {
      const cmp = b.updated_at.localeCompare(a.updated_at);
      if (cmp !== 0) return cmp;
      return b.id.localeCompare(a.id);
    });
  }
  return copy;
}

export function shortCardId(id: string): string {
  return id.slice(0, 8);
}

export function getProjectName(projectRoot: string): string {
  const segments = projectRoot.split(/[/\\]/).filter(Boolean);
  return segments.pop() ?? projectRoot;
}

export function formatRelativeTime(dateString: string, now: number = Date.now()): string {
  const timestamp = new Date(dateString).getTime();
  const diffInSeconds = Math.round((timestamp - now) / 1000);
  const rtf = new Intl.RelativeTimeFormat("en");

  const absSeconds = Math.abs(diffInSeconds);
  if (absSeconds < 60) {
    return rtf.format(diffInSeconds, "second");
  }

  const diffInMinutes = Math.round(diffInSeconds / 60);
  const absMinutes = Math.abs(diffInMinutes);
  if (absMinutes < 60) {
    return rtf.format(diffInMinutes, "minute");
  }

  const diffInHours = Math.round(diffInMinutes / 60);
  const absHours = Math.abs(diffInHours);
  if (absHours < 24) {
    return rtf.format(diffInHours, "hour");
  }

  const diffInDays = Math.round(diffInHours / 24);
  const absDays = Math.abs(diffInDays);
  if (absDays < 30) {
    return rtf.format(diffInDays, "day");
  }

  const diffInMonths = Math.round(diffInDays / 30);
  const absMonths = Math.abs(diffInMonths);
  if (absMonths < 12) {
    return rtf.format(diffInMonths, "month");
  }

  const diffInYears = Math.round(diffInDays / 365);
  return rtf.format(diffInYears, "year");
}

export type CardMoveDiff = {
  card: CardSummary;
  fromState: CardState;
  toState: CardState;
};

export function diffCardMoves(prevCards: readonly CardSummary[], nextCards: readonly CardSummary[]): CardMoveDiff[] {
  const prevMap = new Map(prevCards.map((c) => [c.id, c]));
  const moves: CardMoveDiff[] = [];
  for (const card of nextCards) {
    const prev = prevMap.get(card.id);
    if (prev && prev.state !== card.state) {
      moves.push({
        card,
        fromState: prev.state,
        toState: card.state,
      });
    }
  }
  return moves;
}

export function formatMoveAnnouncement(moves: readonly CardMoveDiff[]): string {
  if (moves.length === 0) return "";
  if (moves.length === 1) {
    const move = moves[0];
    const targetLabel = COLUMN_LABELS[move.toState] ?? move.toState;
    return `'${move.card.title}' moved to ${targetLabel}`;
  }
  return `${moves.length} cards moved`;
}
