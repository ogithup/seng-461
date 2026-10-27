"""Glue between the modules (owner: Oğuz).

`site_agent` and `reference_generator` are working stand-ins so the application generates
real sites end to end before Bejan's model-backed agent and Rana's generator land. Each is
replaced by setting AGENT_IMPL / GENERATOR_IMPL to "package.module:Name"; the ports they
must satisfy are in backend/api/services/ports.py and docs/sprint3-contracts.md.
"""
import importlib
from typing import Any


def load_object(spec: str) -> Any:
    """Import "package.module:Name" and return the attribute."""
    module_name, _, attribute = spec.partition(":")
    if not module_name or not attribute:
        raise ValueError("expected 'package.module:Name', got %r" % spec)
    return getattr(importlib.import_module(module_name), attribute)
