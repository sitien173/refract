import { Tabs as TabsPrimitive } from "@base-ui/react/tabs";
import { cn } from "@/lib/utils";

export function Tabs({ className, ...props }: TabsPrimitive.Root.Props) {
  return <TabsPrimitive.Root data-slot="tabs" className={cn("flex flex-col gap-3", className)} {...props} />;
}

export function TabsList({ className, ...props }: TabsPrimitive.List.Props) {
  return <TabsPrimitive.List data-slot="tabs-list" className={cn("inline-flex w-fit items-center gap-1 rounded-md bg-secondary p-1", className)} {...props} />;
}

export function TabsTrigger({ className, ...props }: TabsPrimitive.Tab.Props) {
  return (
    <TabsPrimitive.Tab
      data-slot="tabs-trigger"
      className={cn(
        "inline-flex h-7 items-center justify-center rounded-sm px-3 text-sm font-medium text-muted-foreground data-active:bg-card data-active:text-foreground data-active:shadow-card",
        className,
      )}
      {...props}
    />
  );
}

export function TabsContent({ className, ...props }: TabsPrimitive.Panel.Props) {
  return <TabsPrimitive.Panel data-slot="tabs-content" className={cn("outline-none", className)} {...props} />;
}
