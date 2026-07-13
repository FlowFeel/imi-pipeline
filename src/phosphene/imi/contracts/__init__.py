"""Contracts — Behave-aligned proofs for pipeline steps.

Each contract is a collection of assertions against a live system.
Contracts run in CI, run on demand, run post-deploy.
A contract failure means the pipeline does not satisfy its spec.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations
