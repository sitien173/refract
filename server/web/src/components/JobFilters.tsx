import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { JobPage } from "../api";

// Radix Select forbids empty item values, so real values are namespaced and the
// "all" choice uses a sentinel that no real option can collide with.
const ALL = "__refract_all_filters__";
const encode = (value: string) => `option:${encodeURIComponent(value)}`;
const decode = (value: string) => (value === ALL ? "" : decodeURIComponent(value.slice("option:".length)));

type FilterItem = { value: string; label: string };
type JobFiltersProps = {
  filters: Record<string, string>;
  options: JobPage["options"];
  onChange: (key: string, value: string) => void;
};

export function JobFilters({ filters, options, onChange }: JobFiltersProps) {
  const [query, setQuery] = useState(filters.q ?? "");
  useEffect(() => setQuery(filters.q ?? ""), [filters.q]);

  const renderFilter = (key: string, label: string, items: FilterItem[]) => (
    <label key={key} className="flex flex-col gap-(--gap-xs)">
      <span className="tds-field-label">{label}</span>
      <Select value={filters[key] ? encode(filters[key]) : ALL} onValueChange={(value) => onChange(key, decode(value))}>
        <SelectTrigger aria-label={`Filter by ${label.toLowerCase()}`}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>All {label.toLowerCase()}s</SelectItem>
          {items.map((item) => (
            <SelectItem key={item.value} value={encode(item.value)}>
              {item.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </label>
  );

  const same = (values: string[]) => values.map((value) => ({ value, label: value }));

  return (
    <div className="flex flex-wrap items-end gap-(--gap-sm)">
      <label className="flex flex-col gap-(--gap-xs)">
        <span className="tds-field-label">Search jobs</span>
        <Input
          aria-label="Search jobs"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onChange("q", query);
          }}
        />
      </label>
      <Button onClick={() => onChange("q", query)}>Search</Button>
      {renderFilter("state", "State", same(options.states))}
      {renderFilter("project", "Project", options.projects.map((p) => ({ value: p.id, label: p.root })))}
      {renderFilter("workflow", "Workflow", same(options.workflows))}
      {renderFilter("target", "Target", same(options.targets))}
    </div>
  );
}
