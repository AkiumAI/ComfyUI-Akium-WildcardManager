"""
Akium-WildcardManager - core engine (framework agnostic)
by AkiumAI

Wildcards only, no dynamic prompts syntax.

This is the same resolution engine used by the Forge Neo extension, extended
with multi-root support so it can read wildcards from several folders at once
(its own folder, ComfyUI/wildcards, Impact Pack's folder, custom paths).

Search order for __token__:
  1. <root>/<token>.txt            (subfolders supported: __styles/artists__)
  2. <root>/<stem>.yaml|.yml       with dot navigation: __colors.warm__
  3. <root>/<token>.yaml|.yml      whole file, flattened
Roots are searched in order; the first match wins.

Token lookup ignores case, for file names and for YAML keys alike, so
__OC__, __oc__ and __Oc__ all resolve to oc.yaml on every platform. Windows
would do that on its own, Linux and macOS would not.
"""

from __future__ import annotations

import glob
import hashlib
import os
import re
import random
import time

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    print("[Akium-WildcardManager] PyYAML not found - YAML support disabled. Install with: pip install pyyaml")

LOG = "[Akium-WildcardManager]"

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_WILDCARDS_DIR = os.path.join(EXT_DIR, "wildcards")
EXTRA_ROOTS_FILE = os.path.join(EXT_DIR, "extra_wildcard_paths.txt")

VALID_EXTS = (".txt", ".yaml", ".yml")
ID_SEP = "::"

PATTERN_WILDCARD = re.compile(r"__([a-zA-Z0-9_\-/\.]+)__")


# -- Roots ----------------------------------------------------------------------
_roots_cache: dict = {"time": 0.0, "roots": []}
_ROOTS_TTL = 10.0  # seconds; refresh_roots() forces a rescan


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "root"


def _comfy_base_path() -> str:
    try:
        import folder_paths  # ComfyUI
        return os.path.abspath(folder_paths.base_path)
    except Exception:
        # custom_nodes/<this extension>/ -> ComfyUI root
        return os.path.abspath(os.path.join(EXT_DIR, "..", ".."))


def _read_extra_roots() -> list[tuple[str, str]]:
    """Reads extra_wildcard_paths.txt: one path per line, or 'name = path'."""
    out: list[tuple[str, str]] = []
    if not os.path.isfile(EXTRA_ROOTS_FILE):
        return out
    try:
        with open(EXTRA_ROOTS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    name, path = line.split("=", 1)
                else:
                    name, path = "", line
                out.append((name.strip(), path.strip()))
    except OSError as e:
        print(f"{LOG} Could not read {EXTRA_ROOTS_FILE}: {e}")
    return out


def discover_roots() -> list[dict]:
    """
    Returns [{name, label, path, writable}, ...] in search order.
    'name' is a slug used as the first half of a file id.
    """
    roots: list[dict] = []
    seen: set[str] = set()

    def add(label: str, path: str):
        if not path:
            return
        path = os.path.abspath(os.path.expanduser(path))
        key = os.path.normcase(path)
        if key in seen or not os.path.isdir(path):
            return
        seen.add(key)
        base = _slug(label)
        name, i = base, 2
        used = {r["name"] for r in roots}
        while name in used:
            name = f"{base}-{i}"
            i += 1
        roots.append({
            "name": name,
            "label": label,
            "path": path,
            "writable": os.access(path, os.W_OK),
        })

    try:
        os.makedirs(LOCAL_WILDCARDS_DIR, exist_ok=True)
    except OSError:
        pass
    add("akium", LOCAL_WILDCARDS_DIR)

    base_path = _comfy_base_path()
    add("comfyui", os.path.join(base_path, "wildcards"))

    custom_nodes = os.path.join(base_path, "custom_nodes")
    for pattern in ("*Impact-Pack*", "*Impact_Pack*", "*ImpactPack*"):
        for folder in sorted(glob.glob(os.path.join(custom_nodes, pattern, "wildcards"))):
            add(os.path.basename(os.path.dirname(folder)), folder)

    for label, path in _read_extra_roots():
        add(label or os.path.basename(path.rstrip("/\\")) or "extra", path)

    return roots


def get_roots(force: bool = False) -> list[dict]:
    now = time.time()
    if force or not _roots_cache["roots"] or (now - _roots_cache["time"]) > _ROOTS_TTL:
        _roots_cache["roots"] = discover_roots()
        _roots_cache["time"] = now
    return _roots_cache["roots"]


def refresh_roots() -> list[dict]:
    refresh_index()
    return get_roots(force=True)


def get_root(name: str) -> dict | None:
    for root in get_roots():
        if root["name"] == name:
            return root
    return None


# -- Case insensitive file index -------------------------------------------------
# One lowercase name -> real path map per root, so lookups behave the same on a
# case sensitive filesystem as they do on NTFS.
_index_cache: dict = {"time": 0.0, "indexes": None}
_INDEX_TTL = 5.0


def get_indexes(force: bool = False) -> list[dict]:
    """[{root, files: {lowercase relative path: absolute path}}, ...] in root order."""
    now = time.time()
    if force or _index_cache["indexes"] is None or (now - _index_cache["time"]) > _INDEX_TTL:
        indexes: list[dict] = []
        by_root: dict[str, dict] = {}
        for root, full, rel in iter_wildcard_files():
            entry = by_root.get(root["name"])
            if entry is None:
                entry = {"root": root, "files": {}}
                by_root[root["name"]] = entry
                indexes.append(entry)
            entry["files"].setdefault(rel.lower(), full)
        _index_cache["indexes"] = indexes
        _index_cache["time"] = now
    return _index_cache["indexes"]


def refresh_index():
    _index_cache["indexes"] = None


# -- Cache with mtime invalidation ----------------------------------------------
_file_cache: dict[str, tuple[float, object]] = {}


def _cached_read(path: str, loader):
    """Reads a file through the cache; reloads if the mtime changed."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    cached = _file_cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        data = loader(path)
    except Exception as e:
        print(f"{LOG} Failed to read {path}: {e}")
        return None
    _file_cache[path] = (mtime, data)
    return data


def _read_txt(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]


def _read_yaml(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def invalidate(path: str):
    _file_cache.pop(path, None)
    refresh_index()


# -- YAML utilities --------------------------------------------------------------
def _flatten_yaml(data) -> list[str]:
    """Recursively flattens a YAML object into a list of strings."""
    if data is None:
        return []
    if isinstance(data, str):
        return [data]
    if isinstance(data, list):
        out: list[str] = []
        for item in data:
            out.extend(_flatten_yaml(item))
        return out
    if isinstance(data, dict):
        out = []
        for v in data.values():
            out.extend(_flatten_yaml(v))
        return out
    return [str(data)]


def _navigate_yaml(data, keys: list[str]):
    """Walks the YAML dict following the key list, ignoring case. None if not found."""
    for key in keys:
        if not isinstance(data, dict):
            return None
        if key in data:
            data = data[key]
            continue
        match = {str(k).lower(): k for k in data}.get(key.lower())
        if match is None:
            return None
        data = data[match]
    return data


def _walk_yaml_paths(data, prefix=()):
    """Yields every (key-path tuple, node) of the nested dicts."""
    if isinstance(data, dict):
        for k, v in data.items():
            path = prefix + (str(k),)
            yield path, v
            yield from _walk_yaml_paths(v, path)


# -- File index -------------------------------------------------------------------
def iter_wildcard_files():
    """Yields (root, absolute_path, relative_path_with_slashes) for every valid file."""
    for root in get_roots():
        for dirpath, _dirs, files in os.walk(root["path"]):
            for fn in sorted(files):
                if fn.lower().endswith(VALID_EXTS):
                    full = os.path.join(dirpath, fn)
                    rel = os.path.relpath(full, root["path"]).replace("\\", "/")
                    yield root, full, rel


def collect_tokens() -> dict[str, int]:
    """
    Returns {token: entry_count} for every token usable as __token__.
    Includes .txt files (with subfolders) and every dot-path of .yaml files.
    When two roots define the same token, the first root wins.
    """
    tokens: dict[str, int] = {}
    for _root, full, rel in iter_wildcard_files():
        stem, ext = os.path.splitext(rel)
        ext = ext.lower()
        if ext == ".txt":
            tokens.setdefault(stem, len(_cached_read(full, _read_txt) or []))
        elif ext in (".yaml", ".yml") and YAML_AVAILABLE:
            data = _cached_read(full, _read_yaml)
            tokens.setdefault(stem, len(_flatten_yaml(data)))
            for path, node in _walk_yaml_paths(data):
                tokens.setdefault(stem + "." + ".".join(path), len(_flatten_yaml(node)))
    return tokens


def token_rows() -> list[dict]:
    """
    Token overview in file/tree order, for the manager panel.
    kind: "txt" | "yaml" | "key"   depth: nesting level of a yaml key
    """
    rows: list[dict] = []
    for root, full, rel in iter_wildcard_files():
        stem, ext = os.path.splitext(rel)
        ext = ext.lower()
        if ext == ".txt":
            lines = _cached_read(full, _read_txt) or []
            rows.append({"token": stem, "count": len(lines), "kind": "txt",
                         "depth": 0, "root": root["name"], "file": file_id(root["name"], rel)})
        elif ext in (".yaml", ".yml") and YAML_AVAILABLE:
            data = _cached_read(full, _read_yaml)
            rows.append({"token": stem, "count": len(_flatten_yaml(data)), "kind": "yaml",
                         "depth": 0, "root": root["name"], "file": file_id(root["name"], rel)})
            for path, node in _walk_yaml_paths(data):
                rows.append({"token": stem + "." + ".".join(path), "count": len(_flatten_yaml(node)),
                             "kind": "key", "depth": len(path), "root": root["name"],
                             "file": file_id(root["name"], rel)})
    return rows


def wildcards_signature() -> str:
    """Short hash of every wildcard file + mtime. Used to invalidate node caches."""
    parts = []
    for root, full, rel in iter_wildcard_files():
        try:
            parts.append(f"{root['name']}/{rel}:{int(os.path.getmtime(full))}")
        except OSError:
            continue
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


# -- Resolution -------------------------------------------------------------------
def get_wildcard_options(name: str) -> list[str] | None:
    """Returns the list of options for a token, or None if not found. Case insensitive."""
    name = (name or "").replace("\\", "/")
    lower = name.lower()

    for entry in get_indexes():
        files = entry["files"]

        # 1) exact .txt
        txt_path = files.get(lower + ".txt")
        if txt_path:
            lines = _cached_read(txt_path, _read_txt)
            if lines:
                return lines

        if not YAML_AVAILABLE:
            continue

        # 2) .yaml with dot navigation (the stem may contain subfolders)
        if "." in name:
            parts = name.split(".")
            for i in range(1, len(parts)):
                stem = ".".join(parts[:i]).lower()
                keys = parts[i:]
                for ext in (".yaml", ".yml"):
                    ypath = files.get(stem + ext)
                    if not ypath:
                        continue
                    data = _cached_read(ypath, _read_yaml)
                    node = _navigate_yaml(data, keys)
                    if node is None:
                        print(f"{LOG} Key not found in {os.path.basename(ypath)}: " + ".".join(keys))
                        continue
                    options = [l for l in _flatten_yaml(node) if l]
                    if options:
                        return options

        # 3) .yaml without keys (whole file flattened)
        for ext in (".yaml", ".yml"):
            ypath = files.get(lower + ext)
            if ypath:
                data = _cached_read(ypath, _read_yaml)
                options = [l for l in _flatten_yaml(data) if l]
                if options:
                    return options

    return None


def resolve_prompt(prompt: str, rng: random.Random, max_depth: int = 10) -> str:
    """
    Replaces every __name__ with a random line from the matching file.
    Loops to support nested wildcards (an entry containing __other__).
    """
    if not prompt:
        return prompt or ""

    warned: set[str] = set()

    def pick(m):
        name = m.group(1)
        options = get_wildcard_options(name)
        if not options:
            if name not in warned:
                warned.add(name)
                print(f"{LOG} Wildcard not found: '{name}'")
            return m.group(0)  # leave the token untouched
        return rng.choice(options)

    for _ in range(max_depth):
        new_prompt = PATTERN_WILDCARD.sub(pick, prompt)
        if new_prompt == prompt:
            break
        prompt = new_prompt
    return prompt


# -- File operations (used by the manager panel) -----------------------------------
def file_id(root_name: str, rel: str) -> str:
    return f"{root_name}{ID_SEP}{rel}"


def split_file_id(fid: str) -> tuple[str, str]:
    if ID_SEP not in (fid or ""):
        return "", ""
    root_name, rel = fid.split(ID_SEP, 1)
    return root_name, rel.replace("\\", "/")


def safe_path(root_name: str, rel: str) -> str | None:
    """Absolute path inside the given root; None if it tries to escape it."""
    root = get_root(root_name)
    if not root or not rel:
        return None
    full = os.path.abspath(os.path.join(root["path"], rel))
    root_abs = os.path.abspath(root["path"])
    if not full.startswith(root_abs + os.sep):
        return None
    if not full.lower().endswith(VALID_EXTS):
        return None
    return full


def list_files() -> list[dict]:
    return [
        {"id": file_id(root["name"], rel), "root": root["name"],
         "rel": rel, "writable": root["writable"]}
        for root, _full, rel in iter_wildcard_files()
    ]


def read_file(fid: str) -> tuple[str, str | None]:
    root_name, rel = split_file_id(fid)
    full = safe_path(root_name, rel)
    if not full or not os.path.isfile(full):
        return "", f"File not found: {rel or fid}"
    try:
        with open(full, "r", encoding="utf-8") as f:
            return f.read(), None
    except OSError as e:
        return "", f"Could not open the file: {e}"


def write_file(fid: str, content: str) -> str | None:
    """Returns an error message, or None on success."""
    root_name, rel = split_file_id(fid)
    full = safe_path(root_name, rel)
    if not full:
        return "Select a file first."
    if not os.path.isfile(full):
        return f"File not found: {rel}"
    if rel.lower().endswith((".yaml", ".yml")) and YAML_AVAILABLE:
        try:
            yaml.safe_load(content)
        except yaml.YAMLError as e:
            return f"Invalid YAML, nothing was saved:\n{e}"
    try:
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        return f"Could not write the file: {e}"
    invalidate(full)
    return None


def create_file(root_name: str, name: str, file_format: str) -> tuple[str | None, str | None]:
    """Returns (file_id, error)."""
    root = get_root(root_name)
    if not root:
        return None, "Pick a folder for the new file."
    if not root["writable"]:
        return None, f"The folder '{root['label']}' is read-only."

    name = (name or "").strip().replace("\\", "/").lstrip("/")
    if not name:
        return None, "Enter a file name."
    # The format selector is authoritative: strip any typed extension
    stem, ext = os.path.splitext(name)
    if ext.lower() in VALID_EXTS:
        name = stem
    name += ".txt" if file_format == "txt" else ".yaml"

    full = safe_path(root_name, name)
    if not full:
        return None, "That name is not allowed."
    if os.path.exists(full):
        return None, f"Already exists: {name}"

    template = ("# One entry per line, lines starting with # are ignored\n"
                if name.endswith(".txt") else
                "# Call with __filename.category__\ncategory:\n  - entry 1\n  - entry 2\n")
    try:
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(template)
    except OSError as e:
        return None, f"Could not create the file: {e}"
    refresh_index()
    return file_id(root_name, name), None


def delete_file(fid: str) -> str | None:
    root_name, rel = split_file_id(fid)
    root = get_root(root_name)
    full = safe_path(root_name, rel)
    if not root or not full or not os.path.isfile(full):
        return f"File not found: {rel or fid}"
    if not root["writable"]:
        return f"The folder '{root['label']}' is read-only."
    try:
        os.remove(full)
    except OSError as e:
        return f"Could not delete the file: {e}"
    invalidate(full)
    return None


def sort_dedupe(rel: str, content: str) -> tuple[str, str]:
    """Sorts A-Z and removes duplicate entries (.txt only). Returns (content, message)."""
    if rel and rel.lower().endswith((".yaml", ".yml")):
        return content, "Sort and dedupe works on .txt files only - it would break the YAML structure."
    lines = content.splitlines()
    comments = [l for l in lines if l.strip().startswith("#")]
    seen: set[str] = set()
    entries: list[str] = []
    total = 0
    for l in lines:
        s = l.strip()
        if not s or s.startswith("#"):
            continue
        total += 1
        key = s.lower()
        if key not in seen:
            seen.add(key)
            entries.append(s)
    removed = total - len(entries)
    entries.sort(key=str.lower)
    new_content = "\n".join(comments + entries)
    if new_content:
        new_content += "\n"
    return new_content, f"Sorted A-Z, removed {removed} duplicate(s). Save to apply."
