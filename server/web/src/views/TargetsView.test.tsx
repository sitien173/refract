import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { TargetsView } from "./TargetsView";

const target = {
  id: "local",
  model: "model-x",
  backend: "codex",
  isolated: false,
  read_only: true,
  max_concurrency: 3,
  active: 1,
  healthy: true,
  circuit_open_until: "",
  breaker_state: "closed" as const,
  cooldown_s: 0,
  probing: false,
};
const config = {
  attempted_at: "",
  successful_at: "",
  source_path: "/etc/refract.toml",
  modification_time: "",
  revision: "r1",
  valid: true,
  latest_error: "",
  last_known_good_revision: "r1",
};
it("renders real target details and valid config health", () => {
  render(<TargetsView targets={[target]} config={config} loading={false} error={null} onNavigate={vi.fn()} />);
  expect(screen.getByText("local")).toBeInTheDocument();
  expect(screen.getByText("model-x")).toBeInTheDocument();
  expect(screen.getByText("codex")).toBeInTheDocument();
  expect(screen.getByText("Healthy")).toBeInTheDocument();
  expect(screen.getByText("closed")).toBeInTheDocument();
  expect(screen.getByText("1/3")).toBeInTheDocument();
  expect(screen.getByText(/Configuration is valid/)).toBeInTheDocument();
});
it("shows config errors, fetch errors, and an in-app console control", () => {
  render(<TargetsView targets={[]} config={{ ...config, valid: false, latest_error: "bad config" }} loading={false} error="Network down" onNavigate={vi.fn()} />);
  expect(screen.getAllByRole("alert")[0]).toHaveTextContent("Network down");
  expect(screen.getByText("bad config")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Back to console" })).toBeInTheDocument();
});
it("shows a loading state without claiming no targets", () => {
  render(<TargetsView targets={[]} config={config} loading error={null} onNavigate={vi.fn()} />);
  expect(screen.getByText("Loading targets…")).toBeInTheDocument();
  expect(screen.queryByText("No targets configured.")).not.toBeInTheDocument();
});
