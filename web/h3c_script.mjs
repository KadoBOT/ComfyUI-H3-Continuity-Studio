// The Script: the Timeline as a list of clips read from top to bottom. Each clip shows its prompt beside its last
// rendered frame, the line between two clips says how the second one starts, and "What happens next?" adds a clip by
// choosing that. It edits the same Timeline state as the classic panels and writes nothing they could not write.
import * as model from './h3c_timeline_model.mjs?v=3e1fe9285010';
import {promptShots, writePromptSections} from './h3c_prompt_sections.mjs?v=b58f04f78a75';
import {continueAfterStack} from './h3c_layers.mjs?v=3e1fe9285010';

const STYLE_ID = 'h3cs-style';
const CSS = `
.h3cs-script { --h3cs-line:#3b3e43; --h3cs-dim:#aeaea9; --h3cs-faint:#8f9196; --h3cs-ink:#ebe8e1; --h3cs-panel:#242528;
  --h3cs-continue:#e6c229; --h3cs-cut:#ebe8e1; --h3cs-scene:#62b0e8; --h3cs-bridge:#5fd0a0; --h3cs-problem:#ef6a57;
  min-width:0; min-height:0; overflow-y:auto; padding:18px 20px 40px 8px; color:var(--h3cs-ink); font-variant-numeric:tabular-nums; }
.h3cs-list { max-width:800px; }
.h3cs-row { display:grid; grid-template-columns:44px minmax(0,1fr); }
.h3cs-gut { position:relative; display:flex; justify-content:center; }
.h3cs-gut::before { content:""; position:absolute; top:0; bottom:0; left:50%; width:3px; margin-left:-1.5px; background:var(--h3cs-line); }
.h3cs-gut.in::before { background:linear-gradient(var(--h3cs-continue) 0 28px, var(--h3cs-line) 28px); }
.h3cs-gut.out::before { background:linear-gradient(var(--h3cs-line) 0 28px, var(--h3cs-continue) 28px); }
.h3cs-gut.in.out::before, .h3cs-gut.continue::before, .h3cs-gut.transition::before { background:var(--h3cs-continue); }
.h3cs-gut.first::before { top:14px; }
.h3cs-gut.end::before { bottom:auto; height:22px; }
.h3cs-gut.cut::before, .h3cs-gut.new_scene::before { background:linear-gradient(var(--h3cs-line) 0 calc(50% - 7px),
  transparent calc(50% - 7px) calc(50% + 7px), var(--h3cs-line) calc(50% + 7px)); }
.h3cs-gut i { position:absolute; top:50%; left:50%; height:3px; width:22px; margin:-1.5px 0 0 -11px; background:var(--h3cs-cut); }
.h3cs-gut.new_scene i { background:var(--h3cs-scene); box-shadow:0 -6px 0 var(--h3cs-scene); margin-top:1.5px; }
.h3cs-num { position:relative; z-index:1; margin-top:12px; width:28px; height:28px; border-radius:50%; background:#15171c;
  border:2px solid var(--h3cs-line); display:grid; place-items:center; font-weight:800; font-size:14px; line-height:1; }
.h3cs-clip.selected .h3cs-num { background:var(--h3cs-ink); color:#15171c; border-color:var(--h3cs-ink); }
.h3cs-card { border:1px solid transparent; border-radius:8px; padding:10px 12px; display:grid;
  grid-template-columns:168px minmax(0,1fr); gap:14px; }
.h3cs-clip.selected .h3cs-card { border-color:var(--h3cs-line); background:var(--h3cs-panel); }
.h3cs-thumb { position:relative; width:168px; aspect-ratio:16/9; border-radius:3px; overflow:hidden; padding:0; display:block;
  border:1px dashed var(--h3cs-faint); cursor:pointer;
  background:repeating-linear-gradient(135deg, #2e3034 0 7px, #242528 7px 14px); }
.h3cs-thumb.has { border:1px solid var(--h3cs-line); background:#000; }
.h3cs-thumb.old img { filter:grayscale(1) brightness(.6); }
.h3cs-thumb img { width:100%; height:100%; object-fit:cover; display:block; }
.h3cs-stage { font-size:13px; margin-top:6px; color:var(--h3cs-dim); }
.h3cs-stage.todo { color:var(--h3cs-continue); font-weight:600; }
.h3cs-part-label { display:block; font-size:12px; color:var(--h3cs-faint); margin:8px 0 4px; }
.h3cs-part-label:first-child { margin-top:0; }
.h3cs-prompt { width:100%; background:none; border:1px solid transparent; border-radius:6px; padding:4px 6px; margin:0 -6px;
  resize:none; overflow:hidden; display:block; color:inherit; font:15px/1.5 inherit; font-family:inherit; }
.h3cs-prompt:hover { border-color:var(--h3cs-line); }
.h3cs-prompt:focus { border-color:var(--h3cs-faint); background:#15171c; outline:0; }
.h3cs-facts { display:none; flex-wrap:wrap; gap:6px 14px; align-items:center; margin-top:10px; font-size:13px; color:var(--h3cs-dim); }
.h3cs-clip.selected .h3cs-facts { display:flex; }
.h3cs-facts b { color:var(--h3cs-ink); font-weight:600; }
.h3cs-join { justify-self:start; background:none; border:1px solid transparent; border-radius:6px; padding:5px 10px; margin:2px 0;
  color:var(--h3cs-dim); text-align:left; cursor:pointer; font:inherit; }
.h3cs-join:hover, .h3cs-join[aria-expanded="true"] { border-color:var(--h3cs-line); color:var(--h3cs-ink); }
.h3cs-join b { font-weight:650; }
.h3cs-join.continue b, .h3cs-join.transition b { color:var(--h3cs-continue); }
.h3cs-join.new_scene b { color:var(--h3cs-scene); }
.h3cs-join .move { color:var(--h3cs-bridge); }
.h3cs-join small { font-size:12px; color:var(--h3cs-faint); margin-left:8px; }
.h3cs-scene { font-weight:750; font-size:19px; color:var(--h3cs-scene); margin:10px 0 0; padding-left:10px; }
.h3cs-problem { color:var(--h3cs-problem); font-size:13px; margin:0 0 6px 10px; }
.h3cs-options { border:1px solid var(--h3cs-line); border-radius:8px; background:var(--h3cs-panel); padding:12px; margin:0 0 6px; max-width:640px; }
.h3cs-option { display:block; width:100%; text-align:left; background:#15171c; border:1px solid var(--h3cs-line); border-radius:8px;
  padding:9px 12px; margin-bottom:6px; color:inherit; font:inherit; cursor:pointer; }
.h3cs-option b { display:block; font-weight:650; }
.h3cs-option span { color:var(--h3cs-dim); font-size:13px; line-height:1.4; display:block; }
.h3cs-option[aria-checked="true"] { box-shadow:inset 3px 0 0 var(--h3cs-oc); border-color:var(--h3cs-oc); }
.h3cs-option.continue { --h3cs-oc:var(--h3cs-continue); } .h3cs-option.cut { --h3cs-oc:var(--h3cs-cut); }
.h3cs-option.new_scene { --h3cs-oc:var(--h3cs-scene); }
.h3cs-option:disabled { opacity:.5; cursor:default; }
.h3cs-next { padding:14px 12px 0; }
.h3cs-next h3 { margin:0 0 10px; font-weight:750; font-size:21px; }
.h3cs-next-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:8px; max-width:720px; }
.h3cs-next-grid .h3cs-option { margin:0; background:var(--h3cs-panel); border-top:3px solid var(--h3cs-oc); }
.h3cs-note { color:var(--h3cs-dim); font-size:13px; margin:8px 0 0; }
.h3cs-script :focus-visible { outline:2px solid var(--h3cs-ink); outline-offset:2px; }
`;

function ensureStyle() {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = CSS;
  document.head.append(style);
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function button(className, onClick) {
  const node = el('button', className);
  node.type = 'button';
  node.addEventListener('click', (event) => {
    event.preventDefault();
    onClick();
  });
  return node;
}

// How far a clip has come: 'draft' has nothing written, 'ready' has never rendered, 'rendered' plays its take, and
// 'outdated' changed after its take (the take still plays in the full video).
export function clipStage(state, index, status) {
  if (status?.status === 'done') return 'rendered';
  if (status?.status === 'outdated') return 'outdated';
  return `${state.boxes[index].prompt}${state.prompt ?? ''}`.trim() ? 'ready' : 'draft';
}

const STAGE_TEXT = {draft: 'Not written yet', ready: 'Not rendered', rendered: 'Rendered', outdated: 'Out of date'};
const MEMORY_TEXT = {scene: 'remembering the scene', selected: 'remembering moments you pinned', cast: 'remembering the Cast'};

// The three ways a clip can start, in the words "What happens next?" uses for them.
export const STARTS = [
  {kind: 'continue', title: 'It keeps going', change: 'Keep it going',
    next: (n) => `Clip ${n + 1} picks up exactly where clip ${n} ends.`,
    what: (n, context) => `Motion and sound carry on. H3 is given the last ${context} frames of clip ${n} and carries on from them.`},
  {kind: 'cut', title: 'Cut to a new angle', change: 'Cut to a new angle',
    next: () => 'The same moment and place, seen from somewhere else.',
    what: () => 'The same moment from somewhere else. No frames are carried.'},
  {kind: 'new_scene', title: 'Go somewhere new', change: 'Go somewhere new',
    next: () => 'A new place, time or look.',
    what: () => 'A new place, time or look. The prompt describes it from scratch.'},
];

// Why clip `index` cannot continue the clip before it, or '' when it can.
export function continueBlocked(state, index) {
  const before = state.boxes[index - 1];
  if (!before) return '';
  if (before.layers?.length) return `Clip ${index} has several videos, and the clip after it can't continue yet.`;
  if (model.droppedFrames(state, index - 1)) return `Clip ${index} drops frames at its end, so nothing can continue from its last one.`;
  return '';
}

// The line between clip `index` and the one before it: its kind, and the sentence parts the Script prints.
export function joinLine(state, index) {
  const box = state.boxes[index], kind = model.joinKind(box);
  const memory = kind === 'cut' || kind === 'new_scene' ? MEMORY_TEXT[box.memory] ?? '' : '';
  const lead = {continue: 'Continues', transition: 'Transitions', cut: 'Cuts', new_scene: 'New scene'}[kind];
  const rest = {continue: ` from clip ${index}`, transition: ` in from clip ${index}`, cut: ' to a new angle', new_scene: ''}[kind]
    + (memory ? `, ${memory}` : '');
  const bridge = model.bridgeOf(state, index);
  const problem = kind === 'continue' || kind === 'transition' ? continueBlocked(state, index) : '';
  return {kind, lead, rest, move: bridge ? `with a ${model.seconds(bridge.frames)} s generated move` : '', problem};
}

// The parts of a clip's prompt the Script edits in place: each [Shot N] of a complete H3 prompt (and the style text
// before the first one), or the whole text of any other prompt. `write(n, value)` returns the new prompt and changes
// nothing else in it.
export function promptParts(prompt) {
  const {sections, shots} = promptShots(prompt);
  if (!sections) return {parts: [{label: '', value: prompt}], write: (n, value) => value};
  const scene = sections.find((section) => ['detailed_description', 'integrated_multimodal_description'].includes(section.key));
  const fields = scene.fields;
  const numbered = shots.length;
  const parts = fields.map((field) => ({field,
    label: /^\[Shot \d+\]$/i.test(field.label) ? (numbered > 1 ? `Shot ${field.label.match(/\d+/)[0]}` : '') : 'Style and scene',
    value: field.value}));
  return {parts, write: (n, value) => {
    parts[n].field.value = value;
    return writePromptSections(prompt, sections);
  }};
}

// Adds a clip that starts as `kind` after the last one and returns its index. A clip that cannot continue starts
// with a cut instead.
export function addNext(state, kind, context) {
  const index = model.addBox(state, context);
  if (index === 0) return index;
  const start = kind === 'continue' && (continueBlocked(state, index) || continueAfterStack(state, index - 1)) ? 'cut' : kind;
  if (start !== 'continue') model.setJoin(state, index, start, '', context);
  return index;
}

const PLACEHOLDER = {first: 'What do we see and hear? Describe the place, who is there and what happens.',
  continue: 'The same moment keeps going. What happens next?', transition: 'The scene changes as we watch. What happens?',
  cut: 'A new angle on the same moment. What do we see now?', new_scene: 'Somewhere or some time new. Describe the place first.'};

export class ScriptView {
  // `editor` is the Timeline editor; `more(index)` opens the classic panels on a clip.
  constructor({more} = {}) {
    ensureStyle();
    this.editor = null;
    this.more = more ?? (() => {});
    this.openJoin = null;
    this.signature = null;
    this.rows = [];
    this.root = el('section', 'h3cs-script');
    this.root.setAttribute('aria-label', 'Script');
    this.list = el('div', 'h3cs-list');
    this.root.append(this.list);
  }

  setEditor(editor) {
    this.editor = editor;
    this.openJoin = null;
    this.signature = null;
    this.render();
  }

  get locked() {
    return !!this.editor?.readOnly?.length;
  }

  context() {
    return this.editor.host.context();
  }

  // Everything that decides which rows exist. A change here rebuilds the list; anything else only updates it.
  shape() {
    const {state} = this.editor;
    return JSON.stringify([this.locked, this.openJoin, state.boxes.map((box, index) => {
      const status = this.editor.statusOf(box);
      return [box.id, box.frames, box.seed, model.joinKind(box), box.memory, clipStage(state, index, status),
        status?.thumb?.filename ?? '', status?.thumb?.v ?? '', promptParts(box.prompt).parts.map((part) => part.label),
        index ? joinLine(state, index) : null];
    })]);
  }

  render() {
    if (!this.editor) return;
    const shape = this.shape();
    if (shape !== this.signature) this.build(shape);
    this.sync();
  }

  // Selection and text the user is not typing in follow the Timeline without rebuilding a row.
  sync() {
    const {state, selected} = this.editor;
    this.rows.forEach((row, index) => {
      row.root.classList.toggle('selected', index === selected);
      const box = state.boxes[index];
      if (!box) return;
      const parts = promptParts(box.prompt).parts;
      row.areas.forEach((area, n) => {
        if (area !== document.activeElement && parts[n] && area.value !== parts[n].value) {
          area.value = parts[n].value;
          this.fit(area);
        }
      });
    });
  }

  fit(area) {
    if (!area.style || !('scrollHeight' in area)) return;
    area.style.height = 'auto';
    area.style.height = `${area.scrollHeight + 2}px`;
  }

  build(shape) {
    const active = document.activeElement, key = active?.dataset?.h3csKey;
    const caret = key != null && typeof active.selectionStart === 'number' ? active.selectionStart : null;
    this.signature = shape;
    this.rows = [];
    const {state} = this.editor, nodes = [];
    let scene = 1;
    state.boxes.forEach((box, index) => {
      if (index) {
        const line = joinLine(state, index);
        if (line.kind === 'new_scene') nodes.push(this.sceneRow(scene += 1));
        nodes.push(this.joinRow(index, line));
      }
      nodes.push(this.clipRow(box, index));
    });
    nodes.push(this.nextRow());
    this.list.replaceChildren(...nodes);
    for (const row of this.rows) row.areas.forEach((area) => this.fit(area));
    if (key != null) {
      const again = this.rows.flatMap((row) => row.areas).find((area) => area.dataset.h3csKey === key);
      again?.focus?.({preventScroll: true});
      if (again && caret != null) again.setSelectionRange?.(caret, caret);
    }
  }

  choose(index) {
    if (this.editor.selected !== index) this.editor.select(index);
    this.sync();
  }

  clipRow(box, index) {
    const {state} = this.editor, status = this.editor.statusOf(box);
    const stage = clipStage(state, index, status), next = state.boxes[index + 1];
    const root = el('article', 'h3cs-row h3cs-clip');
    const gut = el('span', `h3cs-gut${index ? '' : ' first'}`);
    if (index && ['continue', 'transition'].includes(model.joinKind(box))) gut.classList.add('in');
    if (next && ['continue', 'transition'].includes(model.joinKind(next))) gut.classList.add('out');
    gut.append(el('span', 'h3cs-num', String(index + 1)));

    const thumb = button(`h3cs-thumb${status?.thumb ? ' has' : ''}${stage === 'outdated' ? ' old' : ''}`, () => this.choose(index));
    thumb.setAttribute('aria-label', `Show clip ${index + 1}`);
    if (status?.thumb) {
      const image = el('img');
      image.alt = '';
      image.src = this.editor.host.viewUrl(status.thumb);
      thumb.append(image);
    }
    const stageEl = el('div', `h3cs-stage${stage === 'outdated' ? ' todo' : ''}`, STAGE_TEXT[stage]);
    if (stage === 'outdated' && status.reason) stageEl.title = status.reason;
    const left = el('div');
    left.append(thumb, stageEl);

    const right = el('div'), areas = [];
    const edit = promptParts(box.prompt);
    edit.parts.forEach((part, n) => {
      if (part.label) right.append(el('span', 'h3cs-part-label', part.label));
      const area = el('textarea', 'h3cs-prompt');
      area.rows = 2;
      area.value = part.value;
      area.readOnly = this.locked;
      area.dataset.h3csKey = `${box.id}:${n}`;
      area.placeholder = n ? 'What happens in this shot?' : PLACEHOLDER[index ? model.joinKind(box) : 'first'];
      area.setAttribute('aria-label', `Clip ${index + 1}${part.label ? `, ${part.label}` : ''}`);
      area.addEventListener('focus', () => this.choose(index));
      area.addEventListener('input', () => {
        if (state.boxes[index] !== box) return;
        box.prompt = edit.write(n, area.value);
        this.fit(area);
        this.editor.typed();
        // A first word makes the clip ready to render, and the row says so.
        if (this.shape() !== this.signature) this.render();
      });
      areas.push(area);
      right.append(area);
    });
    const facts = el('div', 'h3cs-facts');
    const length = el('span'), seed = el('span');
    length.append(el('b', null, `${model.seconds(box.frames)} s`), ` ${box.frames} frames`);
    seed.append('seed ', el('b', null, String(box.seed)));
    const more = button('h3ct-button', () => { this.choose(index); this.more(index); });
    more.textContent = 'All settings';
    more.title = 'Open this clip in the Legacy view, where its length, seed, frames and takes are';
    facts.append(length, seed, more);
    right.append(facts);

    const card = el('div', 'h3cs-card');
    card.append(left, right);
    root.append(gut, card);
    this.rows.push({root, areas});
    return root;
  }

  sceneRow(number) {
    const row = el('div', 'h3cs-row');
    row.append(el('span', 'h3cs-gut'), el('div', 'h3cs-scene', `Scene ${number}`));
    return row;
  }

  joinRow(index, line) {
    const open = this.openJoin === index;
    const row = el('div', 'h3cs-row');
    const gut = el('span', `h3cs-gut ${line.kind}`);
    if (line.kind === 'cut' || line.kind === 'new_scene') gut.append(el('i'));
    const body = el('div');
    const toggle = button(`h3cs-join ${line.kind}`, () => {
      this.openJoin = open ? null : index;
      this.render();
    });
    toggle.setAttribute('aria-expanded', String(open));
    toggle.append(el('b', null, line.lead), line.rest);
    if (line.move) toggle.append(' ', el('span', 'move', line.move));
    if (!open && !this.locked) toggle.append(el('small', null, 'Change'));
    toggle.disabled = this.locked;
    body.append(toggle);
    if (line.problem) body.append(el('p', 'h3cs-problem', `${line.problem} Change how clip ${index + 1} starts.`));
    if (open) body.append(this.joinOptions(index, line));
    row.append(gut, body);
    return row;
  }

  joinOptions(index, line) {
    const {state} = this.editor, box = state.boxes[index];
    const panel = el('div', 'h3cs-options');
    panel.setAttribute('role', 'radiogroup');
    panel.setAttribute('aria-label', `How clip ${index + 1} starts`);
    const blocked = continueBlocked(state, index);
    for (const start of STARTS) {
      const off = start.kind === 'continue' && blocked;
      const option = button(`h3cs-option ${start.kind}`, () => {
        if (model.joinKind(box) !== start.kind) {
          model.setJoin(state, index, start.kind, box.join?.note, this.context());
          this.editor.commit();
        }
        this.openJoin = null;
        this.render();
      });
      option.setAttribute('role', 'radio');
      option.setAttribute('aria-checked', String(line.kind === start.kind || (line.kind === 'transition' && start.kind === 'continue')));
      option.disabled = !!off;
      option.append(el('b', null, start.change), el('span', null, off || start.what(index, this.context())));
      panel.append(option);
    }
    const status = this.editor.statusOf(box);
    if (status?.status === 'done' || status?.status === 'outdated')
      panel.append(el('p', 'h3cs-note', `Changing how clip ${index + 1} starts means it renders again.`));
    panel.append(el('p', 'h3cs-note', 'What a cut remembers, and a generated move across it, are in the Legacy view for now.'));
    return panel;
  }

  nextRow() {
    const {state} = this.editor, count = state.boxes.length;
    const row = el('div', 'h3cs-row');
    const body = el('div', 'h3cs-next');
    body.append(el('h3', null, count ? 'What happens next?' : 'Start with the first clip'));
    const grid = el('div', 'h3cs-next-grid');
    const add = (kind) => {
      const index = addNext(state, kind, this.context());
      this.editor.selected = index;
      this.editor.commit();
      this.editor.inspectClip?.();
      this.render();
      const area = this.rows[index]?.areas[0];
      area?.focus?.();
      area?.scrollIntoView?.({block: 'nearest'});
    };
    if (!count) {
      const first = button('h3cs-option continue', () => add('continue'));
      first.append(el('b', null, 'Write the first clip'), el('span', null, 'Describe what we see and hear. Plain sentences work.'));
      first.disabled = this.locked;
      grid.append(first);
    } else for (const start of STARTS) {
      const option = button(`h3cs-option ${start.kind}`, () => add(start.kind));
      const blocked = start.kind === 'continue' && (state.boxes[count - 1].layers?.length || model.droppedFrames(state, count - 1));
      option.append(el('b', null, start.title),
        el('span', null, blocked ? `Not after clip ${count}: nothing can continue from it.` : start.next(count)));
      option.disabled = this.locked || !!blocked;
      grid.append(option);
    }
    body.append(grid);
    // With no clip yet there is no line to hang this on.
    if (!count) return body;
    row.append(el('span', 'h3cs-gut end'), body);
    return row;
  }
}
