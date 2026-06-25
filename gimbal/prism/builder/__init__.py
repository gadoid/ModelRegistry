"""gimbal.prism.builder — back-compat shim re-exporting the split modules.

The actual code now lives in:
  - builder.drafts:    AuthDraft, ResourceDraft, StepDraft, ScenarioDraft
  - builder.resources: build_resource (ResourceDraft → ResourceUnion)
  - builder.steps:     _build_step, _step_key
  - builder.scenario:  build_scenario (top-level)
"""
from gimbal.prism.builder.drafts import (
    AuthDraft,
    ResourceDraft,
    ScenarioDraft,
    StepDraft,
)
from gimbal.prism.builder.resources import build_resource
from gimbal.prism.builder.scenario import build_scenario
from gimbal.prism.builder.steps import _build_step, _step_key

# Back-compat alias: legacy code/test imported the underscore-prefixed
# private name. After the split, `build_resource` is the canonical public
# name; expose `_build_resource` as an alias so existing imports keep
# working.
_build_resource = build_resource

__all__ = [
    "AuthDraft",
    "ResourceDraft",
    "ScenarioDraft",
    "StepDraft",
    "build_resource",
    "build_scenario",
    "_build_step",
    "_step_key",
    "_build_resource",
]