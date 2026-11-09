import { memo, useState } from "react";
import { Button } from "@/components/ui/button";
import type { TranscriptRow } from "../transcript/reduce";

function rowTitle(row: TranscriptRow) {
  if (row.kind === "assistant") return "Assistant";
  if (row.kind === "tool") return row.text;
  return row.kind;
}

export type TranscriptViewProps = {
  rows?: readonly TranscriptRow[];
  initialWindow?: number;
};

/** Memoized on the row object: the reducer keeps unchanged rows referentially stable. */
const TranscriptRowItem = memo(function TranscriptRowItem({ row }: { row: TranscriptRow }) {
  return (
    <li data-attempt={row.attempt} data-entity={row.entity} className="rounded-md bg-accent px-3 py-2 text-[0.8125rem]">
      <strong>{rowTitle(row)}</strong>
      {row.state && <span className="text-muted-foreground"> · {row.state}</span>}
      <pre className="mt-1 font-mono text-xs whitespace-pre-wrap">
        {row.text}
        {row.output ? `\n${row.output}` : ""}
      </pre>
    </li>
  );
});

/** Renders the reduced transcript; only the latest `limit` rows are in the DOM. */
export function TranscriptView({ rows = [], initialWindow = 50 }: TranscriptViewProps) {
  const [limit, setLimit] = useState(initialWindow);
  const earlier = rows.length > limit ? rows.length - limit : 0;
  return (
    <section aria-label="Output transcript" className="flex flex-col gap-3">
      {earlier > 0 && (
        <Button variant="secondary" size="sm" className="self-start" onClick={() => setLimit((n) => n + initialWindow)}>
          Show earlier events
        </Button>
      )}
      <ol className="flex flex-col gap-2">
        {rows.slice(earlier).map((row) => (
          <TranscriptRowItem key={row.id} row={row} />
        ))}
      </ol>
    </section>
  );
}
