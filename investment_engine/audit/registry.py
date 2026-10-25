"""The modules whose registered types audit events may hold (docs/tasks/M3-04.md rule 3).

AuditStore imports each one, so a fresh process can decode every stored event
without the writer's imports. Each later M3 task that adds an auditable type
adds its module here, and nothing else.
"""

MODULES: tuple[str, ...] = (
    "investment_engine.policy.accounts",  # M3-05
    "investment_engine.policy.rules",  # M3-06
    "investment_engine.risk.limits",  # M3-06
    "investment_engine.portfolio.reference",  # M3-07
    "investment_engine.portfolio.snapshot",  # M3-07
    "investment_engine.oms.intents",  # M3-08 types, audited from M3-09
    "investment_engine.policy.decisions",  # M3-08
    "investment_engine.risk.decisions",  # M3-08
    "investment_engine.oms.intent_store",  # M3-09
    "investment_engine.lineage.intent_lineage",  # M3-12
    "investment_engine.oms.pipeline",  # M3-12
    "investment_engine.oms.order_states",  # M4-00
    "investment_engine.oms.orders",  # M4-00
    "investment_engine.events.envelope",  # M4-00
    "investment_engine.killswitch.flag",  # M4-04
    "investment_engine.portfolio.fingerprint",  # M4-09: Reservation, stored inside snapshots (Codex M4 review B13)
    "investment_engine.portfolio.provisional",  # M4-09: Adjustment, stored inside snapshots (B13)
    "investment_engine.evaluation.promotion",  # M4-10
    "investment_engine.ledger.contracts",  # M5-00
    "investment_engine.reconciliation.contracts",  # M5-00: neutral evidence only
    "investment_engine.reconciliation.incidents",  # M5-09: incident/readiness payloads
    "investment_engine.research.contracts",  # M6-01: research jobs, records, contexts and budget
)
