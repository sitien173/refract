export type TranscriptRow = {
  id: string;
  attempt: number;
  kind: string;
  text: string;
  entity?: string;
  data?: Record<string, unknown>;
  state?: string;
  output?: string;
};

type StreamEvent = Record<string, unknown>;

const DEFAULT_ATTEMPT = 1;

/**
 * Folds raw stream events into display rows. `attempt` comes from the stream
 * envelope (see `_record_stream_event` in execution.py); entity ids are only
 * unique within an attempt, so every lookup is keyed by both.
 */
export function reduceTranscript(events: StreamEvent[]): TranscriptRow[] {
  const rows: TranscriptRow[] = [];
  const tools = new Map<string, TranscriptRow>();
  const latestAssistant = new Map<string, TranscriptRow>();
  let activeAssistant: TranscriptRow | null = null;

  const createAssistant = (entity: string, attempt: number) => {
    const row: TranscriptRow = {
      id: `assistant-${rows.length}`,
      attempt,
      kind: "assistant",
      entity: entity || undefined,
      text: "",
    };
    rows.push(row);
    if (entity) latestAssistant.set(`${attempt}:${entity}`, row);
    activeAssistant = row;
    return row;
  };

  for (const event of events) {
    const kind = String(event.kind ?? event.type ?? "unknown");
    const data = (event.data && typeof event.data === "object" ? event.data : event) as Record<string, unknown>;
    const attempt = Number(event.attempt ?? data.attempt ?? DEFAULT_ATTEMPT);
    const entity = String(event.entity_id ?? data.entity_id ?? "");

    if (kind === "assistant.text.delta") {
      const text = String(data.text ?? data.text_delta ?? "");
      const previous = activeAssistant as TranscriptRow | null;
      const continues = previous && previous.entity === (entity || undefined) && previous.attempt === attempt;
      const row = continues ? previous : createAssistant(entity, attempt);
      row.text += text;
      continue;
    }

    if (kind === "assistant.message.started") {
      createAssistant(entity, attempt);
      continue;
    }

    if (kind === "assistant.message.completed") {
      const row = entity ? latestAssistant.get(`${attempt}:${entity}`) : activeAssistant;
      if (row) row.state = "completed";
      activeAssistant = null;
      continue;
    }

    if (kind.startsWith("tool.")) {
      activeAssistant = null;
      const key = `${attempt}:${entity}`;
      let row = entity ? tools.get(key) : undefined;
      if (!row) {
        row = {
          id: `tool-${rows.length}`,
          attempt,
          kind: "tool",
          entity: entity || undefined,
          text: String(data.tool ?? data.name ?? "Tool activity"),
          data,
        };
        rows.push(row);
        if (entity) tools.set(key, row);
      }
      if (kind === "tool.completed") {
        row.state = String(data.status ?? "completed");
        if (data.output !== undefined) {
          row.output = typeof data.output === "string" ? data.output : JSON.stringify(data.output);
        }
        row.data = { ...row.data, ...data };
      } else {
        row.state = "running";
      }
      continue;
    }

    if (kind === "telemetry.updated") continue;

    activeAssistant = null;
    rows.push({
      id: `event-${rows.length}`,
      attempt,
      kind,
      entity: entity || undefined,
      text: typeof data.text === "string" ? data.text : JSON.stringify(data),
      data,
    });
  }
  return rows;
}
