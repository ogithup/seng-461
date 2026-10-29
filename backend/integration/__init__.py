"""Glue between the modules (owner: Oğuz).

`reference_generator` (spec_for + a minimal generator) is used by Bejan's Orchestrator for
specs and as a test double. The application default is Orchestrator + Rana's WebsiteGenerator;
AGENT_IMPL / GENERATOR_IMPL ("package.module:Name") swap either. Ports: backend/api/services/ports.py,
docs/sprint3-contracts.md.
"""
import importlib
from typing import Any


def load_object(spec: str) -> Any:
    """Import "package.module:Name" and return the attribute."""
    module_name, _, attribute = spec.partition(":")
    if not module_name or not attribute:
        raise ValueError("expected 'package.module:Name', got %r" % spec)
    return getattr(importlib.import_module(module_name), attribute)
