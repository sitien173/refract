import { Input as InputPrimitive } from "@base-ui/react/input";
import { cn } from "@/lib/utils";

export function Input({ className, ...props }: InputPrimitive.Props) {
  return (
    <InputPrimitive
      data-slot="input"
      className={cn(
        "h-9 w-full min-w-0 rounded-md border border-input bg-card px-3 text-sm text-foreground placeholder:text-muted-foreground disabled:pointer-events-none disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
