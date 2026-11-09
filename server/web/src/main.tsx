import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import "./styles/globals.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      networkMode: "always",
      refetchOnWindowFocus: true,
      refetchIntervalInBackground: false,
    },
    mutations: {
      retry: false,
      networkMode: "always",
    },
  },
});

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root element");

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
