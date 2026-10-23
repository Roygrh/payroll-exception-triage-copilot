# ADR-020: Frontend styling and test tooling

Status: Accepted
Date: 2026-10-20

## Context

ADR-013 fixes React with TypeScript built with Vite for the approver UI, served as static files in compose and proxied to the API in development. It does not choose a styling approach, a test runner, a linter or fonts, and AGENTS.md requires an ADR before any new dependency. Iteration 4 builds the UI from an approved design (four screens: queue, case detail, message confirmation, executed and audit trail) with fixed colors, a mono font for numbers, ids, times and citation keys, keyboard access, touch targets of at least 44 px and a layout that works at phone width. The author's machine has Node 24.11.0 and npm 11.6.2.

## Decision

- **Styling:** Tailwind CSS 4 through its Vite plugin. The design's colors, radius and fonts are tokens in one `@theme` block (`frontend/src/index.css`); components use utility classes. No component library.
- **Tests:** Vitest with React Testing Library, user-event and the jest-dom matchers, in a jsdom environment. Frontend tests never reach the API: `fetch` is replaced by a route table (`frontend/src/test/api-mock.ts`) whose fixtures follow the shapes the API returns with the in-memory runtime and the fake adapter.
- **Lint and types:** ESLint with typescript-eslint and the React hooks rules; `npm run build` runs `tsc --noEmit` before `vite build`.
- **Fonts:** Inter for text and JetBrains Mono for numbers, ids, times and citation keys, bundled from the Fontsource npm packages; nothing is loaded from a CDN.
- **Routing:** hash routes written in the app (`frontend/src/router.ts`), so the built files work as static files with no server rewrite and no router dependency.
- **Development:** the Vite dev server proxies `/api` to `http://127.0.0.1:8000` and strips the prefix (the API has no prefix), so the API needs no CORS change. Two commands: `uv run ptc serve` in `backend/`, `npm run dev` in `frontend/`.
- **Exact pins** (`frontend/package.json`, `save-exact` and `engine-strict` in `frontend/.npmrc`, lock file `frontend/package-lock.json`):

| Package | Version | Role |
| --- | --- | --- |
| react, react-dom | 19.3.1 | UI runtime (ADR-013) |
| @types/react, @types/react-dom | 19.3.0 | types |
| vite | 8.3.5 | build and dev server (ADR-013) |
| @vitejs/plugin-react | 6.1.2 | React support for Vite |
| typescript | 6.0.3 | type checking |
| tailwindcss, @tailwindcss/vite | 4.3.3 | styling |
| @fontsource/inter, @fontsource/jetbrains-mono | 5.3.0 | bundled fonts |
| vitest | 5.0.5 | test runner |
| jsdom | 29.1.1 | DOM for tests |
| @testing-library/react | 16.3.3 | component tests |
| @testing-library/dom | 10.4.2 | peer of the above |
| @testing-library/user-event | 14.6.8 | user interaction in tests |
| @testing-library/jest-dom | 7.0.1 | DOM matchers |
| @types/node | 24.19.2 | Node types for the Vite configuration |
| eslint | 10.13.0 | lint |
| @eslint/js, typescript-eslint, eslint-plugin-react-hooks, globals | 10.0.1, 8.72.0, 7.1.1, 17.13.0 | lint rules |

Two pins are below the newest release at the time of pinning (checked with the npm registry on 2026-10-21), for compatibility: TypeScript 6.0.3 instead of 7.0.2, because typescript-eslint 8.72.0 supports TypeScript below 6.1; jsdom 29.1.1 instead of 30.1.3, because jsdom 30 requires Node 24.15 or later and the author's machine has 24.11.0.

## Consequences

- A contributor needs Node 24.11.0 or later (`engines` in `package.json`; `engine-strict` refuses an install on an older Node).
- Upgrading TypeScript to 7 waits for typescript-eslint support; upgrading jsdom to 30 waits for Node 24.15 on the author's machine.
- The design's colors live in one place; a contrast check is a review of one block.
- The frontend test suite runs offline with no API, database or LLM; the API contract it relies on is covered by the backend API tests.
- Compose still has no frontend service; serving the built files is part of the one-command start in Iteration 6 (ADR-013).
