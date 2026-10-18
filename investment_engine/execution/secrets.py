"""The Execution Worker's secrets file (Law 2; ADR-002 section 5; D32; docs/tasks/M4-03.md rule 3).

`<data dir>/secrets/execution_worker.env`, as KEY=VALUE lines. Only the
worker's entry point calls `load_worker_secrets`; no other process reads the
file, which a layering rule and a canary test enforce. A missing file is an
empty set of secrets (the simulator needs none). Values are never printed,
logged or put in an error message; an unparsable line is reported by its line
number only.
"""

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType


class SecretsFileError(ValueError):
    """The secrets file can't be read; the message never contains a value."""


def load_worker_secrets(path: Path) -> Mapping[str, str]:
    if not path.exists():
        return MappingProxyType({})
    values: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        key, sep, value = text.partition("=")
        if not sep or not key.strip():
            raise SecretsFileError(f"{path.name} line {number} is not KEY=VALUE")
        values[key.strip()] = value.strip()
    return MappingProxyType(values)


__all__ = ["SecretsFileError", "load_worker_secrets"]
