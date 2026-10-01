"""Pinned CMS package specs shared by init and the local preview harness.

Keep these in one place so a scaffolded ``package.json`` cannot ship a
manifest shape that the installed ``@caraer/cms-runtime`` types reject.
"""

from __future__ import annotations

PUBLISHED_RUNTIME_TAG = "v0.1.4"
PUBLISHED_TOKENS_TAG = "v0.1.2"

PUBLISHED_RUNTIME_SPEC = f"github:Caraer-HQ/caraer-cms-runtime#{PUBLISHED_RUNTIME_TAG}"
PUBLISHED_TOKENS_SPEC = f"github:Caraer-HQ/caraer-cms-tokens#{PUBLISHED_TOKENS_TAG}"
