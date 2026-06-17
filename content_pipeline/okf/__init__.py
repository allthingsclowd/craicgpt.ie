"""Open Knowledge Format (OKF v0.1) — deterministic serialization of the
code-verified research into a markdown+frontmatter bundle that grounds the judge.

The generic core mirrors the canonical reference in the ``grounding-judges-with-okf``
skill; ``build_craicgpt_bundle`` is the craicgpt mapper (one concept per curated
AI / fun candidate).
"""

from content_pipeline.okf.builder import (
    OKF_VERSION,
    Bundle,
    Concept,
    build_craicgpt_bundle,
    bundle_files,
    bundle_from_json,
    bundle_to_json,
    flatten_for_judge,
    render_concept,
    validate,
)

__all__ = [
    "OKF_VERSION",
    "Bundle",
    "Concept",
    "build_craicgpt_bundle",
    "bundle_files",
    "bundle_from_json",
    "bundle_to_json",
    "flatten_for_judge",
    "render_concept",
    "validate",
]
