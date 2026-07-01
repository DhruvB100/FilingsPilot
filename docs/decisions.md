# Decision records

## 001 - pgvector instead of Azure AI Search
**Context:** need hybrid (keyword + vector) search over ~14k chunks.
**Decision:** Postgres + pgvector, keyword side with tsvector + ts_rank_cd, merged with RRF in python.
**Why:** the financial data has to live in Postgres anyway for text-to-SQL, so one database instead of two.
AI Search free tier is capped at 50MB / 3 indexes and the next tier is ~$75/month.
**Downside:** have to write the fusion myself, no semantic ranker.

## 002 - fiscal year from the period end date
**Context:** companyfacts `fy` field = year of the filing the number came from, so comparatives get the wrong year.
**Decision:** year = year of the period end date, only ~12 month durations for flow items, latest filing wins.
**Why:** see issues log #3. Banks end Oct 31 so their fiscal 2025 ends 2025-10-31, which still works.

## 003 - the agent writes the SQL itself
**Context:** text-to-SQL could be a separate LLM call inside the tool.
**Decision:** `query_financials` takes SQL directly, the schema is in the tool description.
**Why:** one less LLM call per question (cheaper + faster), and the agent already knows what it's looking for.
The guardrails are the same either way (sql_guard + read only user).

## 004 - 512 dimension embeddings
**Decision:** text-embedding-3-small with `dimensions=512` instead of 1536.
**Why:** 3x smaller table and index, which matters for the CI database fixture and the small Postgres SKU.
Hybrid search makes up for most of the quality difference. Embedding the whole corpus cost about $0.07.

## 005 - CI evals on a 10 question subset with a database fixture
**Context:** the full eval is ~$0.20 per run, and CI needs a database with the chunks in it.
**Decision:** PRs run the 10 `ci: true` questions + the red team tests against a Postgres service container
restored from a small dump (only the filings the CI questions need). Only runs when backend/evals/sql change.
**Why:** keeps every PR at a few cents and doesn't need the Azure database to be running.
Full 50 question runs are done by hand before merging bigger changes.

## 006 - free / serverless tiers everywhere, destroy after demo
**Decision:** Cosmos DB serverless, Container Apps min replicas 0, Functions flex consumption, the UI as a storage static website
(Static Web Apps isn't allowed in my subscription regions), App Insights with a 0.5GB/day cap, GitHub Container Registry instead of ACR. Postgres B1ms is the only
always-on cost (~$0.55/day) so the environment gets `terraform destroy`ed after the demo.

## 007 - MCP server calls the API instead of the database
**Decision:** the Node/TypeScript MCP server is a thin wrapper over `/tools/*` on the FastAPI app.
**Why:** the SQL guard and the read only db user stay in one place (python), the MCP server has no secrets.

## 008 - Gemini only for the comparison
**Decision:** Gemini on Vertex AI (Agent Platform API) is behind the same `get_llm()` switch but only used for one
manual eval run, never in CI or dev. The judge is always the Azure model so both get graded the same way.
**Why:** no free GCP credits on my account.
