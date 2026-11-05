import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { reduceTranscript, type TranscriptRow } from "../transcript/reduce";

function rowTitle(row: TranscriptRow) {
  if (row.kind === "assistant") return "Assistant";
  if (row.kind === "tool") return row.text;
  return row.kind;
}

/** Renders the reduced transcript; only the latest `limit` rows are in the DOM. */
export function TranscriptView({ events, initialWindow = 50 }: { events: Record<string, unknown>[]; initialWindow?: number }) {
  const [limit, setLimit] = useState(initialWindow);
  const rows = useMemo(() => reduceTranscript(events), [events]);
  const earlier = rows.length > limit ? rows.length - limit : 0;
  return (
    <section aria-label="Output transcript" className="flex flex-col gap-(--gap-sm)">
      {earlier > 0 && (
        <Button variant="secondary" size="sm" onClick={() => setLimit((n) => n + initialWindow)}>
          Show earlier events
        </Button>
      )}
      <ol className="flex flex-col gap-(--gap-sm)">
        {rows.slice(earlier).map((row) => (
          <li key={row.id} data-attempt={row.attempt} data-entity={row.entity} className="text-body-sm">
            <strong>{rowTitle(row)}</strong>
            {row.state && <span> · {row.state}</span>}
            <pre className="whitespace-pre-wrap">
              {row.text}
              {row.output ? `\n${row.output}` : ""}
            </pre>
          </li>
        ))}
      </ol>
    </section>
  );
}
