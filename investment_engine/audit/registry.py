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
)
