# Target-State Gap Analysis and Delivery Plan (UI Mockup Alignment)

## Scope
This document maps the **current TranscriptWorkbench implementation** to the provided mobile UI mockup target state and defines a practical implementation path.

## Current-state snapshot (what exists now)

- App shell is a **single Streamlit page** with sidebar controls and a top-to-bottom workflow (upload → config → run → results).  
- Upload supports one local file and shows filename/size/MIME only.  
- Configuration includes provider/model selection, feature checkboxes, and capability panel.  
- Run is a single primary button; results are tabbed (Transcript, Segments, Confidence, Metadata, Raw/Debug, Downloads, History).  
- History is a table-based list from SQLite; no dedicated “recent uploads card” UX.

## Target-state decomposition from the mockup

### Primary navigation
1. Bottom nav with tabs: **New Job, Results, History, Settings**.
2. New Job has top segmented controls: **New Job / Results / History** (redundant with bottom nav, but in mockup).

### New Job screen
1. Header branding + “Local-first MVP” badge.
2. Input Source section:
   - Upload File, Audio URL, Podcast RSS selectors.
   - Large drag/tap upload zone with explicit accepted formats + max size.
   - Recent uploads mini-list with quick access.
3. Configuration section:
   - Provider/model dropdowns.
   - Toggle switches for Timestamps, Confidence (proxy), Speaker labels/diarization.
   - Capability feedback card with per-capability status text.
   - Provider status list (OpenAI/Whisper/AWS readiness indicators).
4. Sticky/anchored Run button + estimated runtime text.

### Result detail screen
1. Job header with timestamp and overflow actions.
2. Tabs: **Transcript / Details / Downloads**.
3. Summary strip: provider, model, duration.
4. Search + filter controls over transcript.
5. Transcript list with visible timestamps and speaker chips.
6. Inline media player with scrubber + speed control.
7. Quick download tiles (TXT/MD/JSON/Raw).

## Gap analysis (current vs target)

## 1) Navigation & layout
- **Gap:** Current app is single-page Streamlit with sidebar; target is mobile app style with bottom navigation and screen-specific headers.
- **Implication:** Requires state-driven page router and a mobile-first layout system (still possible in Streamlit, but less native than React Native/Flutter/web SPA).

## 2) Input sources
- **Gap:** Current supports only file upload. No Audio URL or Podcast RSS ingest path.
- **Implication:** Need new ingestion services, metadata fetchers, validation, and download/transcode pipeline before transcription starts.

## 3) Recent uploads UX
- **Gap:** Current has history table, not recent upload cards in New Job flow.
- **Implication:** Add indexed file catalog + lightweight card UI + rehydrate configuration from selected prior item.

## 4) Feature/capability presentation
- **Gap:** Capability exists (good), but visual treatment differs (expander metrics vs persistent card with “Supported/Proxy/Unavailable” rows).
- **Implication:** Mostly UI refactor; capability model can be reused.

## 5) Provider status block
- **Gap:** Target implies multi-provider readiness indicators. Current registry marks non-OpenAI as “coming soon,” but readiness panel is not present in main flow.
- **Implication:** Add health-check hooks per provider (credentials, binaries, permissions, connectivity).

## 6) Result transcript experience
- **Gap:** Current transcript tab is readable but lacks search/filter controls, speaker chip styling, and detail summary strip in the target format.
- **Implication:** Build transcript index/filter UI and richer row components.

## 7) Audio playback integration
- **Gap:** Target includes integrated player with timeline and speed control. Current results do not expose this integrated player UX.
- **Implication:** Need persistent reference to audio artifact and synchronized time-based transcript highlighting.

## 8) Download UX
- **Gap:** Current uses button list; target uses quick tiles with visual hierarchy.
- **Implication:** UI redesign only; export back-end already exists.

## 9) Settings screen
- **Gap:** Target bottom nav includes Settings; current app places key controls in sidebar.
- **Implication:** Move environment/runtime options into a dedicated settings view and keep sidebar optional/debug-only.

## Detailed implementation plan (how to get there)

## Phase 0 — Alignment decisions (1-2 days)
1. Confirm platform choice:
   - **Option A:** Keep Streamlit, emulate mobile UI patterns.
   - **Option B:** Build dedicated frontend (React/Next/React Native) with existing Python service layer behind API.
2. Define “must match pixel-perfect” vs “functionally equivalent” acceptance criteria.
3. Freeze MVP+ scope for this redesign (exclude uncertain features from first cut).

## Phase 1 — Information architecture & state model (2-4 days)
1. Introduce explicit app views: `new_job`, `results_list`, `history`, `settings`, `job_detail`.
2. Add centralized session state object for:
   - selected job
   - active transcript tab
   - search query/filter
   - active audio position/speed
3. Add reusable UI primitives for cards, chips, status pills, and segmented controls.

## Phase 2 — New Job screen parity (4-7 days)
1. Build branded header and badges.
2. Replace linear uploader with Input Source selector tabs:
   - Upload File (existing path)
   - Audio URL (new)
   - Podcast RSS (new)
3. Add “Recent uploads” strip using recent job/source records.
4. Refactor configuration card:
   - provider/model selectors
   - toggle-style options
   - always-visible capability panel
5. Add provider status card with health indicators and actionable warning text.
6. Move run CTA to sticky footer container with runtime estimate.

## Phase 3 — Ingestion expansion (Audio URL + RSS) (5-10 days)
1. `services/ingest_url.py`: resolve URL, validate content type/size, safe download to staging.
2. `services/ingest_rss.py`: parse feed, list episodes, resolve enclosure URL.
3. Reuse existing file/audio preprocessing and job creation pipeline after ingestion normalization.
4. Add SSRF and file abuse protections:
   - deny private-network targets
   - enforce size/time limits
   - strict MIME/extension checks

## Phase 4 — Result detail screen parity (5-8 days)
1. Job header with timestamp + actions.
2. Tabs: Transcript / Details / Downloads.
3. Summary strip (provider/model/duration).
4. Transcript search/filter controls.
5. Speaker/time row component with chips and formatting.
6. Embedded player with:
   - seek
   - speed
   - current time
   - optional click-to-seek from transcript rows.
7. Quick downloads tiles and destination message.

## Phase 5 — Settings & operational readiness (2-4 days)
1. Dedicated settings view:
   - API key override
   - defaults (provider/model/features)
   - runtime diagnostics (ffmpeg, db path, data dir)
2. Preserve secure handling: no persistence of sensitive session overrides by default.

## Phase 6 — QA, UAT, and rollout (3-6 days)
1. Expand unit tests for new ingestion and transcript search logic.
2. Add integration tests for new navigation and job-detail state transitions.
3. Update docs with new UX paths + screenshots.
4. Run UAT checklist against mockup-aligned scenarios.

## Inconsistencies / ambiguity in the mockup to resolve early

1. **Dual navigation pattern:** top segmented tabs and bottom nav both expose New Job/Results/History.
   - Risk of duplicated state and confusing active-tab behavior.
2. **“Results” meaning ambiguity:** could mean list of jobs or active selected job detail.
3. **Speaker labels vs provider support:** mockup shows HOST/GUEST chips, but OpenAI path may not provide true diarization today.
4. **Confidence toggle wording (“proxy”)** may confuse users unless tooltip explains calibration limits.
5. **Provider status “AWS blocked” semantics** unclear (missing credentials? policy? network?).
6. **Estimated runtime value** in mockup implies predictable SLA; actual runtime varies by duration/network/provider load.

## Key risks you should be aware of

## Product/UX risks
1. **Expectation mismatch on diarization/confidence** if UI implies guaranteed speaker labels/high-quality confidence.
2. **Overfitting to mockup visuals** can delay core functional gains if platform constraints are ignored.
3. **Navigation complexity** from duplicated tab systems can degrade usability.

## Technical risks
1. **Streamlit mobile UX limits:** exact native-like interactions (sticky bottom nav/player behavior) are harder than SPA/native frameworks.
2. **Audio URL/RSS ingestion attack surface:** SSRF, large-file abuse, malformed media, and timeout handling need hardening.
3. **Playback-transcript sync complexity:** robust seek/highlight behavior requires precise timing and consistent segment metadata.
4. **Provider divergence:** capability matrix can drift as providers/models change; registry must be maintained.

## Delivery risks
1. **Scope creep:** adding URL/RSS, player sync, search, and settings together is significant.
2. **Test debt:** UI-heavy refactor can regress existing stable transcription flow without strong integration coverage.
3. **Operational drift:** provider readiness panel can become inaccurate unless checks are reliable and fast.

## Recommended implementation sequence (risk-adjusted)
1. Ship **navigation + New Job parity** first (no new ingestion modes).
2. Ship **result detail parity + downloads redesign**.
3. Ship **audio URL ingestion** with strict safeguards.
4. Ship **RSS ingestion** last.
5. Then tighten UI polish and advanced sync behaviors.

This sequencing preserves value while reducing failure modes early.
