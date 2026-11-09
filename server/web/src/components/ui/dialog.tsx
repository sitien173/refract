import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import type * as React from "react";
import { cn } from "@/lib/utils";

export const Dialog = DialogPrimitive.Root;

export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

export function DialogContent({ className, children, ...props }: DialogPrimitive.Popup.Props) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Backdrop data-slot="dialog-overlay" className="fixed inset-0 z-50 bg-scrim" />
      <DialogPrimitive.Popup
        data-slot="dialog-content"
        className={cn("fixed top-1/2 left-1/2 z-50 flex w-[calc(100vw-2rem)] max-w-md flex-col gap-4 rounded-lg bg-popover p-6 text-popover-foreground shadow-dialog", className)}
        {...props}
      >
        {children}
      </DialogPrimitive.Popup>
    </DialogPrimitive.Portal>
  );
}

export function DialogHeader({ className, ...props }: React.ComponentProps<"header">) {
  return <header data-slot="dialog-header" className={cn("flex flex-col gap-1.5", className)} {...props} />;
}

export function DialogTitle({ className, ...props }: DialogPrimitive.Title.Props) {
  return <DialogPrimitive.Title data-slot="dialog-title" className={cn("text-lg font-semibold tracking-tight", className)} {...props} />;
}

export function DialogDescription({ className, ...props }: DialogPrimitive.Description.Props) {
  return <DialogPrimitive.Description data-slot="dialog-description" className={cn("text-sm text-muted-foreground", className)} {...props} />;
}

export function DialogFooter({ className, ...props }: React.ComponentProps<"footer">) {
  return <footer data-slot="dialog-footer" className={cn("flex justify-end gap-2", className)} {...props} />;
}
