# Assisted Execution Playbook

This playbook turns the target-state UI plan into an execution system you can run with coding assistants (Codex/Claude/GPT-style agents), while keeping architecture quality and delivery safety.

## 1) Should you move away from Streamlit?

## Short answer
**Yes—if your target is the attached mobile-style UI, you should plan to move away from Streamlit for the front-end layer.**

## Why
Your target UI depends on interaction patterns that Streamlit can emulate but not own natively with long-term maintainability:
- persistent bottom navigation and mobile tab routing
- sticky player + transcript sync + row-level interactions
- richer state transitions (results list vs detail views)
- precise layout/theming for mobile fidelity

For pure MVP iteration, Streamlit remains excellent. For your target-state product UX, a dedicated front-end is the lower-risk long-term path.

## Recommended architecture decision
- Keep the **existing Python domain/services/repository layers** as core business logic.
- Introduce a **backend API boundary** (FastAPI preferred) around transcription jobs, history, artifacts, and provider status.
- Build UI in:
  - **React Native** (best if true mobile app delivery), or
  - **Next.js/React web app** (best if browser-first but mobile-like responsive UX).

Treat Streamlit as:
1) internal admin/debug console, or
2) temporary interface during migration.

---

## 2) How to implement the plan with coding assistants

## Team operating model (human + assistants)
Use a **Tech Lead + Executor agents** model:

- **You (Tech Lead):** own acceptance criteria, architecture choices, risk decisions.
- **Assistant A (Planner):** writes issue specs, decomposition, and definition-of-done.
- **Assistant B (Implementer):** writes code for one scoped ticket.
- **Assistant C (Verifier):** writes/extends tests, lint fixes, and regression checks.
- **Assistant D (Reviewer):** compares output to mockup and flags UX drift.

Never let one assistant do all four roles in one pass.

## Golden prompt template for implementation tickets
Use this structure for each ticket:

1. **Objective** (single outcome)
2. **Constraints** (files allowed, forbidden refactors, perf/security requirements)
3. **Acceptance Criteria** (bullet list, objective and testable)
4. **Output Format**
   - summary
   - changed files
   - tests added/updated
   - risks/assumptions
5. **Validation Commands** to run before handing off

This sharply reduces “smart but wrong” outputs.

## Branching + delivery loop
For each ticket:
1. Create branch `feat/<area>-<ticket-id>`.
2. Ask assistant to implement only that ticket.
3. Run local checks (lint/type/test).
4. Run UX check against mockup acceptance list.
5. Merge only when DoD and checklist pass.

---

## 3) Ticket sequence (assistant-friendly)

## Epic A — Platform split and API boundary
1. Create `backend/api` service with FastAPI skeleton.
2. Add endpoints:
   - `POST /jobs`
   - `GET /jobs`
   - `GET /jobs/{id}`
   - `GET /jobs/{id}/artifacts`
   - `GET /providers/status`
3. Reuse existing services/repository modules; avoid business-logic duplication.
4. Add OpenAPI examples for each endpoint.

## Epic B — Front-end shell
1. Bootstrap app shell (Next.js or RN).
2. Implement bottom nav: New Job, Results, History, Settings.
3. Add routing state store (Zustand/Redux Toolkit or equivalent).
4. Add design tokens (colors/spacing/type scale) from mockup.

## Epic C — New Job parity
1. Header + badge.
2. Input source tabs: Upload File, Audio URL, Podcast RSS.
3. Upload dropzone + constraints text.
4. Recent uploads cards.
5. Provider/model controls, feature toggles.
6. Capability feedback card + provider status card.
7. Sticky “Run Transcription” CTA + estimated runtime.

## Epic D — Result detail parity
1. Job header + overflow actions.
2. Tabs: Transcript, Details, Downloads.
3. Summary strip (provider/model/duration).
4. Search/filter controls.
5. Speaker chips + timestamp rows.
6. Audio player + speed + transcript click-to-seek.
7. Quick download tiles.

## Epic E — Ingestion and safety
1. URL ingestion pipeline with SSRF defenses.
2. RSS ingestion + episode selection.
3. Size/time/MIME guards.
4. Error taxonomy for user-safe messages.

## Epic F — QA hardening
1. Unit + integration tests.
2. Golden snapshot/UI tests for key screens.
3. UAT runbook execution.

---

## 4) Detailed checklists

## A. Architecture checklist
- [ ] Business logic remains in shared Python service modules.
- [ ] No provider-specific logic in front-end.
- [ ] API schemas versioned and documented.
- [ ] Capability negotiation exposed by API, not recreated in UI.
- [ ] Artifact paths never exposed as unsafe filesystem primitives.

## B. Security checklist (URL/RSS ingestion)
- [ ] Block localhost/private CIDRs to prevent SSRF.
- [ ] Enforce max download size and timeout.
- [ ] Validate MIME + extension + magic bytes where possible.
- [ ] Sanitize filenames and reject path traversal.
- [ ] Log request IDs for traceability.

## C. UX parity checklist (mockup)
- [ ] Bottom nav with 4 items present and persistent.
- [ ] New Job has source selector tabs.
- [ ] Recent uploads list appears on New Job.
- [ ] Capability card always visible near config toggles.
- [ ] Provider status list with clear states.
- [ ] Results detail has Transcript/Details/Downloads tabs.
- [ ] Transcript rows show timestamps and speaker chips when available.
- [ ] Search/filter controls function on transcript rows.
- [ ] Embedded player supports seek + speed.
- [ ] Quick download tiles for TXT/MD/JSON/Raw.

## D. Data correctness checklist
- [ ] Job status transitions are valid (`created -> preprocessing -> running -> completed|failed`).
- [ ] Effective features match negotiated backend output.
- [ ] Duration/cost estimation displayed with caveat text.
- [ ] Missing capabilities render explicit “unsupported/proxy” messaging.

## E. Testing checklist
- [ ] Backend unit tests for ingestion validators.
- [ ] Backend integration tests for job lifecycle endpoints.
- [ ] Front-end component tests for nav, toggles, cards.
- [ ] Front-end integration test for New Job -> Run -> Result detail flow.
- [ ] Regression tests for downloads and artifact retrieval.
- [ ] Smoke test against a real short audio sample.

## F. Release readiness checklist
- [ ] UAT checklist signed for all core flows.
- [ ] Known limitations documented.
- [ ] Observability baseline added (structured logs, error rates).
- [ ] Rollback plan prepared.
- [ ] Streamlit fallback path kept until two stable releases.

---

## 5) High-quality assistant prompts you can reuse

## Prompt: ticket implementation
"Implement only Ticket C-4 (Recent uploads cards). Do not modify backend services. Keep changes inside frontend/components/uploads and frontend/screens/new-job. Add component tests. Acceptance criteria: cards display filename/date/duration; click hydrates selected source; empty state shown. Run tests and report commands/output."

## Prompt: strict reviewer
"Review this diff against UX checklist section C. Report only: (1) checklist items passed, (2) checklist items missing, (3) concrete code-level fixes by file path. Do not propose unrelated enhancements."

## Prompt: migration guard
"Identify any duplicated business logic between frontend and backend in this branch. Provide exact file paths and a patch plan to centralize logic in backend services."

---

## 6) Practical migration strategy (minimize disruption)

1. Keep Streamlit running while API + new UI are built.
2. Migrate feature-by-feature behind flags.
3. Route a subset of users/jobs to new UI first.
4. Keep SQLite schema stable; avoid schema churn mid-migration.
5. Decommission Streamlit only after metrics and UAT pass.

This gives you velocity without risking current functionality.
