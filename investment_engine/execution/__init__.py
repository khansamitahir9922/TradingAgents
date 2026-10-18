"""The Execution Worker: the only process with a path to a broker (Laws 1, 2; architecture Part E; ADR-002;
docs/tasks/M4-03.md onwards).

Nothing outside this package imports it, except the offline research harness
(`investment_engine.simulation`, M4-13), which may build only the worker, the
factory, the broker port and the simulated broker. Only this package's entry
point reads the worker's secrets file. Both rules are enforced by
tests/engine/test_layering.py; until M7's separate OS users they are a
development convention, stated as such (ADR-002 section 5).
"""
