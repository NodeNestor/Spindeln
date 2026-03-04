# CLAUDE.md — Spindeln Development Guide

## What This Is

Spindeln is a Swedish Person Intelligence Platform. It runs multi-agent OSINT investigations: searches public records, social media, breach databases, and the web, then extracts, validates, and synthesizes person data.

## Stack

- **Backend**: Python 3.12, FastAPI, Pydantic, httpx (no ORM — in-memory sessions)
- **Frontend**: React 18, Vite, TypeScript, Tailwind CSS, Zustand, Recharts, react-force-graph-2d
- **Infrastructure**: Docker Compose — SearXNG, Crawl4AI, vLLM, HiveMindDB, Tor proxy
- **LLM**: Two-model system — bulk (Qwen 3.5 0.8B via vLLM) + synthesis (any OpenAI-compatible API)

## Project Layout

```
orchestrator/src/           — All backend code
  main.py                   — FastAPI app, all API endpoints, WebSocket, graph/timeline builders
  investigate.py            — Investigation pipeline orchestrator (11 phases)
  models.py                 — All Pydantic models (Person, SourcedFact, enums, etc.)
  config.py                 — Pydantic Settings + runtime config layer (persisted to /app/data/config.json)
  fact_validator.py          — Synthesis model fact validation + contradiction detection
  scraper/extractors.py     — LLM prompts, JSON extraction, JSON repair, deduplication
  scraper/searxng_client.py — SearXNG search client
  scraper/crawl4ai_client.py — Crawl4AI scraper client
  agents/base.py            — BaseAgent ABC with search/scrape/extract helpers
  agents/registry.py        — Agent registration + category discovery
  agents/public_records/    — 9 Swedish registry agents (ratsit, hitta, etc.)
  agents/social_media/      — 9 platform agents (facebook, instagram, etc.)
  agents/breach/            — 6 breach/exposure agents (hibp, intelx, etc.)
  agents/web/               — 3 web/news agents
  agents/analysis/          — Graph builder, timeline builder, profile synthesis
  storage/client.py         — HiveMindDB async client
  storage/schemas.py        — Entity/relation type constants
frontend/src/               — React frontend
  pages/                    — Dashboard, Investigate, Profile, Search, Settings, Graph, Timeline
  components/               — CategoryRadar, ConnectionGraph, FactCard, SwarmFeed, TimelineView
  stores/                   — Zustand stores (investigation.ts, profile.ts)
```

## Key Patterns

### Agent Pattern
All agents inherit `BaseAgent` and implement `run(person: Person) -> Person`. Helpers: `search()`, `scrape()`, `extract_page_facts()`, `extract_json()`, `store_person_fact()`. Registration via `@register_agent("name")` decorator.

### Investigation Pipeline
`investigate.py:run_investigation()` runs phases sequentially: seed → public_records → social_media → web_news → breach_check → fact_validation → discovery_loop → graph → dedup → synthesis → embeddings → loom. Each phase uses `_run_parallel_agents()` with bounded concurrency.

### Two-Model System
- `extract_json()` → bulk model (fast, cheap, local GPU)
- `extract_json_synthesis()` → synthesis model (smart, external API)
- Agents set `use_synthesis_model = True` to switch
- Both use OpenAI-compatible `/chat/completions` endpoint

### JSON Repair
Small models produce truncated JSON. `_repair_json()` in extractors.py handles: bracket stack tracking, trailing comma removal, truncated string closure, progressive trimming.

### Identity Disambiguation
`_build_identity_anchors()` in base.py collects DOB/address/personnummer. These are injected into extraction prompts so the model can distinguish between multiple people with the same name. `fact_validator.py` uses the synthesis model to rate facts as CONFIRMED/WRONG_PERSON/CONTRADICTS.

### Discovery Loop
After fact validation, `_run_discovery_loop()` in investigate.py collects emails/handles/companies from sourced_facts and social profiles, searches for them, extracts new facts, repeats until convergence or `max_discovery_iterations`.

## Development

### Running Locally
```bash
docker compose up -d              # Start all services (no GPU)
docker compose --profile gpu up -d  # Start with local vLLM on GPU
```

Source code is volume-mounted: `./orchestrator/src:/app/src`. Restart the container to pick up changes:
```bash
docker restart spindeln-orchestrator
```

### Frontend Dev
```bash
cd frontend
npm install
npm run dev    # Vite dev server on :3000, proxies API to :8083
```

### Adding a New Agent
1. Create `orchestrator/src/agents/<category>/my_agent.py`
2. Inherit `BaseAgent`, implement `name`, `source_type`, `run()`
3. Decorate with `@register_agent("my_agent")`
4. Add source type to `SourceType` enum in `models.py` if needed
5. The agent is auto-discovered by `registry.py` via category folder

### Testing
```bash
# Start investigation via API
curl -X POST http://localhost:8083/api/investigate \
  -H "Content-Type: application/json" \
  -d '{"query": "Test Person", "location": "Stockholm"}'

# Check health
curl http://localhost:8083/api/health

# View config
curl http://localhost:8083/api/config
```

## Conventions

- Swedish field names in backend models (namn, personnummer, fodelsedatum, adress, etc.)
- English field names in frontend-facing API responses (name, date_of_birth, address)
- `_transform_person_for_frontend()` in main.py handles the mapping
- All dates are `datetime.date` or `datetime.datetime` objects
- Confidence scores: 0.0-1.0. Quality scores: 0-10.
- Sessions are in-memory — lost on container restart
- Config persists to `/app/data/config.json` inside the orchestrator container

## Important Notes

- SearXNG sometimes returns 0 results for Swedish names — this is an upstream issue
- Qwen 0.8B produces truncated JSON on long pages — `_repair_json()` handles most cases
- The `--profile gpu` flag in docker-compose enables the vLLM container
- WebSocket at `/ws` broadcasts `ProgressEvent` for live frontend updates
- HiveMindDB `entities/find` may 404 — graph is built from person data in main.py instead
