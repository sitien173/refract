import { cleanup, render } from "@testing-library/react";
import { JobActions } from "../components/JobActions";
import { ConsoleView } from "../views/ConsoleView";

/**
 * Radix Select, the resizable panels and the dialogs cost several hundred
 * milliseconds on their first render in a fresh worker. Paying that in a
 * `beforeAll` keeps it out of whichever test happens to run first, so a busy
 * machine cannot push an unrelated assertion past the default test timeout.
 */
export function warmUpComponents() {
  render(
    <ConsoleView
      jobs={[]}
      selectedId={null}
      onSelect={() => {}}
      filters={{}}
      options={{ states: [], projects: [], workflows: [], targets: [] }}
      onFilter={() => {}}
      detail={null}
      events={[]}
      announcement=""
      actions={
        <JobActions
          jobId="warm"
          state="running"
          busy={false}
          pendingQuestion={{ question_id: "q", text: "?" }}
          onCancel={() => {}}
          onRetry={() => {}}
          onAnswer={() => {}}
        />
      }
    />,
  );
  cleanup();
}
