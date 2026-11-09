import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { JobPage } from "../api";

const FIELD_LABEL = "text-[0.8125rem] font-medium text-muted-foreground";

type FilterItem = { value: string; label: string };
type JobFiltersProps = {
  filters: Record<string, string>;
  options: JobPage["options"];
  onChange: (key: string, value: string) => void;
};

export function JobFilters({ filters, options, onChange }: JobFiltersProps) {
  const [query, setQuery] = useState(filters.q ?? "");
  useEffect(() => setQuery(filters.q ?? ""), [filters.q]);

  // The null item stands for "no filter": it shows the "All ..." label and reports the empty value.
  const renderFilter = (key: string, label: string, items: FilterItem[]) => {
    const choices = [{ value: null, label: `All ${label.toLowerCase()}s` }, ...items];
    return (
      <div key={key} className="flex flex-col gap-1">
        <span className={FIELD_LABEL}>{label}</span>
        <Select items={choices} value={filters[key] || null} onValueChange={(value) => onChange(key, value ?? "")}>
          <SelectTrigger aria-label={`Filter by ${label.toLowerCase()}`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {choices.map((item) => (
              <SelectItem key={item.value === null ? "none" : `value:${item.value}`} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    );
  };

  const same = (values: string[]) => values.map((value) => ({ value, label: value }));

  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="flex flex-col gap-1" htmlFor="job-search">
        <span className={FIELD_LABEL}>Search jobs</span>
        <Input
          id="job-search"
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
      {renderFilter(
        "project",
        "Project",
        options.projects.map((p) => ({ value: p.id, label: p.root })),
      )}
      {renderFilter("workflow", "Workflow", same(options.workflows))}
      {renderFilter("target", "Target", same(options.targets))}
    </div>
  );
}
