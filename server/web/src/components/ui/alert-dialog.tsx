import { AlertDialog as AlertDialogPrimitive } from "@base-ui/react/alert-dialog";
import type * as React from "react";
import { cn } from "@/lib/utils";

export const AlertDialog = AlertDialogPrimitive.Root;

export const AlertDialogTrigger = AlertDialogPrimitive.Trigger;
export const AlertDialogCancel = AlertDialogPrimitive.Close;
export const AlertDialogAction = AlertDialogPrimitive.Close;

export function AlertDialogContent({ className, children, ...props }: AlertDialogPrimitive.Popup.Props) {
  return (
    <AlertDialogPrimitive.Portal>
      <AlertDialogPrimitive.Backdrop data-slot="alert-dialog-overlay" className="fixed inset-0 z-50 bg-scrim" />
      <AlertDialogPrimitive.Popup
        data-slot="alert-dialog-content"
        className={cn("fixed top-1/2 left-1/2 z-50 flex w-[calc(100vw-2rem)] max-w-sm flex-col gap-4 rounded-lg bg-popover p-6 text-popover-foreground shadow-dialog", className)}
        {...props}
      >
        {children}
      </AlertDialogPrimitive.Popup>
    </AlertDialogPrimitive.Portal>
  );
}

export function AlertDialogHeader({ className, ...props }: React.ComponentProps<"header">) {
  return <header data-slot="alert-dialog-header" className={cn("flex flex-col gap-1.5", className)} {...props} />;
}

export function AlertDialogTitle({ className, ...props }: AlertDialogPrimitive.Title.Props) {
  return <AlertDialogPrimitive.Title data-slot="alert-dialog-title" className={cn("text-lg font-semibold tracking-tight", className)} {...props} />;
}

export function AlertDialogDescription({ className, ...props }: AlertDialogPrimitive.Description.Props) {
  return <AlertDialogPrimitive.Description data-slot="alert-dialog-description" className={cn("text-sm text-muted-foreground", className)} {...props} />;
}

export function AlertDialogFooter({ className, ...props }: React.ComponentProps<"footer">) {
  return <footer data-slot="alert-dialog-footer" className={cn("flex justify-end gap-2", className)} {...props} />;
}
