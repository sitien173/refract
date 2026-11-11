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

it("groups targets by backend sorted by name with target count and healthy count in heading", () => {
  const multiTargets = [
    { ...target, id: "codex-1", backend: "codex", healthy: true },
    { ...target, id: "codex-2", backend: "codex", healthy: true },
    { ...target, id: "codex-3", backend: "codex", healthy: false },
    { ...target, id: "anthropic-1", backend: "anthropic", healthy: true },
  ];

  const { container } = render(<TargetsView targets={multiTargets} config={config} loading={false} error={null} onNavigate={vi.fn()} />);

  const sections = container.querySelectorAll("section[aria-labelledby]");
  expect(sections).toHaveLength(2);

  // Group headings in alphabetical order of backend name with index-based ids
  const headings = container.querySelectorAll("section[aria-labelledby] > h3");
  expect(headings).toHaveLength(2);
  expect(headings[0].textContent).toBe("anthropic · 1 target · 1 healthy");
  expect(headings[0].id).toBe("backend-0-heading");
  expect(sections[0].getAttribute("aria-labelledby")).toBe("backend-0-heading");
  expect(headings[1].textContent).toBe("codex · 3 targets · 2 healthy");
  expect(headings[1].id).toBe("backend-1-heading");
  expect(sections[1].getAttribute("aria-labelledby")).toBe("backend-1-heading");

  // Cards container uses grid
  const grids = container.querySelectorAll(".grid.gap-3.sm\\:grid-cols-2");
  expect(grids).toHaveLength(2);
});
