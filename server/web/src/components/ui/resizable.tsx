import type * as React from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { cn } from "@/lib/utils";

function ResizablePanelGroup({ className, ...props }: React.ComponentProps<typeof PanelGroup>) {
  return <PanelGroup className={cn("flex h-full w-full", className)} {...props} />;
}

const ResizablePanel = Panel;

// Keyboard resizing (arrows, Home/End, F6) is implemented by the library.
function ResizableHandle({ className, "aria-label": ariaLabel = "Resize panels", ...props }: React.ComponentProps<typeof PanelResizeHandle>) {
  return (
    <PanelResizeHandle
      aria-label={ariaLabel}
      className={cn("mx-1 w-1 shrink-0 cursor-col-resize rounded-full bg-border hover:bg-input data-[resize-handle-state=drag]:bg-primary", className)}
      {...props}
    />
  );
}

export { ResizableHandle, ResizablePanel, ResizablePanelGroup };
