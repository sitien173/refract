import * as DialogPrimitive from "@radix-ui/react-dialog";
import * as React from "react";
import { cn } from "@/lib/utils";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;
export const DialogPortal = DialogPrimitive.Portal;
export const DialogOverlay = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay ref={ref} className={cn("tds-dialog__backdrop", className)} {...props} />
));
DialogOverlay.displayName = "DialogOverlay";
export const DialogContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, ...props }, ref) => (
  <DialogPrimitive.Portal>
    <div className="tds-dialog tds-dialog--center tds-dialog--md tds-dialog--open">
      <DialogOverlay />
      <DialogPrimitive.Content ref={ref} className={cn("tds-dialog__panel", className)} {...props}>
        {children}
      </DialogPrimitive.Content>
    </div>
  </DialogPrimitive.Portal>
));
DialogContent.displayName = "DialogContent";
export const DialogHeader = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => <header className={cn("tds-dialog__header", className)} {...props} />;
export const DialogTitle = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => <DialogPrimitive.Title ref={ref} className={cn("tds-dialog__title", className)} {...props} />);
DialogTitle.displayName = "DialogTitle";
export const DialogDescription = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => <DialogPrimitive.Description ref={ref} className={cn("tds-dialog__text", className)} {...props} />);
DialogDescription.displayName = "DialogDescription";
export const DialogFooter = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => <footer className={cn("tds-dialog__footer", className)} {...props} />;
