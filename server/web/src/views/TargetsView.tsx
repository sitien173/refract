import { Button } from "@/components/ui/button";
import type { ConfigHealth, TargetView } from "../api";
import { ViewNav } from "../components/ViewNav";

type TargetsViewProps = {
  targets: TargetView[];
  config: ConfigHealth | null;
  loading: boolean;
  error: string | null;
  onNavigate: (path: string) => void;
};

const yesNo = (value: boolean) => (value ? "Yes" : "No");

function ConfigurationSection({ config }: { config: ConfigHealth }) {
  return (
    <section aria-label="Configuration" className="flex flex-col gap-2">
      <h2 className="text-xl font-semibold tracking-tight">Configuration</h2>
      {config.valid ? (
        <p className="text-sm text-muted-foreground">
          Configuration is valid. Source: {config.source_path}. Revision: {config.revision}.
        </p>
      ) : (
        <div className="callout callout-error" role="alert">
          <h3 className="font-semibold">Configuration error</h3>
          <p>{config.latest_error || "Configuration is not loaded."}</p>
          <p>Source: {config.source_path}</p>
        </div>
      )}
    </section>
  );
}

function TargetCard({ target }: { target: TargetView }) {
  return (
    <article className="flex flex-col gap-3 rounded-lg bg-card p-5 shadow-card">
      <h3 className="text-lg font-semibold tracking-tight">{target.id}</h3>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1.5 text-sm [&>dt]:text-muted-foreground">
        <dt>Backend</dt>
        <dd>{target.backend}</dd>
        <dt>Model</dt>
        <dd>{target.model}</dd>
        <dt>Health</dt>
        <dd>{target.healthy ? "Healthy" : "Unhealthy"}</dd>
        <dt>Breaker state</dt>
        <dd>{target.breaker_state.replaceAll("_", " ")}</dd>
        <dt>Concurrency</dt>
        <dd>
          {target.active}/{target.max_concurrency}
        </dd>
        <dt>Open until</dt>
        <dd>{target.circuit_open_until || "Not open"}</dd>
        <dt>Cooldown</dt>
        <dd>{target.cooldown_s} s</dd>
        <dt>Probing</dt>
        <dd>{yesNo(target.probing)}</dd>
        <dt>Isolated</dt>
        <dd>{yesNo(target.isolated)}</dd>
        <dt>Read only</dt>
        <dd>{yesNo(target.read_only)}</dd>
      </dl>
    </article>
  );
}

export function TargetsView({ targets, config, loading, error, onNavigate }: TargetsViewProps) {
  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-4 p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Targets</h1>
        <div className="flex items-center gap-3">
          <ViewNav current="targets" onNavigate={onNavigate} />
          <Button variant="secondary" onClick={() => onNavigate("/dashboard/")}>
            Back to console
          </Button>
        </div>
      </header>
      {error && (
        <div className="callout callout-error" role="alert">
          {error}
        </div>
      )}
      {loading && (
        <p role="status" className="text-sm text-muted-foreground">
          Loading targets…
        </p>
      )}
      {!loading && config && <ConfigurationSection config={config} />}
      {!loading && !error && targets.length === 0 && <p className="text-sm text-muted-foreground">No targets configured.</p>}
      {!loading && targets.length > 0 && (
        <section aria-label="Targets" className="flex flex-col gap-3">
          <h2 className="text-xl font-semibold tracking-tight">Targets</h2>
          <div className="flex flex-col gap-4">
            {targets.map((target) => (
              <TargetCard key={target.id} target={target} />
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
