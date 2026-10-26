"""The Research Worker's secrets and startup checks (D48; ADR-002 section 5).

`<data dir>/secrets/research_worker.env` (KEY=VALUE lines) is the only source of
LLM and research-data keys. Values are never printed, logged or put in an error
message. In development the process boundary is a convention; from M7 it is
enforced by OS users or containers (ADR-012).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

# Keys this worker may load into its own process environment for upstream TradingAgents.
LLM_KEYS = frozenset({"GOOGLE_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "XAI_API_KEY", "DEEPSEEK_API_KEY",
                      "OPENROUTER_API_KEY", "ALPHA_VANTAGE_API_KEY", "FRED_API_KEY", "FINNHUB_API_KEY"})
MIN_SECRET_CHARS = 8  # shorter values would make redaction erase ordinary text
# Environment names that look like broker credentials: the Research Worker must never see one.
BROKER_MARKERS = ("ALPACA", "BROKER", "IBKR", "INTERACTIVE_BROKERS", "TRADIER", "SCHWAB", "TASTYTRADE", "OANDA")


# Ambient variables that change a Google-only run (D45) outside the job's frozen settings and the budget's
# counter: TypeSafe/Jev switches itself on whatever the provider (excluded, D54), and the Google client moves to
# Vertex AI (another endpoint, project and billing) on these. Both tiers are pinned to Google (B4), so other
# providers' keys and endpoints are inert and not refused.
AMBIENT_SWITCHES = frozenset({"TYPESAFE_API_KEY", "TYPESAFE_BASE_URL", "TYPESAFE_DEFAULT_MODEL",
                              "GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION",
                              "GOOGLE_APPLICATION_CREDENTIALS"})
# TRADINGAGENTS_* overrides change upstream defaults; the adapter sets its own paths, so only these three are inert.
INERT_TRADINGAGENTS = frozenset({"TRADINGAGENTS_RESULTS_DIR", "TRADINGAGENTS_CACHE_DIR",
                                 "TRADINGAGENTS_MEMORY_LOG_PATH"})


def ambient_switches(environ: Mapping[str, str]) -> list[str]:
    """Names (never values) of set variables that would change providers, endpoints or integrations."""
    return sorted(name for name, value in environ.items() if value and (
        name.upper() in AMBIENT_SWITCHES or
        (name.upper().startswith("TRADINGAGENTS_") and name.upper() not in INERT_TRADINGAGENTS)))


class ResearchSecretsError(ValueError):
    """Startup refused; the message names keys or files, never a value."""


def load_research_secrets(path: Path) -> Mapping[str, str]:
    if not path.is_file():
        raise ResearchSecretsError(f"{path.name} is missing: the Research Worker loads its LLM key only from it (D48)")
    values: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        key, sep, value = text.partition("=")
        key = key.strip()
        if not sep or not key:
            raise ResearchSecretsError(f"{path.name} line {number} is not KEY=VALUE")
        if key not in LLM_KEYS:
            raise ResearchSecretsError(f"{path.name} line {number}: {key} is not an LLM or research-data key")
        if len(value.strip()) < MIN_SECRET_CHARS:
            raise ResearchSecretsError(f"{path.name} line {number}: the {key} value is too short to redact safely")
        values[key] = value.strip()
    if not values:
        raise ResearchSecretsError(f"{path.name} holds no key")
    return MappingProxyType(values)


def check_environment(environ: Mapping[str, str], *, execution_secrets: Path) -> None:
    """Refuse when broker credentials are visible or an LLM key arrives from the ambient environment."""
    broker = sorted(name for name in environ if any(marker in name.upper() for marker in BROKER_MARKERS))
    if broker:
        raise ResearchSecretsError("broker credential variables are visible to the Research Worker: "
                                   + ", ".join(broker))
    if execution_secrets.exists():
        raise ResearchSecretsError(f"the Execution Worker's broker secrets file {execution_secrets.name} is visible "
                                   "to the Research Worker; run them as separate users (ADR-002)")
    switches = ambient_switches(environ)
    if switches:
        raise ResearchSecretsError("variables that change upstream providers, endpoints or integrations are set ("
                                   + ", ".join(switches) + "); M6 runs Google only, with Jev excluded (D45, D54)")
    ambient = sorted(name for name in environ if name in LLM_KEYS and environ[name])
    if ambient:
        raise ResearchSecretsError("LLM keys are set in the inherited environment (" + ", ".join(ambient) +
                                   "); remove them from the user environment so only research_worker.env holds "
                                   "them (D48)")


def install(secrets: Mapping[str, str]) -> None:
    """Make the keys visible to upstream TradingAgents in this process only."""
    for key, value in secrets.items():
        os.environ[key] = value


__all__ = ["AMBIENT_SWITCHES", "BROKER_MARKERS", "LLM_KEYS", "ResearchSecretsError", "ambient_switches",
           "check_environment", "install", "load_research_secrets"]
