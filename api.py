"""
Akium-WildcardManager - HTTP API for the manager panel
by AkiumAI

All routes live under /akium/wildcards and are served by ComfyUI's own aiohttp app.
Every path goes through wildcards_core.safe_path(), so requests cannot read or
write outside the configured wildcard folders.
"""

import random

from aiohttp import web
from server import PromptServer

from . import wildcards_core as core

PREFIX = "/akium/wildcards"
routes = PromptServer.instance.routes


def _ok(**payload):
    return web.json_response({"ok": True, **payload})


def _fail(message, status=400):
    return web.json_response({"ok": False, "error": message}, status=status)


async def _body(request):
    try:
        return await request.json()
    except Exception:
        return {}


@routes.get(f"{PREFIX}/state")
async def get_state(request):
    """Everything the panel needs on open or refresh."""
    if request.query.get("rescan") == "1":
        core.refresh_roots()
    return _ok(
        roots=[{"name": r["name"], "label": r["label"], "path": r["path"], "writable": r["writable"]}
               for r in core.get_roots()],
        files=core.list_files(),
        rows=core.token_rows(),
        yaml=core.YAML_AVAILABLE,
    )


@routes.get(f"{PREFIX}/tokens")
async def get_tokens(request):
    """Flat token list, used by the prompt autocomplete."""
    try:
        tokens = core.collect_tokens()
    except Exception as e:
        return _fail(str(e), status=500)
    return _ok(tokens=[{"token": t, "count": c} for t, c in sorted(tokens.items())])


@routes.get(f"{PREFIX}/file")
async def get_file(request):
    content, error = core.read_file(request.query.get("id", ""))
    if error:
        return _fail(error, status=404)
    return _ok(content=content)


@routes.post(f"{PREFIX}/file")
async def post_file(request):
    data = await _body(request)
    error = core.write_file(data.get("id", ""), data.get("content", ""))
    if error:
        return _fail(error)
    return _ok(message="Saved.")


@routes.post(f"{PREFIX}/create")
async def post_create(request):
    data = await _body(request)
    fid, error = core.create_file(
        data.get("root", ""), data.get("name", ""), data.get("format", "txt"))
    if error:
        return _fail(error)
    return _ok(id=fid, message="File created.")


@routes.post(f"{PREFIX}/delete")
async def post_delete(request):
    data = await _body(request)
    error = core.delete_file(data.get("id", ""))
    if error:
        return _fail(error)
    return _ok(message="File deleted.")


@routes.post(f"{PREFIX}/sort")
async def post_sort(request):
    data = await _body(request)
    _root, rel = core.split_file_id(data.get("id", ""))
    content, message = core.sort_dedupe(rel, data.get("content", ""))
    return _ok(content=content, message=message)


@routes.post(f"{PREFIX}/resolve")
async def post_resolve(request):
    data = await _body(request)
    text = data.get("text", "")
    if not text.strip():
        return _fail("Enter a prompt with __wildcard__ to test.")
    seed = data.get("seed")
    rng = random.Random(seed) if isinstance(seed, int) else random.Random()
    try:
        return _ok(result=core.resolve_prompt(text, rng))
    except Exception as e:
        return _fail(str(e), status=500)


print(f"[Akium-WildcardManager] API ready at {PREFIX}")
