import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        networkMode: "always",
        gcTime: Number.POSITIVE_INFINITY,
      },
      mutations: {
        retry: false,
        networkMode: "always",
        gcTime: Number.POSITIVE_INFINITY,
      },
    },
  });
}

export function createQueryWrapper(queryClient = createTestQueryClient()) {
  // biome-ignore lint/correctness/noComponentHookFactories: Test wrapper factory
  return function QueryWrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}
