"""Pytest bootstrap.

Ensures the repository root is on ``sys.path`` so tests can import the
``content_pipeline`` package the same way the application does
(``from content_pipeline.config import cfg``).
"""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
