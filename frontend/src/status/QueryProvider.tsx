/**
 * Gate 4A2 — the one `QueryClient` for the app. React Query owns every piece
 * of authoritative server state (scenarios, dashboard, decision options,
 * preview, resolution, history, saves); this provider is what makes that
 * cache available to every screen.
 *
 * `refetchOnWindowFocus: false` -- a local single-player desktop game gained
 * no value from silently refetching on tab focus, and it would fight the
 * explicit stale-revision recovery flow (a refetch happens because the
 * player asked, or because a mutation's own `onSuccess` seeded fresh data,
 * never behind their back). `retry: false` -- a failed request surfaces as a
 * structured error immediately; silently retrying would hide a real
 * `resolution_in_progress` or `stale_revision` behind extra latency.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";

export function AppQueryProvider({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: false,
            retry: false,
          },
          mutations: {
            retry: false,
          },
        },
      }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
