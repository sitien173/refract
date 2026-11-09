import { Button as ButtonPrimitive } from "@base-ui/react/button";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium transition-transform duration-(--duration-fast) ease-(--ease-out) select-none active:scale-[0.97] disabled:pointer-events-none disabled:opacity-50 disabled:active:scale-100",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary-hover",
        secondary: "bg-secondary text-secondary-foreground hover:bg-muted",
        outline: "border border-input bg-card text-foreground hover:bg-accent",
        destructive: "bg-destructive text-destructive-foreground hover:opacity-90",
        ghost: "text-foreground hover:bg-accent",
      },
      size: {
        sm: "h-8 px-3 text-[0.8125rem]",
        default: "h-9 px-4 text-sm",
        lg: "h-11 px-5 text-base",
        icon: "size-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps extends ButtonPrimitive.Props, VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, size, type = "button", ...props }: ButtonProps) {
  return <ButtonPrimitive data-slot="button" type={type} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
