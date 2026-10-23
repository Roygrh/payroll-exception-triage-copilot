import { useEffect, useState } from "react";

// Hash routes, so the built UI works as static files with no server rewrite.
export type Route =
  | { name: "queue" }
  | { name: "case"; id: string }
  | { name: "message"; id: string }
  | { name: "audit"; id: string };

export function parseHash(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (parts[0] === "cases" && parts[1]) {
    const id = decodeURIComponent(parts[1]);
    if (parts[2] === "message") return { name: "message", id };
    if (parts[2] === "audit") return { name: "audit", id };
    return { name: "case", id };
  }
  return { name: "queue" };
}

export function href(route: Route): string {
  if (route.name === "queue") return "#/";
  const base = `#/cases/${encodeURIComponent(route.id)}`;
  return route.name === "case" ? base : `${base}/${route.name}`;
}

export function navigate(route: Route): void {
  window.location.hash = href(route);
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => {
      setRoute(parseHash(window.location.hash));
      window.scrollTo?.(0, 0);
      // Tell keyboard and screen reader users the page changed.
      document.getElementById("main")?.focus({ preventScroll: true });
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
