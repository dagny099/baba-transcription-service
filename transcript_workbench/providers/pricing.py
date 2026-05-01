"""Provider pricing rules and cost estimation.

Cost tracking is intentionally an *estimate* — providers like OpenAI do not
return a billed amount in the API response, so we derive cost from
`duration_seconds * rate`. Every job records both the final estimate AND the
rate that produced it, so historical job records remain correct even after
prices change.

Prices are isolated in this module (Fork A, option 2) so updating them does
not touch the registry or the orchestrator. If we later need historical
accuracy across price changes, a SQLite-backed effective-dated table can
replace this dict without changing any callers.

Verify and update these rates against the current OpenAI pricing page; they
are not constants the SDK exposes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PricingUnit = Literal["per_minute", "per_second", "free", "unknown"]


@dataclass(frozen=True)
class PricingRule:
    """How a provider/model is priced."""

    unit: PricingUnit
    usd_per_unit: float
    notes: str = ""


@dataclass(frozen=True)
class CostEstimate:
    """A cost estimate plus the rate that produced it (for auditability)."""

    usd: float
    rate_usd: float
    unit: PricingUnit


# Rates verified against publicly listed prices at time of writing. Treat as a
# starting point; users should re-confirm against current provider docs.
PRICING: dict[str, dict[str, PricingRule]] = {
    "openai": {
        "gpt-4o-mini-transcribe": PricingRule(
            unit="per_minute",
            usd_per_unit=0.003,
            notes="Per minute of input audio.",
        ),
        "gpt-4o-transcribe": PricingRule(
            unit="per_minute",
            usd_per_unit=0.006,
            notes="Per minute of input audio.",
        ),
        "whisper-1": PricingRule(
            unit="per_minute",
            usd_per_unit=0.006,
            notes="Per minute of input audio.",
        ),
    },
    "aws": {
        # Tiered in reality; this is a single "standard" tier placeholder so
        # the AWS milestone has a number to work with from day one.
        "standard": PricingRule(
            unit="per_second",
            usd_per_unit=0.024 / 60.0,
            notes="Approximate AWS Transcribe standard tier (~$0.024/min).",
        ),
    },
    "faster_whisper": {
        "small": PricingRule(unit="free", usd_per_unit=0.0, notes="Local model."),
        "medium": PricingRule(unit="free", usd_per_unit=0.0, notes="Local model."),
    },
}


def get_pricing_rule(provider: str, model: str) -> PricingRule | None:
    return PRICING.get(provider, {}).get(model)


def estimate_cost(
    provider: str,
    model: str,
    duration_seconds: float | None,
) -> CostEstimate | None:
    """Return a cost estimate or None if it can't be computed.

    Returns None (not zero) when:
    - duration is unknown (no ffprobe, no provider duration), or
    - the provider/model has no pricing rule.

    Free models return CostEstimate(usd=0.0, rate=0.0, unit="free") so the UI
    can render "free" instead of a misleading "—".
    """
    if duration_seconds is None or duration_seconds < 0:
        return None
    rule = get_pricing_rule(provider, model)
    if rule is None:
        return None
    if rule.unit == "free":
        return CostEstimate(usd=0.0, rate_usd=0.0, unit="free")
    if rule.unit == "per_minute":
        usd = (duration_seconds / 60.0) * rule.usd_per_unit
        return CostEstimate(usd=usd, rate_usd=rule.usd_per_unit, unit="per_minute")
    if rule.unit == "per_second":
        usd = duration_seconds * rule.usd_per_unit
        return CostEstimate(usd=usd, rate_usd=rule.usd_per_unit, unit="per_second")
    return None


def format_cost_usd(usd: float | None) -> str:
    """Display helper. Distinguishes 'free', '<$0.01', '$0.018', '—'."""
    if usd is None:
        return "—"
    if usd <= 0:
        return "free"
    if usd < 0.01:
        return "<$0.01"
    if usd < 1.0:
        return f"${usd:.3f}"
    return f"${usd:.2f}"
