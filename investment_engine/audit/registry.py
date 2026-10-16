"""The modules whose registered types audit events may hold (docs/tasks/M3-04.md rule 3).

AuditStore imports each one, so a fresh process can decode every stored event
without the writer's imports. Each later M3 task that adds an auditable type
adds its module here, and nothing else.
"""

MODULES: tuple[str, ...] = ()
