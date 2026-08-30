"""
Akium-WildcardManager for ComfyUI
by AkiumAI

Wildcards only, no dynamic prompts syntax.
"""

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
from . import wildcards_core as core

try:
    from . import api  # noqa: F401  (registers the /akium/wildcards routes)
except Exception as e:  # ComfyUI server not available (e.g. imported standalone)
    print(f"[Akium-WildcardManager] Manager API not loaded: {e}")

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]

_roots = core.get_roots(force=True)
print("[Akium-WildcardManager] Wildcard folders:")
for _r in _roots:
    print(f"  - {_r['label']}: {_r['path']}" + ("" if _r["writable"] else "  (read-only)"))
