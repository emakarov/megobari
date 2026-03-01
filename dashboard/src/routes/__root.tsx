import { useState, useCallback, useEffect } from "react";
import {
  createRootRouteWithContext,
  HeadContent,
  Outlet,
  Scripts,
  useRouter,
} from "@tanstack/react-router";
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { hasToken } from "@/lib/api";
import { Login } from "@/components/login";
import { AppLayout } from "@/components/layout/app-layout";
import appCss from "@/index.css?url";

interface RouterContext {
  queryClient: QueryClient;
}

export const Route = createRootRouteWithContext<RouterContext>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "Megobari Dashboard" },
    ],
    links: [{ rel: "stylesheet", href: appCss }],
  }),
  component: RootComponent,
});

function RootComponent() {
  // Start as null (unknown) to avoid hydration mismatch
  const [authed, setAuthed] = useState<boolean | null>(null);
  const { queryClient } = Route.useRouteContext();
  const router = useRouter();

  const handleLogin = useCallback(() => {
    // Clear cached 401 errors and re-run route loaders with new token
    queryClient.clear();
    router.invalidate();
    setAuthed(true);
  }, [queryClient, router]);

  // Check auth only on the client after hydration
  useEffect(() => {
    setAuthed(hasToken());
  }, []);

  return (
    <html lang="en" className="dark">
      <head>
        <HeadContent />
      </head>
      <body className="bg-background text-foreground">
        <QueryClientProvider client={queryClient}>
          {authed === null ? (
            // Loading state during hydration - matches server-rendered shell
            <div className="flex min-h-screen items-center justify-center">
              <div className="animate-pulse text-muted-foreground">Loading...</div>
            </div>
          ) : authed ? (
            <AppLayout>
              <Outlet />
            </AppLayout>
          ) : (
            <Login onLogin={handleLogin} />
          )}
        </QueryClientProvider>
        <Scripts />
      </body>
    </html>
  );
}
