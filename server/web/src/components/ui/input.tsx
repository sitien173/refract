import * as React from "react";
import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <div className="tds-text-input">
      <input ref={ref} className={cn("tds-text-input__field", className)} {...props} />
    </div>
  ),
);
Input.displayName = "Input";
