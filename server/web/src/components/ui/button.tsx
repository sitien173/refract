import * as React from "react";
import { cn } from "@/lib/utils";

type Variant = "default" | "secondary" | "outline" | "destructive" | "ghost";
type Size = "sm" | "default" | "lg" | "icon";
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const variants: Record<Variant, string> = {
  default: "tds-btn--primary",
  secondary: "tds-btn--secondary",
  outline: "tds-btn--secondary",
  destructive: "tds-btn--danger",
  ghost: "tds-btn--invisible",
};
const sizes: Record<Exclude<Size, "icon">, string> = {
  sm: "tds-btn--sm",
  default: "tds-btn--md",
  lg: "tds-btn--lg",
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "default", type = "button", ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={cn(size === "icon" ? "tds-icon-btn tds-icon-btn--md tds-icon-btn--invisible" : `tds-btn ${sizes[size]} ${variants[variant]}`, className)}
      {...props}
    />
  ),
);
Button.displayName = "Button";
