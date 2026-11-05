import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import { settle } from "../test/async";
import { warmUpComponents } from "../test/warmup";
import { JobActions } from "./JobActions";

type Props = React.ComponentProps<typeof JobActions>;
const question = { question_id: "q1", text: "Proceed?" };
const props = (overrides: Partial<Props> = {}): Props => ({
  jobId: "j1",
  state: "running",
  busy: false,
  pendingQuestion: null,
  onCancel: vi.fn(),
  onRetry: vi.fn(),
  onAnswer: vi.fn(),
  ...overrides,
});
const typeAnswer = (value: string) => {
  fireEvent.click(screen.getByRole("button", { name: "Answer question" }));
  fireEvent.change(screen.getByLabelText("Your answer"), { target: { value } });
};

beforeAll(warmUpComponents);
beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

it("confirms cancellation before calling onCancel", async () => {
  const onCancel = vi.fn();
  render(<JobActions {...props({ onCancel })} />);
  fireEvent.click(screen.getByRole("button", { name: "Cancel job" }));
  await settle();
  expect(screen.getByRole("alertdialog")).toBeInTheDocument();
  expect(onCancel).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Confirm cancellation" }));
  await settle();
  expect(onCancel).toHaveBeenCalledTimes(1);
});

it("sends question_id with the answer and closes the dialog", async () => {
  const onAnswer = vi.fn().mockResolvedValue(undefined);
  render(<JobActions {...props({ pendingQuestion: question, onAnswer })} />);
  typeAnswer("Yes");
  fireEvent.click(screen.getByRole("button", { name: "Send answer" }));
  await settle();
  expect(onAnswer).toHaveBeenCalledWith("q1", "Yes");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("keeps a failed answer and draft in the dialog with an inline error", async () => {
  const onAnswer = vi.fn().mockRejectedValue(Error("question expired"));
  render(<JobActions {...props({ pendingQuestion: question, onAnswer })} />);
  typeAnswer("Keep this");
  fireEvent.click(screen.getByRole("button", { name: "Send answer" }));
  await settle();
  expect(screen.getByRole("alert")).toHaveTextContent("question expired");
  expect(screen.getByLabelText("Your answer")).toHaveValue("Keep this");
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});

it("clears the answer draft when switching jobs", () => {
  const { rerender } = render(<JobActions {...props({ jobId: "one", pendingQuestion: { question_id: "q1", text: "Question one" } })} />);
  typeAnswer("old draft");
  rerender(<JobActions {...props({ jobId: "two", pendingQuestion: { question_id: "q2", text: "Question two" } })} />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Answer question" }));
  expect(screen.getByLabelText("Your answer")).toHaveValue("");
});

it("disables cancellation for terminal jobs and retry for nonterminal jobs", () => {
  const { rerender } = render(<JobActions {...props({ state: "succeeded" })} />);
  expect(screen.getByRole("button", { name: "Cancel job" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Retry job" })).toBeEnabled();
  rerender(<JobActions {...props({ state: "running" })} />);
  expect(screen.getByRole("button", { name: "Cancel job" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Retry job" })).toBeDisabled();
});

it("disables every action while a request is active", () => {
  render(<JobActions {...props({ busy: true, pendingQuestion: question })} />);
  expect(screen.getByRole("button", { name: "Cancel job" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Retry job" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Answer question" })).toBeDisabled();
});
