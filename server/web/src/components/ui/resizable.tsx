import * as React from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { cn } from "@/lib/utils";

function ResizablePanelGroup({ className, ...props }: React.ComponentProps<typeof PanelGroup>) {
  return <PanelGroup className={cn("flex h-full w-full", className)} {...props} />;
}

const ResizablePanel = Panel;

// There is no TDS divider component, so the handle uses TDS tokens only.
// Keyboard resizing (arrows, Home/End, F6) is implemented by the library.
function ResizableHandle({
  className,
  style,
  "aria-label": ariaLabel = "Resize panels",
  ...props
}: React.ComponentProps<typeof PanelResizeHandle>) {
  return (
    <PanelResizeHandle
      aria-label={ariaLabel}
      className={cn("cursor-col-resize", className)}
      style={{ background: "var(--border-subtle)", width: "var(--spacing-8)", ...style }}
      {...props}
    />
  );
}

export { ResizableHandle, ResizablePanel, ResizablePanelGroup };
