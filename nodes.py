"""
Akium-WildcardManager - ComfyUI nodes
by AkiumAI
"""

import random

from . import wildcards_core as core

MAX_SEED = 0xFFFFFFFFFFFFFFFF

HIDDEN = {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO", "unique_id": "UNIQUE_ID"}

SEED_INPUT = ("INT", {
    "default": 0,
    "min": 0,
    "max": MAX_SEED,
    "control_after_generate": True,
    "tooltip": "Picks are reproducible for a given seed. Set the control below to 'randomize' "
               "for a different roll on every run.",
})

TEXT_INPUT = ("STRING", {
    "multiline": True,
    "dynamicPrompts": False,
    "default": "1girl, __hair_color__, __colors.warm__ background",
    "tooltip": "Type __ in this box to autocomplete a wildcard token.",
})


def _record(resolved: str, prompt, extra_pnginfo, unique_id):
    """
    Records the prompt this node actually produced, in both metadata chunks the
    image carries: extra.akium_wildcards[node_id] in the workflow, and a
    'resolved' input in the API prompt. Both dicts are the same objects SaveImage
    later writes, so the values always belong to the image being saved.

    The text widget keeps the unresolved template, so re-queueing a saved
    workflow rolls the wildcards again instead of repeating one draw.
    """
    node_id = str(unique_id)
    try:
        workflow = (extra_pnginfo or {}).get("workflow")
        if isinstance(workflow, dict):
            extra = workflow.setdefault("extra", {})
            extra.setdefault("akium_wildcards", {})[node_id] = resolved
    except Exception as e:
        print(f"[Akium-WildcardManager] Could not record the resolved prompt: {e}")
    try:
        node = (prompt or {}).get(node_id)
        if isinstance(node, dict) and isinstance(node.get("inputs"), dict):
            node["inputs"]["resolved"] = resolved
    except Exception as e:
        print(f"[Akium-WildcardManager] Could not record the resolved prompt: {e}")


def _encode(clip, text: str):
    tokens = clip.tokenize(text)
    if hasattr(clip, "encode_from_tokens_scheduled"):
        return clip.encode_from_tokens_scheduled(tokens)
    cond, pooled = clip.encode_from_tokens(tokens, return_pooled=True)
    return [[cond, {"pooled_output": pooled}]]


class AkiumWildcardPrompt:
    """Resolves __wildcards__ in a prompt and outputs plain text."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"text": TEXT_INPUT, "seed": SEED_INPUT}, "hidden": HIDDEN}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    FUNCTION = "run"
    CATEGORY = "AkiumAI/Wildcards"
    DESCRIPTION = "Replaces every __token__ with a random entry from the matching wildcard file."

    @classmethod
    def IS_CHANGED(cls, text, seed, **_kwargs):
        # Re-runs when the prompt, the seed, or any wildcard file changes.
        return f"{seed}|{core.wildcards_signature()}|{text}"

    def run(self, text, seed, prompt=None, extra_pnginfo=None, unique_id=None):
        resolved = core.resolve_prompt(text or "", random.Random(seed))
        _record(resolved, prompt, extra_pnginfo, unique_id)
        return {"ui": {"text": [resolved]}, "result": (resolved,)}


class AkiumWildcardEncode:
    """Resolves __wildcards__ and encodes the result with CLIP in one step."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "clip": ("CLIP", {"tooltip": "The CLIP model used to encode the prompt."}),
                "text": TEXT_INPUT,
                "seed": SEED_INPUT,
            },
            "hidden": HIDDEN,
        }

    RETURN_TYPES = ("CONDITIONING", "STRING")
    RETURN_NAMES = ("conditioning", "prompt")
    FUNCTION = "run"
    CATEGORY = "AkiumAI/Wildcards"
    DESCRIPTION = "Resolves wildcards, then encodes the finished prompt. Replaces CLIP Text Encode."

    @classmethod
    def IS_CHANGED(cls, clip, text, seed, **_kwargs):
        return f"{seed}|{core.wildcards_signature()}|{text}"

    def run(self, clip, text, seed, prompt=None, extra_pnginfo=None, unique_id=None):
        resolved = core.resolve_prompt(text or "", random.Random(seed))
        _record(resolved, prompt, extra_pnginfo, unique_id)
        conditioning = _encode(clip, resolved)
        return {"ui": {"text": [resolved]}, "result": (conditioning, resolved)}


NODE_CLASS_MAPPINGS = {
    "AkiumWildcardPrompt": AkiumWildcardPrompt,
    "AkiumWildcardEncode": AkiumWildcardEncode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "AkiumWildcardPrompt": "Wildcard Prompt (Akium)",
    "AkiumWildcardEncode": "Wildcard Encode (Akium)",
}
