import { cn } from "@/lib/utils";

export type ViewNavProps = {
  current: "console" | "board" | "targets";
  onNavigate: (path: string) => void;
};

const LINKS = [
  { view: "console", label: "Console", href: "/dashboard/" },
  { view: "board", label: "Board", href: "/dashboard/board" },
  { view: "targets", label: "Targets", href: "/dashboard/targets" },
] as const;

export function ViewNav({ current, onNavigate }: ViewNavProps) {
  const activeView = current;

  return (
    <nav aria-label="Views" className="flex items-center gap-2">
      {LINKS.map((link) => {
        const isCurrent = activeView === link.view;
        return (
          <a
            key={link.view}
            href={link.href}
            aria-current={isCurrent ? "page" : undefined}
            onClick={(e) => {
              e.preventDefault();
              onNavigate(link.href);
            }}
            className={cn(
              "inline-flex items-center justify-center rounded-md px-3 py-1.5 text-sm font-medium transition-colors select-none",
              isCurrent ? "bg-secondary text-secondary-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            {link.label}
          </a>
        );
      })}
    </nav>
  );
}
