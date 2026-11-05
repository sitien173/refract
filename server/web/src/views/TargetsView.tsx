import { Button } from "@/components/ui/button";
import type { ConfigHealth, TargetView } from "../api";

type TargetsViewProps = {
  targets: TargetView[];
  config: ConfigHealth | null;
  loading: boolean;
  error: string | null;
  onNavigate: () => void;
};

const yesNo = (value: boolean) => (value ? "Yes" : "No");

function ConfigurationSection({ config }: { config: ConfigHealth }) {
  return (
    <section aria-label="Configuration">
      <h2 className="text-heading-lg">Configuration</h2>
      {config.valid ? (
        <p>
          Configuration is valid. Source: {config.source_path}. Revision: {config.revision}.
        </p>
      ) : (
        <div className="tds-announcement tds-announcement--error" role="alert">
          <h3>Configuration error</h3>
          <p>{config.latest_error || "Configuration is not loaded."}</p>
          <p>Source: {config.source_path}</p>
        </div>
      )}
    </section>
  );
}

function TargetCard({ target }: { target: TargetView }) {
  return (
    <article className="flex flex-col gap-(--gap-sm) p-(--padding-md)">
      <h3 className="text-heading-md">{target.id}</h3>
      <dl className="grid grid-cols-2 gap-(--gap-sm)">
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
    <main className="flex flex-col gap-(--gap-md) p-(--padding-xl)">
      <header className="flex items-center justify-between">
        <h1 className="text-heading-xl">Targets</h1>
        <Button variant="secondary" onClick={onNavigate}>
          Back to console
        </Button>
      </header>
      {error && (
        <div className="tds-announcement tds-announcement--error" role="alert">
          {error}
        </div>
      )}
      {loading && <p role="status">Loading targets…</p>}
      {!loading && config && <ConfigurationSection config={config} />}
      {!loading && !error && targets.length === 0 && <p>No targets configured.</p>}
      {!loading && targets.length > 0 && (
        <section aria-label="Targets">
          <h2 className="text-heading-lg">Targets</h2>
          <div className="flex flex-col gap-(--gap-md)">
            {targets.map((target) => (
              <TargetCard key={target.id} target={target} />
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
