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

export type StreamEvent = Record<string, unknown>;

export type TranscriptState = {
  readonly rows: readonly TranscriptRow[];
  readonly toolIndices: ReadonlyMap<string, number>;
  readonly assistantIndices: ReadonlyMap<string, number>;
  readonly activeAssistantIndex: number | null;
};

const DEFAULT_ATTEMPT = 1;

export function initialTranscriptState(): TranscriptState {
  return {
    rows: [],
    toolIndices: new Map(),
    assistantIndices: new Map(),
    activeAssistantIndex: null,
  };
}

/**
 * Incrementally applies raw stream events to a transcript state.
 * Rows are creation-numbered with IDs `${kind}-${n}`, lookup maps
 * pair tool and assistant events by `${attempt}:${entity}`, and each
 * batch copies the row array once and copies only the rows it changes.
 */
export function apply(state: TranscriptState = initialTranscriptState(), events: readonly StreamEvent[]): TranscriptState {
  if (events.length === 0) return state;

  const nextRows: TranscriptRow[] = [...state.rows];
  const initialRowCount = state.rows.length;
  const clonedIndices = new Set<number>();

  let nextToolIndices = state.toolIndices;
  let toolIndicesCopied = false;

  let nextAssistantIndices = state.assistantIndices;
  let assistantIndicesCopied = false;

  let activeAssistantIndex = state.activeAssistantIndex;

  const ensureRowCloned = (index: number): TranscriptRow => {
    const existing = nextRows[index];
    if (!existing) throw new Error(`Row index out of range: ${index}`);
    if (index < initialRowCount && !clonedIndices.has(index)) {
      const cloned = { ...existing };
      nextRows[index] = cloned;
      clonedIndices.add(index);
      return cloned;
    }
    return existing;
  };

  const createAssistant = (entity: string, attempt: number) => {
    const row: TranscriptRow = {
      id: `assistant-${nextRows.length}`,
      attempt,
      kind: "assistant",
      entity: entity || undefined,
      text: "",
    };
    const index = nextRows.length;
    nextRows.push(row);
    if (entity) {
      if (!assistantIndicesCopied) {
        nextAssistantIndices = new Map(nextAssistantIndices);
        assistantIndicesCopied = true;
      }
      (nextAssistantIndices as Map<string, number>).set(`${attempt}:${entity}`, index);
    }
    activeAssistantIndex = index;
    return row;
  };

  for (const event of events) {
    const kind = String(event.kind ?? event.type ?? "unknown");
    const data = (event.data && typeof event.data === "object" ? event.data : event) as Record<string, unknown>;
    const attempt = Number(event.attempt ?? data.attempt ?? DEFAULT_ATTEMPT);
    const entity = String(event.entity_id ?? data.entity_id ?? "");

    if (kind === "assistant.text.delta") {
      const text = String(data.text ?? data.text_delta ?? "");
      const previous = activeAssistantIndex !== null ? nextRows[activeAssistantIndex] : null;
      const continues = Boolean(previous && previous.entity === (entity || undefined) && previous.attempt === attempt);
      if (continues && activeAssistantIndex !== null) {
        const row = ensureRowCloned(activeAssistantIndex);
        row.text += text;
      } else {
        const row = createAssistant(entity, attempt);
        row.text += text;
      }
      continue;
    }

    if (kind === "assistant.message.started") {
      createAssistant(entity, attempt);
      continue;
    }

    if (kind === "assistant.message.completed") {
      const targetIndex = entity ? nextAssistantIndices.get(`${attempt}:${entity}`) : (activeAssistantIndex ?? undefined);
      if (targetIndex !== undefined) {
        const row = ensureRowCloned(targetIndex);
        row.state = "completed";
      }
      activeAssistantIndex = null;
      continue;
    }

    if (kind.startsWith("tool.")) {
      activeAssistantIndex = null;
      const key = `${attempt}:${entity}`;
      let rowIndex = entity ? nextToolIndices.get(key) : undefined;
      if (rowIndex === undefined) {
        const row: TranscriptRow = {
          id: `tool-${nextRows.length}`,
          attempt,
          kind: "tool",
          entity: entity || undefined,
          text: String(data.tool ?? data.name ?? "Tool activity"),
          data,
        };
        rowIndex = nextRows.length;
        nextRows.push(row);
        if (entity) {
          if (!toolIndicesCopied) {
            nextToolIndices = new Map(nextToolIndices);
            toolIndicesCopied = true;
          }
          (nextToolIndices as Map<string, number>).set(key, rowIndex);
        }
      }
      const row = ensureRowCloned(rowIndex);
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

    activeAssistantIndex = null;
    nextRows.push({
      id: `event-${nextRows.length}`,
      attempt,
      kind,
      entity: entity || undefined,
      text: typeof data.text === "string" ? data.text : JSON.stringify(data),
      data,
    });
  }

  return {
    rows: nextRows,
    toolIndices: nextToolIndices,
    assistantIndices: nextAssistantIndices,
    activeAssistantIndex,
  };
}

/**
 * Convenience oracle for tests: folds all events in one batch.
 */
export function reduceTranscript(events: readonly StreamEvent[]): TranscriptRow[] {
  return [...apply(initialTranscriptState(), events).rows];
}
