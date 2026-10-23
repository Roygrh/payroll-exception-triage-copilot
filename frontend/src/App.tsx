import { useEffect, useState } from "react";
import { api, errorText } from "./api/client";
import type { Context } from "./api/types";
import { Header } from "./components/Header";
import { ErrorNote } from "./components/ui";
import { AuditPage } from "./pages/AuditPage";
import { CaseDetailPage } from "./pages/CaseDetailPage";
import { ConfirmMessagePage } from "./pages/ConfirmMessagePage";
import { QueuePage } from "./pages/QueuePage";
import { useRoute } from "./router";

export function App() {
  const route = useRoute();
  const [context, setContext] = useState<Context | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .context()
      .then(setContext)
      .catch((e) => setError(errorText(e)));
  }, []);

  return (
    <div className="min-h-screen bg-page">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:bg-white focus:p-2">
        Skip to content
      </a>
      <Header context={context} />
      <main id="main" tabIndex={-1} className="mx-auto max-w-7xl px-4 py-5 focus:outline-none">
        {error && (
          <div className="mb-4">
            <ErrorNote>The API is not reachable ({error}). Start it with "uv run ptc serve" in backend/.</ErrorNote>
          </div>
        )}
        {route.name === "queue" && <QueuePage context={context} />}
        {route.name === "case" && <CaseDetailPage key={route.id} id={route.id} context={context} />}
        {route.name === "message" && <ConfirmMessagePage key={route.id} id={route.id} context={context} />}
        {route.name === "audit" && <AuditPage key={route.id} id={route.id} />}
      </main>
    </div>
  );
}
