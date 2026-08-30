/*
 * Akium-WildcardManager for ComfyUI
 * by AkiumAI
 *
 * Adds three things to the frontend:
 *   1. a "Wildcards" sidebar tab: file browser, editor, token list, test box
 *   2. __ autocomplete in every prompt box
 *   3. the resolved prompt shown on the node after it runs
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

const PREFIX = "/akium/wildcards";
const NODE_NAMES = ["AkiumWildcardPrompt", "AkiumWildcardEncode"];
const TOKEN_CHARS = /[a-zA-Z0-9_\-/.]/;
const TRIGGER = /(?:^|[\s,;:({\[|])__([a-zA-Z0-9_\-/.]*)$/;

/* ------------------------------------------------------------------ helpers */

async function call(path, options) {
  const res = await api.fetchApi(PREFIX + path, options);
  let data = {};
  try {
    data = await res.json();
  } catch (e) {
    /* keep the empty object */
  }
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

const post = (path, body) =>
  call(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "style") Object.assign(node.style, v);
    else if (k === "dataset") Object.assign(node.dataset, v);
    else if (k.startsWith("on")) node.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "className") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v);
  }
  for (const child of [].concat(children)) {
    if (child) node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

/* ------------------------------------------------------------- token store */

const tokens = {
  list: [],
  async refresh() {
    try {
      const data = await call("/tokens");
      this.list = data.tokens.map((t) => t.token);
    } catch (e) {
      console.error("[Akium-WildcardManager]", e);
    }
  },
};

/* -------------------------------------------------------------------- style */

const STYLE = `
.akwm { display:flex; flex-direction:column; gap:8px; height:100%; padding:10px;
        box-sizing:border-box; overflow:hidden; font-size:12px; color:var(--input-text,#ddd); }
.akwm-row { display:flex; gap:6px; align-items:center; }
.akwm-row > select { flex:1; min-width:0; }
.akwm select, .akwm input, .akwm textarea {
  background:var(--comfy-input-bg,#222); color:var(--input-text,#ddd);
  border:1px solid var(--border-color,#444); border-radius:4px; padding:4px 6px;
  font-size:12px; font-family:inherit; }
.akwm textarea { resize:none; }
.akwm button { background:var(--comfy-input-bg,#222); color:var(--input-text,#ddd);
  border:1px solid var(--border-color,#444); border-radius:4px; padding:4px 9px;
  font-size:12px; cursor:pointer; white-space:nowrap; }
.akwm button:hover:not(:disabled) { background:var(--comfy-menu-bg,#353535); }
.akwm button:disabled { opacity:.45; cursor:default; }
.akwm button.primary { border-color:var(--p-primary-color,#5b9dd9); }
.akwm-editor { flex:1 1 auto; min-height:120px; font-family:ui-monospace,Consolas,monospace;
  line-height:1.45; white-space:pre; overflow:auto; }
.akwm-status { min-height:15px; opacity:.8; white-space:pre-wrap; }
.akwm-status.error { color:var(--error-text,#f16b6b); opacity:1; }
.akwm-label { text-transform:uppercase; letter-spacing:.06em; font-size:10px; opacity:.6; }
.akwm-sep { border-top:1px solid var(--border-color,#444); margin:2px 0; }
.akwm-tokens { max-height:26vh; overflow:auto; border:1px solid var(--border-color,#444);
  border-radius:4px; }
.akwm-token { display:flex; justify-content:space-between; gap:6px; padding:2px 6px;
  cursor:pointer; font-family:ui-monospace,Consolas,monospace; }
.akwm-token:hover { background:var(--content-hover-bg,#3a3a3a); }
.akwm-token .count { opacity:.5; }
.akwm-token.file { font-weight:600; }
.akwm-empty { padding:8px; opacity:.6; }
.akwm-form { display:flex; flex-direction:column; gap:6px; padding:8px;
  border:1px solid var(--border-color,#444); border-radius:4px; }
.akwm-help { opacity:.8; line-height:1.5; }
.akwm-help code, .akwm-help pre { background:var(--comfy-input-bg,#222); border-radius:3px;
  font-family:ui-monospace,Consolas,monospace; }
.akwm-help code { padding:0 3px; }
.akwm-help pre { padding:6px; overflow:auto; }
.akwm-ac { position:fixed; z-index:10000; max-height:230px; overflow:auto; min-width:190px;
  background:var(--comfy-menu-bg,#282828); border:1px solid var(--border-color,#555);
  border-radius:5px; box-shadow:0 6px 18px rgba(0,0,0,.45); font-size:12px;
  font-family:ui-monospace,Consolas,monospace; }
.akwm-ac-item { display:flex; justify-content:space-between; gap:10px; padding:3px 8px;
  cursor:pointer; color:var(--input-text,#ddd); }
.akwm-ac-item.active { background:var(--p-primary-color,#4a7fb5); color:#fff; }
`;

function injectStyle() {
  if (document.getElementById("akwm-style")) return;
  document.head.appendChild(el("style", { id: "akwm-style", text: STYLE }));
}

const HELP = `
<p><b>Text files (.txt)</b> hold one entry per line. A file called <code>hair_color.txt</code>
is used in a prompt as <code>__hair_color__</code>, and one line gets picked at random.
Lines starting with <code>#</code> are comments. Subfolders work too:
<code>styles/artists.txt</code> becomes <code>__styles/artists__</code>.</p>
<p><b>YAML files (.yaml)</b> keep several lists in one file:</p>
<pre>warm:
  - red
  - orange
cool:
  - blue
  - teal</pre>
<p>In <code>colors.yaml</code> that gives you <code>__colors.warm__</code> for the warm list and
<code>__colors__</code> for all four. Categories can nest as deep as you want.
A category name ends with <code>:</code>, every entry below starts with <code>-</code>, and
indentation uses spaces, never tabs. Broken YAML is refused on save with the reason.</p>
<p>An entry can contain other wildcards, so <code>__hair_color__ with hat</code> works as a line.
Two folders defining the same token: the first folder in the list wins.</p>`;

/* ------------------------------------------------------------------- panel */

function buildPanel(container) {
  const state = { roots: [], files: [], rows: [], currentId: null, dirty: false };

  const fileSelect = el("select", { title: "Wildcard file" });
  const refreshBtn = el("button", { text: "Refresh", title: "Rescan the wildcard folders" });
  const newBtn = el("button", { text: "New file" });
  const deleteBtn = el("button", { text: "Delete" });
  const editor = el("textarea", { className: "akwm-editor", spellcheck: "false",
                                  dataset: { akwmNoac: "1" },
                                  placeholder: "Select a file above to edit it." });
  const saveBtn = el("button", { className: "primary", text: "Save" });
  const sortBtn = el("button", { text: "Sort A-Z", title: "Sort and remove duplicates (.txt only)" });
  const status = el("div", { className: "akwm-status" });
  const filter = el("input", { type: "text", placeholder: "Filter tokens" });
  const tokenList = el("div", { className: "akwm-tokens" });
  const testInput = el("input", { type: "text", placeholder: "1girl, __hair_color__" });
  const testBtn = el("button", { text: "Resolve" });
  const testOut = el("div", { style: { fontFamily: "ui-monospace,Consolas,monospace",
                                       opacity: ".85", wordBreak: "break-word" } });

  const nameInput = el("input", { type: "text", placeholder: "hair_color or styles/artists" });
  const formatSelect = el("select", {}, [
    el("option", { value: "txt", text: "Text (.txt) - one entry per line" }),
    el("option", { value: "yaml", text: "YAML (.yaml) - nested categories" }),
  ]);
  const rootSelect = el("select", {});
  const createBtn = el("button", { className: "primary", text: "Create" });
  const cancelBtn = el("button", { text: "Cancel" });
  const helpBody = el("div", { className: "akwm-help" });
  helpBody.innerHTML = HELP;
  const help = el("details", {}, [
    el("summary", { text: "How wildcard files work", style: { cursor: "pointer", opacity: ".75" } }),
    helpBody,
  ]);

  const newForm = el("div", { className: "akwm-form", style: { display: "none" } }, [
    el("div", { className: "akwm-label", text: "New file" }),
    nameInput, formatSelect, rootSelect,
    el("div", { className: "akwm-row" }, [createBtn, cancelBtn]),
  ]);

  const root = el("div", { className: "akwm" }, [
    el("div", { className: "akwm-row" }, [fileSelect, refreshBtn]),
    el("div", { className: "akwm-row" }, [newBtn, deleteBtn]),
    newForm,
    editor,
    el("div", { className: "akwm-row" }, [saveBtn, sortBtn]),
    status,
    el("div", { className: "akwm-sep" }),
    el("div", { className: "akwm-label", text: "Tokens" }),
    filter,
    tokenList,
    el("div", { className: "akwm-sep" }),
    el("div", { className: "akwm-label", text: "Test a prompt" }),
    el("div", { className: "akwm-row" }, [testInput, testBtn]),
    testOut,
    help,
  ]);
  container.appendChild(root);

  /* -- rendering -- */

  const say = (message, isError = false) => {
    status.textContent = message || "";
    status.classList.toggle("error", !!isError);
  };

  function renderFiles() {
    fileSelect.replaceChildren();
    if (!state.files.length) {
      fileSelect.appendChild(el("option", { value: "", text: "No wildcard files found" }));
      return;
    }
    for (const rootDef of state.roots) {
      const files = state.files.filter((f) => f.root === rootDef.name);
      if (!files.length) continue;
      const group = el("optgroup", {
        label: rootDef.label + (rootDef.writable ? "" : " (read-only)"),
      });
      for (const f of files) group.appendChild(el("option", { value: f.id, text: f.rel }));
      fileSelect.appendChild(group);
    }
    if (state.currentId) fileSelect.value = state.currentId;
  }

  function renderTokens() {
    const query = filter.value.trim().toLowerCase();
    const rows = query
      ? state.rows.filter((r) => r.token.toLowerCase().includes(query))
      : state.rows;
    tokenList.replaceChildren();
    if (!rows.length) {
      tokenList.appendChild(el("div", {
        className: "akwm-empty",
        text: state.rows.length ? "No tokens match that filter." : "No wildcards yet. Create a file to get started.",
      }));
      return;
    }
    for (const row of rows) {
      const indent = query ? 0 : row.depth;
      const item = el("div", {
        className: "akwm-token" + (row.kind === "key" ? "" : " file"),
        title: `${row.root} / ${row.file.split("::")[1]}  -  click to insert`,
        style: { paddingLeft: `${6 + indent * 10}px` },
        onclick: () => insertToken(row.token, say),
      }, [
        el("span", { text: `__${row.token}__` }),
        el("span", { className: "count", text: String(row.count) }),
      ]);
      tokenList.appendChild(item);
    }
  }

  function renderRoots() {
    rootSelect.replaceChildren();
    for (const r of state.roots.filter((r) => r.writable)) {
      rootSelect.appendChild(el("option", { value: r.name, text: r.label }));
    }
  }

  /* -- data -- */

  async function reload(rescan = false) {
    try {
      const data = await call(`/state${rescan ? "?rescan=1" : ""}`);
      state.roots = data.roots;
      state.files = data.files;
      state.rows = data.rows;
      if (!state.files.some((f) => f.id === state.currentId)) state.currentId = null;
      renderFiles();
      renderRoots();
      renderTokens();
      updateButtons();
      if (!data.yaml) say("PyYAML is missing, so .yaml files are ignored. Install it with: pip install pyyaml", true);
    } catch (e) {
      say(e.message, true);
    }
    tokens.refresh();
  }

  function currentFile() {
    return state.files.find((f) => f.id === state.currentId) || null;
  }

  function updateButtons() {
    const file = currentFile();
    const editable = !!file && file.writable;
    editor.readOnly = !editable;
    saveBtn.disabled = !editable;
    sortBtn.disabled = !editable;
    deleteBtn.disabled = !editable;
  }

  async function openFile(id) {
    if (state.dirty && !confirm("You have unsaved changes. Discard them?")) {
      fileSelect.value = state.currentId || "";
      return;
    }
    state.currentId = id || null;
    state.dirty = false;
    updateButtons();
    if (!id) {
      editor.value = "";
      return;
    }
    try {
      const data = await call(`/file?id=${encodeURIComponent(id)}`);
      editor.value = data.content;
      const file = currentFile();
      say(file && !file.writable ? "This folder is read-only." : "");
    } catch (e) {
      editor.value = "";
      say(e.message, true);
    }
  }

  /* -- events -- */

  fileSelect.onchange = () => openFile(fileSelect.value);
  editor.oninput = () => { state.dirty = true; };
  filter.oninput = renderTokens;
  refreshBtn.onclick = () => { reload(true); say("Folders rescanned."); };

  saveBtn.onclick = async () => {
    if (!state.currentId) return say("Select a file first.", true);
    try {
      await post("/file", { id: state.currentId, content: editor.value });
      state.dirty = false;
      say("Saved.");
      reload();
    } catch (e) {
      say(e.message, true);
    }
  };

  sortBtn.onclick = async () => {
    if (!state.currentId) return say("Select a file first.", true);
    try {
      const data = await post("/sort", { id: state.currentId, content: editor.value });
      if (data.content !== editor.value) {
        editor.value = data.content;
        state.dirty = true;
      }
      say(data.message);
    } catch (e) {
      say(e.message, true);
    }
  };

  newBtn.onclick = () => {
    newForm.style.display = newForm.style.display === "none" ? "flex" : "none";
    if (newForm.style.display === "flex") nameInput.focus();
  };
  cancelBtn.onclick = () => { newForm.style.display = "none"; };

  createBtn.onclick = async () => {
    try {
      const data = await post("/create", {
        root: rootSelect.value,
        name: nameInput.value,
        format: formatSelect.value,
      });
      nameInput.value = "";
      newForm.style.display = "none";
      await reload();
      state.currentId = data.id;
      state.dirty = false;
      renderFiles();
      await openFile(data.id);
      say(data.message);
    } catch (e) {
      say(e.message, true);
    }
  };

  deleteBtn.onclick = async () => {
    const file = currentFile();
    if (!file) return say("Select a file first.", true);
    if (!confirm(`Delete ${file.rel}? This cannot be undone.`)) return;
    try {
      const data = await post("/delete", { id: file.id });
      state.currentId = null;
      state.dirty = false;
      editor.value = "";
      await reload();
      say(data.message);
    } catch (e) {
      say(e.message, true);
    }
  };

  const runTest = async () => {
    try {
      const data = await post("/resolve", { text: testInput.value });
      testOut.textContent = data.result;
    } catch (e) {
      testOut.textContent = e.message;
    }
  };
  testBtn.onclick = runTest;
  testInput.onkeydown = (e) => { if (e.key === "Enter") runTest(); };

  reload();
  return { reload };
}

/* -------------------------------------------------- insert into a prompt box */

let lastPromptInput = null;

function isPromptInput(node) {
  return node && node.tagName === "TEXTAREA" && !node.dataset.akwmNoac;
}

function insertToken(token, say) {
  const target = lastPromptInput;
  const text = `__${token}__`;
  if (!target || !document.body.contains(target)) {
    navigator.clipboard?.writeText(text);
    say?.(`Copied ${text} - click a prompt box first to insert it directly.`);
    return;
  }
  const caret = target.selectionStart ?? target.value.length;
  const before = target.value.slice(0, caret);
  const after = target.value.slice(target.selectionEnd ?? caret);
  const spacer = before && !/[\s,]$/.test(before) ? ", " : "";
  target.value = before + spacer + text + after;
  const pos = before.length + spacer.length + text.length;
  target.setSelectionRange(pos, pos);
  target.dispatchEvent(new Event("input", { bubbles: true }));
  target.focus();
  say?.(`Inserted ${text}.`);
}

/* ----------------------------------------------------------- autocomplete */

const ac = { box: null, items: [], index: 0, target: null, start: 0, skip: false };

function caretPoint(ta) {
  const style = getComputedStyle(ta);
  const mirror = document.createElement("div");
  const copy = ["fontFamily", "fontSize", "fontWeight", "fontStyle", "letterSpacing",
    "textTransform", "wordSpacing", "textIndent", "lineHeight", "paddingTop", "paddingRight",
    "paddingBottom", "paddingLeft", "borderTopWidth", "borderRightWidth", "borderBottomWidth",
    "borderLeftWidth", "boxSizing"];
  copy.forEach((p) => (mirror.style[p] = style[p]));
  Object.assign(mirror.style, {
    position: "absolute", visibility: "hidden", whiteSpace: "pre-wrap",
    wordWrap: "break-word", overflow: "hidden", top: "0", left: "-9999px",
    width: style.width, height: "auto",
  });
  mirror.textContent = ta.value.slice(0, ta.selectionStart);
  const marker = el("span", { text: "\u200b" });
  mirror.appendChild(marker);
  document.body.appendChild(mirror);
  const rect = ta.getBoundingClientRect();
  const lineHeight = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.4;
  const point = {
    x: rect.left + marker.offsetLeft - ta.scrollLeft,
    y: rect.top + marker.offsetTop - ta.scrollTop + lineHeight,
  };
  mirror.remove();
  return point;
}

function hideAc() {
  ac.box?.remove();
  ac.box = null;
  ac.items = [];
  ac.target = null;
}

function renderAc() {
  if (!ac.box) {
    ac.box = el("div", { className: "akwm-ac" });
    document.body.appendChild(ac.box);
  }
  ac.box.replaceChildren();
  ac.items.forEach((token, i) => {
    ac.box.appendChild(el("div", {
      className: "akwm-ac-item" + (i === ac.index ? " active" : ""),
      onmousedown: (e) => { e.preventDefault(); acceptAc(i); },
      onmouseenter: () => { ac.index = i; renderAc(); },
    }, [el("span", { text: token })]));
  });
  const point = caretPoint(ac.target);
  const width = ac.box.offsetWidth || 200;
  const height = ac.box.offsetHeight || 100;
  ac.box.style.left = `${Math.min(point.x, window.innerWidth - width - 8)}px`;
  ac.box.style.top = point.y + height > window.innerHeight
    ? `${Math.max(4, point.y - height - 22)}px`
    : `${point.y}px`;
  ac.box.querySelector(".active")?.scrollIntoView({ block: "nearest" });
}

function maybeShowAc(target) {
  if (ac.skip) { ac.skip = false; return hideAc(); }
  const caret = target.selectionStart;
  const match = TRIGGER.exec(target.value.slice(0, caret));
  if (!match) return hideAc();
  const query = match[1].toLowerCase();
  const pool = tokens.list;
  const starts = pool.filter((t) => t.toLowerCase().startsWith(query));
  const contains = pool.filter((t) => !starts.includes(t) && t.toLowerCase().includes(query));
  ac.items = [...starts, ...contains].slice(0, 15);
  if (!ac.items.length) return hideAc();
  ac.target = target;
  ac.start = caret - match[1].length - 2; // position of the opening __
  ac.index = 0;
  renderAc();
}

function acceptAc(index = ac.index) {
  const token = ac.items[index];
  const target = ac.target;
  if (!token || !target) return hideAc();
  const caret = target.selectionStart;
  const before = target.value.slice(0, ac.start);
  const after = target.value.slice(caret);
  const insert = `__${token}__`;
  target.value = before + insert + after;
  const pos = before.length + insert.length;
  target.setSelectionRange(pos, pos);
  ac.skip = true;
  target.dispatchEvent(new Event("input", { bubbles: true }));
  hideAc();
  target.focus();
}

function setupAutocomplete() {
  document.addEventListener("focusin", (e) => {
    if (isPromptInput(e.target)) lastPromptInput = e.target;
  });
  document.addEventListener("input", (e) => {
    if (isPromptInput(e.target)) maybeShowAc(e.target);
  }, true);
  document.addEventListener("keydown", (e) => {
    if (!ac.box || e.target !== ac.target) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      e.stopPropagation();
      ac.index = (ac.index + (e.key === "ArrowDown" ? 1 : -1) + ac.items.length) % ac.items.length;
      renderAc();
    } else if (e.key === "Enter" || e.key === "Tab") {
      e.preventDefault();
      e.stopPropagation();
      acceptAc();
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      hideAc();
    }
  }, true);
  document.addEventListener("mousedown", (e) => {
    if (ac.box && !ac.box.contains(e.target)) hideAc();
  });
  window.addEventListener("blur", hideAc);
}

/* ------------------------------------------------- keep the preview out of the API prompt */

// The preview widget must never reach the queued prompt: it would carry the
// previous run's text into the metadata of the next image. onSerialize covers
// the workflow, this covers the API prompt.
function patchGraphToPrompt() {
  if (app.__akiumWildcardPatch) return;
  app.__akiumWildcardPatch = true;
  const original = app.graphToPrompt;
  app.graphToPrompt = async function (...args) {
    const result = await original.apply(this, args);
    for (const node of Object.values(result?.output ?? {})) {
      if (NODE_NAMES.includes(node?.class_type) && node.inputs) delete node.inputs.resolved;
    }
    return result;
  };
}

/* ------------------------------------------------------------- registration */

app.registerExtension({
  name: "akium.wildcardmanager",

  async setup() {
    injectStyle();
    await tokens.refresh();
    setupAutocomplete();
    patchGraphToPrompt();

    if (!app.extensionManager?.registerSidebarTab) {
      console.warn("[Akium-WildcardManager] This ComfyUI frontend has no sidebar API - " +
                   "the nodes and autocomplete still work.");
      return;
    }
    app.extensionManager.registerSidebarTab({
      id: "akiumWildcards",
      icon: "pi pi-clone",
      title: "Wildcards",
      tooltip: "Akium Wildcard Manager",
      type: "custom",
      render: (element) => {
        injectStyle();
        element.replaceChildren();
        buildPanel(element);
      },
    });
  },

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!NODE_NAMES.includes(nodeData.name)) return;

    // The preview widget is display only. Without this it would be serialized
    // with the graph, so every queued run would carry the previous run's text
    // into the saved workflow and into the PNG metadata.
    const onSerialize = nodeType.prototype.onSerialize;
    nodeType.prototype.onSerialize = function (o) {
      onSerialize?.apply(this, arguments);
      const index = this.widgets?.findIndex((w) => w.name === "resolved") ?? -1;
      if (index >= 0 && Array.isArray(o.widgets_values) && o.widgets_values.length > index) {
        o.widgets_values.splice(index, 1);
      }
    };

    const onExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (message) {
      onExecuted?.apply(this, arguments);
      const text = message?.text?.[0];
      if (text === undefined) return;
      let widget = this.widgets?.find((w) => w.name === "resolved");
      if (!widget) {
        widget = ComfyWidgets["STRING"](this, "resolved", ["STRING", { multiline: true }], app).widget;
        widget.serialize = false;
        widget.serializeValue = async () => undefined;
        if (widget.options) widget.options.serialize = false;
        if (widget.inputEl) {
          widget.inputEl.readOnly = true;
          widget.inputEl.style.opacity = "0.7";
          widget.inputEl.dataset.akwmNoac = "1";
          widget.inputEl.placeholder = "The resolved prompt shows up here after a run.";
        }
      }
      widget.value = text;
      this.setSize?.(this.computeSize());
      app.graph.setDirtyCanvas(true, false);
    };
  },
});
