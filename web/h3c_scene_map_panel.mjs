// The Studio's scene map: the clip panel's Scene map section and the map page in the centre. Edits go through
// h3c_scene_maps.mjs, so a clip that continues another keeps sharing its map; the timeline editor commits them.
import * as maps from './h3c_scene_maps.mjs?v=bcaf35949d73';
import {SceneMapEditor, el, inputFile} from './h3c_scene_map_editor.mjs?v=2cf054593719';
import {drawLayout} from './h3c_scene_map_draw.mjs?v=7143aaa9f4a0';
import {parseLayout} from './h3c_scene_map_model.mjs?v=e7a88f4152e0';
import {SwitchSection} from './h3c_switch_section.mjs?v=c253500f4908';

const MARKER_LOOK = ['label', 'icon', 'color', 'size', 'legend', 'text'];
const CAMERA_LOOK = ['fov', 'height', 'label', 'color'];
const PLACE = ['x', 'y', 'tx', 'ty'];
const PREVIEW_URL = '/h3c/scene-map/preview';
const STYLE_ID = 'h3csm-panel-style';
const STYLE = `
.h3csm-preview{width:100%;aspect-ratio:16/9;display:block;background:#141416;border-radius:4px}
.h3csm-prompt pre{margin:4px 0 0;white-space:pre-wrap;font:11px/1.4 ui-monospace,monospace;color:#c6cbd4}
.h3csm-page{height:100%;min-height:560px;gap:8px}
.h3csm-page-head{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.h3csm-page-head button.on{background:#3d5a80;border-color:#6d9bd1}
.h3csm-holder{flex:1;min-height:0;display:flex;flex-direction:column}
`;

const pick = (value, keys) => Object.fromEntries(keys.map(key => [key, value[key]]));

// What the clip panel shows: whether the map is on, which clip it continues (as numbered in the Studio), and whether
// the map picture can go to the video, from the server's preview of this clip.
export function panelState(state, index, preview) {
  const box = state.boxes[index], source = maps.source(state, index);
  const video = preview?.video ?? {}, reason = video.reason ?? '';
  const sendVisible = video.mode === 'ref2va';
  return {on: !!box?.scene_map?.on, linkedTo: source === null ? null : source + 1, sendVisible,
    canSendPicture: sendVisible && !reason, sendReason: reason, multiShot: /\[Shot 2\]/.test(box?.prompt ?? '')};
}

// Applies what the editor changed in box `index`'s `phase` layout; true when the state changed.
export function applyLayout(state, index, phase, layout) {
  const shown = maps.layoutFor(state, index, phase);
  if (!shown) return false;
  const resolved = maps.resolve(state, index), was = parseLayout(shown), now = parseLayout(layout);
  let changed = false;
  const shared = {};
  if (now.width !== was.width || now.height !== was.height) Object.assign(shared, {width: now.width, height: now.height});
  if (now.scale !== was.scale) shared.scale = now.scale;
  if (now.legend.show !== was.legend.show || now.legend.position !== was.legend.position) shared.legend = {...now.legend};
  const look = was.camera ?? resolved.look;
  if (now.camera && CAMERA_LOOK.some(key => now.camera[key] !== look[key])) shared.camera = pick(now.camera, CAMERA_LOOK);
  if (Object.keys(shared).length) { maps.setShared(state, index, shared); changed = true; }
  if (!now.camera && was.camera) { maps.move(state, index, phase, {kind: 'camera'}, null); changed = true; }
  else if (now.camera && (!was.camera || PLACE.some(key => now.camera[key] !== was.camera[key]))) {
    maps.move(state, index, phase, {kind: 'camera'}, pick(now.camera, PLACE));
    changed = true;
  }
  const before = new Map(was.markers.map(marker => [marker.id, marker])), kept = new Set(now.markers.map(marker => marker.id));
  for (const marker of was.markers) {
    if (kept.has(marker.id)) continue;
    if (resolved.owners[marker.id] === index) maps.removeMarker(state, index, marker.id);
    else maps.setAbsent(state, index, marker.id, true);
    changed = true;
  }
  for (const marker of now.markers) {
    const prior = before.get(marker.id);
    if (!prior) {
      maps.addMarker(state, index, pick(marker, MARKER_LOOK), {x: marker.x, y: marker.y});
      changed = true;
      continue;
    }
    const patch = Object.fromEntries(MARKER_LOOK.filter(key => marker[key] !== prior[key]).map(key => [key, marker[key]]));
    if (Object.keys(patch).length) { maps.setLook(state, index, marker.id, patch); changed = true; }
    if (marker.x !== prior.x || marker.y !== prior.y) {
      maps.move(state, index, phase, {kind: 'marker', id: marker.id}, {x: marker.x, y: marker.y});
      changed = true;
    }
  }
  return changed;
}

// The editor's name for a map picture in the input folder (subfolder/name.png), or '' for none.
export function pictureName(picture) {
  if (!picture || picture.type !== 'input') return '';
  return picture.subfolder ? `${picture.subfolder}/${picture.filename}` : picture.filename;
}

// The "Added to the prompt" text for a preview from the server.
export function promptText(preview) {
  const video = preview?.video ?? {}, parts = video.parts;
  const lines = parts ? [parts.definition, parts.retention, parts.blocking].filter(Boolean) : [];
  const blocks = [['Video', ...(lines.length ? lines : [`Nothing: ${video.reason || 'the map is off.'}`]),
    ...(lines.length && video.reason ? [`(${video.reason})`] : [])].join('\n')];
  const stills = preview?.stills ?? {};
  if (stills.first) blocks.push(`First-frame still\n${stills.first}`);
  if (stills.last) blocks.push(`Last-frame still\n${stills.last}`);
  return blocks.join('\n\n');
}

function injectStyle() {
  if (document.getElementById(STYLE_ID)) return;
  document.head.append(el('style', {id: STYLE_ID, textContent: STYLE}));
}

function viewUrl(api, file) {
  return api.apiURL(`/view?filename=${encodeURIComponent(file.filename)}&type=${file.type}&subfolder=${encodeURIComponent(file.subfolder ?? '')}`);
}

// The clip panel's Scene map section. `editor` is the TimelineEditor; render() follows its selected clip.
export class SceneMapSection {
  constructor(editor) {
    injectStyle();
    this.editor = editor;
    this.preview = null;
    this.block = new SwitchSection('Scene map', {onToggle: on => {
      if (editor.readOnly.length) return;
      if (on) maps.enable(editor.state, editor.selected);
      else maps.disable(editor.state, editor.selected);
      editor.commit();
    }});
    this.root = this.block.root;
    this.canvas = el('canvas', {className: 'h3csm-preview', width: 320, height: 180});
    this.editButton = el('button', {type: 'button', textContent: 'Edit map', title: 'Open the map in the centre'});
    // A focused control keeps its SwitchSection on, so the button lets go before the next clip's switch is drawn.
    this.editButton.addEventListener('click', () => { this.editButton.blur(); editor.host.openSceneMap?.(); });
    this.sendInput = el('input', {type: 'checkbox'});
    this.sendInput.addEventListener('change', () => {
      const map = editor.box()?.scene_map;
      if (!map || editor.readOnly.length) return;
      map.video_picture = this.sendInput.checked;
      editor.commit();
    });
    this.sendField = el('label', {className: 'h3ct-check'}, this.sendInput, ' Send map picture to video');
    this.sendNote = el('p', {className: 'h3ct-hint'});
    this.shotNote = el('p', {className: 'h3ct-hint', textContent: 'The map applies to the first shot only.'});
    this.stillNote = el('p', {className: 'h3ct-hint', textContent: 'Only the MiniMax still recipe uses the map.'});
    this.promptEl = el('pre');
    this.promptDetails = el('details', {className: 'h3csm-prompt'}, el('summary', {textContent: 'Added to the prompt'}), this.promptEl);
    this.block.body.append(this.canvas, this.editButton, this.sendField, this.sendNote, this.shotNote, this.stillNote, this.promptDetails);
  }

  render() {
    const editor = this.editor, box = editor.box(), index = editor.selected, locked = editor.readOnly.length > 0;
    this.root.hidden = !box;
    if (!box) return;
    const key = `${box.id}\n${editor.host.read?.() ?? ''}`;
    const preview = this.preview?.key === key ? this.preview.value : null;
    const info = panelState(editor.state, index, preview);
    this.block.set(info.on, {disabled: locked, state: info.on && info.linkedTo ? `Continues clip ${info.linkedTo}` : ''});
    if (!info.on) return;
    this.drawPreview();
    this.editButton.disabled = false;
    this.sendField.hidden = !info.sendVisible;
    this.sendInput.checked = !!box.scene_map.video_picture;
    this.sendInput.disabled = locked || (!info.canSendPicture && !this.sendInput.checked);
    this.sendNote.textContent = info.sendReason;
    this.sendNote.hidden = !info.sendReason;
    this.shotNote.hidden = !info.multiShot;
    this.loadAdapter(box.id);
    this.stillNote.hidden = this.adapter?.box !== box.id || this.adapter.value === 'pixels';
    this.promptEl.textContent = preview ? promptText(preview) : this.preview?.error ?? 'Checking…';
    if (this.preview?.key !== key && this.pending !== key) this.fetchPreview(key, box.id);
  }

  fetchPreview(key, boxId) {
    this.pending = key;
    clearTimeout(this.timer);
    this.timer = setTimeout(async () => {
      const api = this.editor.host.api, text = key.slice(key.indexOf('\n') + 1);
      if (!api) return;
      let value = null, error = '';
      try {
        const response = await api.fetchApi(PREVIEW_URL, {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({timeline: text, box: boxId})});
        if (response.status === 404 || response.status === 405) error = 'Restart ComfyUI, then refresh this page, to see what the map adds.';
        else {
          const result = await response.json();
          if (result.ok) value = result;
          else error = result.error ?? `The preview failed (${response.status}).`;
        }
      } catch (failure) {
        error = `The preview failed: ${failure.message}`;
      }
      if (this.pending !== key) return;
      this.pending = null;
      this.preview = {key, value, error};
      if (!value) this.preview.value = null;
      this.render();
    }, 300);
  }

  async loadAdapter(boxId) {
    if (this.adapter?.box === boxId || this.adapterLoading === boxId || !this.editor.host.stillControls) return;
    this.adapterLoading = boxId;
    let value = null;
    try { value = (await this.editor.host.stillControls())?.adapter ?? null; } catch { value = null; }
    this.adapterLoading = null;
    this.adapter = {box: boxId, value};
    if (this.editor.box()?.id === boxId) this.render();
  }

  drawPreview() {
    const editor = this.editor, layout = maps.layoutFor(editor.state, editor.selected, 'opening');
    const ratio = globalThis.devicePixelRatio || 1, box = this.canvas.getBoundingClientRect?.();
    if (!layout || !box?.width) return;
    this.canvas.width = Math.round(box.width * ratio);
    this.canvas.height = Math.round(box.height * ratio);
    const ctx = this.canvas.getContext('2d'), parsed = parseLayout(layout);
    const width = parsed.width ?? 1600, height = parsed.height ?? 900;
    const scale = Math.min(this.canvas.width / width, this.canvas.height / height);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    ctx.translate((this.canvas.width - width * scale) / 2, (this.canvas.height - height * scale) / 2);
    ctx.scale(scale, scale);
    const picture = maps.resolve(editor.state, editor.selected).picture, api = editor.host.api;
    const url = picture && api ? viewUrl(api, picture) : null;
    if (url && this.picture?.url === url && this.picture.image.complete) ctx.drawImage(this.picture.image, 0, 0, width, height);
    else {
      ctx.fillStyle = '#26272b';
      ctx.fillRect(0, 0, width, height);
      if (url && this.picture?.url !== url) {
        const image = new Image();
        this.picture = {url, image};
        image.onload = () => { if (this.picture?.url === url) this.drawPreview(); };
        image.src = url;
      }
    }
    drawLayout(ctx, parsed, width, height, {editor: false});
  }
}

// The map page in the Studio's centre: Opening and End tabs over the editor for the selected clip.
export class SceneMapPage {
  constructor(root) {
    injectStyle();
    this.root = root;
    this.root.classList.add('h3csm-page');
    this.phase = 'opening';
    this.tabs = Object.fromEntries([['opening', 'Opening'], ['end', 'End']].map(([phase, text]) => {
      const tab = el('button', {type: 'button', textContent: text, title: `Where everything is at the clip’s ${text.toLowerCase()}`});
      tab.addEventListener('click', () => { this.phase = phase; this.refresh(this.timeline); });
      return [phase, tab];
    }));
    this.message = el('p', {className: 'h3cx-note'});
    this.absentRow = el('div', {className: 'h3csm-page-head'});
    this.head = el('div', {className: 'h3csm-page-head'}, ...Object.values(this.tabs));
    this.holder = el('div', {className: 'h3csm-holder'});
    this.root.append(this.head, this.absentRow, this.message, this.holder);
  }

  refresh(timeline) {
    this.timeline = timeline;
    const box = timeline?.box(), index = timeline?.selected, state = timeline?.state;
    const resolved = box ? maps.resolve(state, index) : null;
    this.head.hidden = this.holder.hidden = this.absentRow.hidden = !resolved;
    this.message.hidden = !!resolved;
    if (!resolved) {
      this.message.textContent = box ? 'Turn on Scene map in this clip’s settings to give it a map.' : 'No clip selected.';
      return;
    }
    if (this.shown?.split(':')[0] !== box.id) this.phase = 'opening';
    for (const [phase, tab] of Object.entries(this.tabs)) tab.classList.toggle('on', phase === this.phase);
    const other = this.phase === 'opening' ? 'end' : 'opening';
    const notice = this.phase === 'opening' && resolved.source !== null ? `Shared with clip ${resolved.source + 1}’s end` : '';
    const layout = resolved[this.phase], ghost = resolved[other], image = pictureName(resolved.picture);
    const locked = timeline.readOnly.length > 0;
    if (!this.editor) {
      this.editor = new SceneMapEditor({api: timeline.host.api, height: 0, layout, image, ghost, notice,
        onLayout: changed => this.changed(changed), onImage: name => this.picked(name),
        markerId: () => maps.nextMarkerId(this.timeline.state), decorate: (panel, marker) => this.decorate(panel, marker)});
      this.holder.append(this.editor.root);
    } else {
      this.editor.api = timeline.host.api;
      if (this.shown !== `${box.id}:${this.phase}`) this.editor.selected = null;
      this.editor.setLayout(layout, {ghost, notice, force: this.shown !== `${box.id}:${this.phase}`});
      if (this.editor.image !== image) this.editor.setImage(image);
    }
    this.shown = `${box.id}:${this.phase}`;
    this.editor.root.inert = locked;
    this.renderAbsent(state, index, resolved, locked);
  }

  renderAbsent(state, index, resolved, locked) {
    const absent = resolved.source === null ? [] : state.boxes[index].scene_map.absent;
    const previous = absent.length ? maps.layoutFor(state, resolved.source, 'end') : null;
    const items = absent.map(id => previous?.markers.find(marker => marker.id === id)).filter(Boolean);
    this.absentRow.replaceChildren(...(items.length ? [el('span', {className: 'h3csm-hint', textContent: 'Not in this clip:'}),
      ...items.map(marker => {
        const back = el('button', {type: 'button', textContent: `${marker.label || marker.id} · Bring back`, disabled: locked});
        back.addEventListener('click', () => this.edit(() => maps.setAbsent(state, index, marker.id, false)));
        return back;
      })] : []));
  }

  edit(change) {
    const timeline = this.timeline;
    if (!timeline || timeline.readOnly.length) return;
    if (change() !== false) timeline.commit();
  }

  changed(layout) {
    this.edit(() => applyLayout(this.timeline.state, this.timeline.selected, this.phase, layout));
  }

  picked(name) {
    this.edit(() => maps.setShared(this.timeline.state, this.timeline.selected, {picture: name ? inputFile(name) : null}));
  }

  decorate(panel, marker) {
    const timeline = this.timeline, state = timeline.state, index = timeline.selected;
    const resolved = maps.resolve(state, index);
    if (resolved.owners[marker.id] !== index) {
      const absent = el('button', {type: 'button', textContent: 'Not in this clip',
        title: 'Leave this marker out of this clip and the clips that continue it'});
      absent.addEventListener('click', () => this.edit(() => maps.setAbsent(state, index, marker.id, true)));
      panel.append(absent);
    }
    const entities = state.bible?.entities ?? [];
    if (!entities.length) return;
    const current = resolved.opening.markers.find(item => item.id === marker.id)?.entity ?? '';
    const select = el('select', {title: 'The Cast entry this marker stands for; the prompt then names it'},
      el('option', {value: '', textContent: '(not linked)'}),
      ...entities.map(entity => el('option', {value: entity.id, textContent: entity.name || entity.id})));
    select.value = current;
    select.addEventListener('change', () => this.edit(() => maps.setLook(state, index, marker.id, {entity: select.value})));
    panel.append(el('label', {}, 'Cast', select));
  }
}
