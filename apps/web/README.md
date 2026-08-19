# JobRadar web dashboard

Local React + TypeScript UI for JobRadar. It talks only to the FastAPI envelope API (`{ data, error, meta }`). No scoring, gating, or notification logic lives here.

## Requirements

- Node.js 20+
- npm
- JobRadar API on `http://127.0.0.1:8000`

## Setup

```bash
cd apps/web
cp .env.example .env
npm install
```

Default `VITE_API_BASE_URL=/api`. Vite rewrites `/api/...` to FastAPI on port 8000, so SPA routes like `/alerts` never collide with API paths.

## Run

```bash
# terminal 1 — API (repo root)
uv run uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000

# terminal 2 — web
cd apps/web
npm run dev
```

Open http://127.0.0.1:5173. The shell header shows **Connected** when `GET /api/career-sources` succeeds. `/sources` manages career sources and discovery. `/opportunities` searches openings and shows recommendation lists. `/tracker` bookmarks opportunities and moves them through application states. `/drafts` generates draft artifacts and records outbound delivery after an explicit approval. `/alerts` configures and runs immediate alerts and morning digests. `/notifications` delivers a completed run to the in-app inbox and the recording email adapter.

Outbound delivery and email notifications are recorded locally and never send anything externally. Draft approval is not persisted by the API, so it is lost on reload and consumed by the first delivery.

## Scripts

| Command | Purpose |
|---------|---------|
| `npm run dev` | Vite dev server on port 5173 |
| `npm run build` | Typecheck + production build |
| `npm test` | Vitest (API client + Sources, Opportunities, Tracker, Drafts, Alerts, Notifications pages) |
| `npm run preview` | Serve the production build |

## Story map

| Route | Status |
|-------|--------|
| `/sources` | Live — story 6.2 |
| `/opportunities` | Live — story 6.3 |
| `/tracker`, `/drafts` | Live — story 6.4 |
| `/alerts`, `/notifications` | Live — story 6.5 |
