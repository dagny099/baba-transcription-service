"""Job history tab — reads recent jobs from SQLite."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from transcript_workbench.config import AppConfig
from transcript_workbench.db.connection import initialize_database
from transcript_workbench.db.repository import Repository
from transcript_workbench.providers.pricing import format_cost_usd


def render_history_tab(config: AppConfig) -> None:
    st.subheader("Recent jobs")
    initialize_database(config.db_path)
    repo = Repository(config.db_path)
    rows = repo.list_recent_jobs(limit=25)
    if not rows:
        st.info("No transcription jobs yet. Run one above to populate history.")
        return

    enriched = []
    for r in rows:
        run = repo.get_latest_provider_run(r["job_id"]) or {}
        cost = run.get("cost_estimate_usd")
        enriched.append(
            {
                "created_at": r.get("created_at"),
                "status": r.get("status"),
                "provider": r.get("provider"),
                "model": r.get("model"),
                "filename": r.get("original_filename"),
                "duration_s": r.get("duration_seconds"),
                "estimated_cost": format_cost_usd(cost) if cost is not None else "—",
                "job_id": r.get("job_id"),
            }
        )
    df = pd.DataFrame(enriched)
    st.dataframe(df, width="stretch", hide_index=True)
