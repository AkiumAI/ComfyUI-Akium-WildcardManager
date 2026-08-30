# Akium Wildcard Manager (ComfyUI)

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-support-ff5e5b?logo=ko-fi&logoColor=white)](https://ko-fi.com/akinak4)

Wildcards for ComfyUI, with a manager panel to edit them without leaving the browser.
Same engine as the Forge Neo extension: `__token__` in a prompt is replaced by a random
entry from the matching file. No dynamic prompts syntax.

## Install

```
cd ComfyUI/custom_nodes
git clone <your repo> ComfyUI-Akium-WildcardManager
pip install pyyaml
```

Restart ComfyUI. The console prints every wildcard folder that was found.

## Nodes

| Node | Output | Use it for |
|---|---|---|
| **Wildcard Prompt (Akium)** | `STRING` | Feed a resolved prompt into CLIP Text Encode or anything else that takes text. |
| **Wildcard Encode (Akium)** | `CONDITIONING`, `STRING` | Drop-in replacement for CLIP Text Encode when the prompt has wildcards. |

Both have a `seed` widget. Set the control under it to **randomize** for a new roll on
every run, or **fixed** to keep the same picks. After a run the node shows the resolved
prompt underneath, so you can see what actually got generated.

The workflow embedded in the PNG stores the unresolved template, which is what you want
for re-rolling. To keep the finished text as well, wire the `prompt` output into a
string-saving node of your choice.

Note on batches: `batch_size` on the latent produces several images from one prompt, so
the wildcards resolve once. For a different prompt per image, queue the workflow N times
with the seed control on randomize.

## Wildcard folders

Folders are searched in this order, and the first match for a token wins:

1. `custom_nodes/ComfyUI-Akium-WildcardManager/wildcards`
2. `ComfyUI/wildcards`
3. `custom_nodes/ComfyUI-Impact-Pack/wildcards` (any Impact Pack variant)
4. anything listed in `extra_wildcard_paths.txt`

To share one collection with a Forge install, copy `extra_wildcard_paths.txt.example`
to `extra_wildcard_paths.txt` and point it at the Forge extension's `wildcards` folder.
Read-only folders show up in the panel but can't be edited.

## File format

`.txt` files hold one entry per line; `hair_color.txt` is used as `__hair_color__`.
Lines starting with `#` are comments. Subfolders work: `styles/artists.txt` becomes
`__styles/artists__`.

Token lookup ignores case, so `__hair_color__`, `__Hair_Color__` and
`__HAIR_COLOR__` all reach `hair_color.txt` on Linux and macOS too, not just on
Windows. The same goes for YAML category names.

`.yaml` files hold several lists in one file:

```yaml
warm:
  - red
  - orange
cool:
  - blue
  - teal
```

In `colors.yaml` that gives `__colors.warm__` for one category and `__colors__` for the
whole file. Categories nest as deep as you like. Entries can contain other wildcards,
up to 10 levels of nesting.

## The Wildcards panel

Open the **Wildcards** tab in the sidebar to browse and edit files, create and delete
them, sort a `.txt` file A-Z with duplicates removed, and test a prompt without queueing
anything. The token list shows every `__token__` with its entry count; clicking one
inserts it into the last prompt box you touched.

Typing `__` in any prompt box brings up autocomplete. Arrow keys move, Enter or Tab
inserts, Escape closes.

## API

The panel talks to these routes, in case you want to script against them:
`GET /akium/wildcards/state`, `GET /akium/wildcards/tokens`,
`GET|POST /akium/wildcards/file`, `POST /akium/wildcards/create`,
`POST /akium/wildcards/delete`, `POST /akium/wildcards/sort`,
`POST /akium/wildcards/resolve`.

## Layout

```
ComfyUI-Akium-WildcardManager/
├── __init__.py                     node + web registration
├── nodes.py                        the two nodes
├── api.py                          routes for the panel
├── wildcards_core.py               resolution engine (shared with the Forge version)
├── web/manager.js                  sidebar panel, autocomplete, node preview
├── example_workflows/              drag one into ComfyUI to get started
├── extra_wildcard_paths.txt.example
└── wildcards/                      your files
```

`wildcards_core.py` has no ComfyUI imports beyond an optional `folder_paths` lookup, so
it can be dropped into the Forge extension as-is and kept in sync.

## Support

This extension is free and MIT licensed. If it saves you time, you can buy me a
coffee at [ko-fi.com/akinak4](https://ko-fi.com/akinak4). Bug reports and pull
requests are just as welcome.

by AkiumAI
