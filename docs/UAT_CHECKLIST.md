# TranscriptWorkbench UAT Checklist (MVP)

A short, opinionated test plan for the first round of user acceptance testing.

## 0 · Setup

- [ ] `python -m venv .venv && source .venv/bin/activate`
- [ ] `pip install -r requirements.txt`
- [ ] `cp .env.example .env`
- [ ] Add a real `OPENAI_API_KEY` to `.env`
- [ ] (Optional but recommended) `brew install ffmpeg` so audio metadata appears
- [ ] `streamlit run app.py`

The app should open in a browser tab.

## 1 · Smoke checks (no API call)

- [ ] App loads without an exception screen
- [ ] Sidebar shows "OPENAI_API_KEY loaded from environment" when `.env` is set
- [ ] Sidebar shows ffmpeg/ffprobe status (success or warning)
- [ ] Capability panel renders for default provider (OpenAI) + default model
- [ ] Selecting AWS or faster-whisper shows a "coming soon" warning
- [ ] Switching provider updates the model dropdown to the right list

## 2 · Feature negotiation behavior

- [ ] Check **Identify speakers** while OpenAI mini is selected → warning appears explaining diarization is unsupported
- [ ] Check **Include confidence info** while OpenAI mini is selected → warning explains confidence is a proxy
- [ ] Switch to model `whisper-1` → timestamps shows `supported`
- [ ] Uncheck all features → all effective values become `not_requested`

## 3 · Real OpenAI transcription (short clip < 1 minute recommended first)

- [ ] Upload a short `.mp3` or `.m4a` (under ~10MB)
- [ ] File metrics row shows filename, size, MIME
- [ ] Click **Run transcription**
- [ ] Status panel shows "Running transcription..." then "Transcription complete"

After completion:

- [ ] **Transcript** tab shows readable text
- [ ] **Segments** tab: with `whisper-1`, segments appear with timestamps; with `gpt-4o-mini-transcribe`, a single segment is acceptable
- [ ] **Confidence** tab: with `whisper-1` shows token logprob proxy stats; with `gpt-4o-mini-transcribe` shows "no confidence info"
- [ ] **Metadata** tab shows job id, provider, model, requested/effective features, audio metadata if ffprobe was available
- [ ] **Raw / Debug** tab shows the saved provider response JSON
- [ ] **Downloads** tab offers TXT, Markdown, JSON download buttons
- [ ] Each download button produces a valid file when clicked
- [ ] **History** tab shows the just-completed job at the top

## 4 · Persistence

- [ ] Stop Streamlit (Ctrl+C) and restart it
- [ ] **History** tab still shows the previous job
- [ ] On disk: `data/jobs/<job_id>/` contains `input/original.<ext>`, `raw/provider_response.json`, and `exports/transcript.{txt,md,json}`
- [ ] On disk: `data/transcript_workbench.sqlite` exists

## 5 · Error paths

- [ ] Remove the OpenAI key from `.env` and `OPENAI_API_KEY` from the env (or set sidebar override empty), restart, run transcription → clear error message about missing key
- [ ] Paste an invalid key into the sidebar override → API error is displayed in the UI without crashing the app
- [ ] Select **AWS Transcribe** and run → clean "not yet implemented" error rather than a stack trace
- [ ] Select **Local faster-whisper** and run → clean "not yet implemented" error

## 6 · Data quality / sanity

- [ ] Generated `transcript.txt` matches the transcript shown in the UI
- [ ] Generated `transcript.json` parses with `python -m json.tool`
- [ ] `transcript.md` includes provider, model, original filename, and any warnings
- [ ] Raw response file is exactly what the provider returned (no app post-processing)

## 7 · Cost tracking

- [ ] After uploading a file (with ffmpeg installed), the **Capability panel** shows a "Pre-flight estimate" with duration, estimated cost, and rate
- [ ] Switching between OpenAI models (`gpt-4o-mini-transcribe` vs `gpt-4o-transcribe`) updates the estimated cost (mini should be ~half of standard)
- [ ] Selecting **AWS Transcribe** shows a per-second rate in the pre-flight estimate
- [ ] Selecting **Local faster-whisper** shows "free" in the pre-flight estimate
- [ ] Without ffmpeg installed, pre-flight shows a graceful "install ffprobe" caption instead of erroring
- [ ] After a real OpenAI run, the **Metadata** tab shows three top metrics: Duration, Estimated cost, Rate
- [ ] The cost line reads as an **estimate** (caption says "Cost is an estimate from duration × published rate")
- [ ] **History** tab shows an `estimated_cost` column populated for completed jobs
- [ ] A failed run records no cost (the row appears in History with status `failed` and `estimated_cost = —`)
- [ ] An existing pre-cost-tracking SQLite DB still loads (migration adds new columns silently); old jobs show `—` in the cost column

## 8 · Tests

- [ ] `python -m pytest tests/ -v` passes (46 tests)

## Notes / open issues

Use this space to log anything observed during UAT that should be addressed
before AWS Transcribe work begins.
