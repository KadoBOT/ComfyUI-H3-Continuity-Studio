// The scene map editor without a node: pick a map picture, place markers and the camera, and edit the legend. The
// H3 Scene Map node (h3c_scene_map.js) and the Studio's map page both build one and keep the layout themselves.
import {LEGEND_POSITIONS, PALETTE, addMarker, hitTest, iconNames, parseLayout, serializeLayout, placeCamera} from './h3c_scene_map_model.mjs?v=e7a88f4152e0';
import {badge, drawLayout} from './h3c_scene_map_draw.mjs?v=7143aaa9f4a0';

export const HEIGHT = 640;
const MODES = [['move', 'Move', 'Drag markers, the camera arrow or its aim ring'], ['marker', 'Add marker', 'Click the map to add a marker'],
  ['camera', 'Place camera', 'Press where the camera stands and drag towards where it looks']];
const STYLE = `
.h3csm{box-sizing:border-box;display:flex;flex-direction:column;gap:6px;padding:4px;font:12px/1.3 system-ui,sans-serif;color:#ddd}
.h3csm *{box-sizing:border-box}
.h3csm-row{display:flex;flex-wrap:wrap;gap:4px;align-items:center}
.h3csm button,.h3csm select,.h3csm input{font:inherit;color:#eee;background:#2a2b2f;border:1px solid #44464c;border-radius:4px;padding:2px 6px;min-height:24px}
.h3csm button:hover{background:#34363b}
.h3csm button.on{background:#3d5a80;border-color:#6d9bd1}
.h3csm-icon{padding:1px!important;width:28px;height:28px;display:inline-flex;align-items:center;justify-content:center}
.h3csm-swatch{width:22px;height:22px;padding:0!important;border-radius:50%!important}
.h3csm-swatch.on{outline:2px solid #ffd23f;outline-offset:1px}
.h3csm-stage{flex:1;min-height:200px;position:relative;background:#141416;border-radius:4px;overflow:hidden}
.h3csm-stage canvas{width:100%;height:100%;display:block;outline:none;touch-action:none}
.h3csm-panel{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;min-height:30px}
.h3csm-panel label{display:inline-flex;gap:4px;align-items:center}
.h3csm-hint{color:#999;font-size:11px}
.h3csm-notice{color:#e8c872;font-size:11px}
.h3csm-notice:empty{display:none}
.h3csm select.h3csm-image{max-width:260px}
`;

export function el(tag, props = {}, ...children) {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children.filter(child => child != null));
  return node;
}

export function inputFile(value) {
  const parts = String(value).split('/');
  return {filename: parts.pop(), subfolder: parts.join('/'), type: 'input'};
}

// options: {layout, image, onLayout(layout), onImage(name), linked() -> bool, background, ghost, notice, height,
// decorate(panel, marker), markerId() -> string, api}. `image` is a name in ComfyUI's input folder (subfolder/name.png);
// `background` is a file shown instead while linked() is true; `ghost` is a layout drawn faintly under the live one;
// `height` 0 fills the parent.
export class SceneMapEditor {
  constructor(options) {
    this.options = options;
    this.api = options.api;
    this.layout = parseLayout(options.layout);
    this.last = serializeLayout(this.layout);
    this.image = options.image ?? '';
    this.background = options.background ?? null;
    this.ghost = options.ghost ? parseLayout(options.ghost) : null;
    this.selected = null;
    this.mode = 'move';
    this.icon = 'dot';
    this.color = PALETTE[0];
    this.picture = null;
    this.pictureUrl = null;
    this.build();
    const height = options.height ?? HEIGHT;
    this.root.style.height = height ? `${height}px` : '100%';
    this.notice.textContent = options.notice ?? '';
    if (typeof ResizeObserver === 'function') {
      this.observer = new ResizeObserver(() => this.draw());
      this.observer.observe(this.stage);
    }
    this.loadImages();
    this.loadPicture();
    this.renderPanel();
  }

  // --- building -------------------------------------------------------------------------------------------------

  build() {
    if (!document.getElementById('h3csm-style')) document.head.append(el('style', {id: 'h3csm-style', textContent: STYLE}));
    this.imageSelect = el('select', {className: 'h3csm-image', title: 'Map picture from the input folder'});
    this.imageSelect.addEventListener('change', () => this.chooseImage(this.imageSelect.value));
    this.fileInput = el('input', {type: 'file', accept: 'image/*', hidden: true});
    this.fileInput.addEventListener('change', () => this.upload(this.fileInput.files?.[0]));
    const upload = el('button', {textContent: 'Upload…', title: 'Upload a map picture to the input folder'});
    upload.addEventListener('click', () => this.fileInput.click());
    this.sourceNote = el('span', {className: 'h3csm-hint'});
    const pictureRow = el('div', {className: 'h3csm-row'}, el('span', {textContent: 'Map'}), this.imageSelect, upload, this.fileInput, this.sourceNote);

    this.modeButtons = MODES.map(([mode, text, title]) => {
      const button = el('button', {textContent: text, title});
      button.addEventListener('click', () => { this.mode = mode; this.renderTools(); });
      return button;
    });
    this.iconButtons = iconNames().map(({key, name}) => {
      const canvas = el('canvas', {width: 48, height: 48});
      canvas.style.cssText = 'width:24px;height:24px';
      const button = el('button', {className: 'h3csm-icon', title: name}, canvas);
      button.dataset.icon = key;
      button.addEventListener('click', () => this.chooseIcon(key));
      return button;
    });
    this.swatches = PALETTE.map(color => {
      const button = el('button', {className: 'h3csm-swatch', title: color});
      button.style.background = color;
      button.dataset.color = color;
      button.addEventListener('click', () => this.chooseColor(color));
      return button;
    });
    this.colorInput = el('input', {type: 'color', title: 'Other color', value: this.color});
    this.colorInput.style.cssText = 'width:30px;padding:0';
    this.colorInput.addEventListener('input', () => this.chooseColor(this.colorInput.value));
    const toolRow = el('div', {className: 'h3csm-row'}, ...this.modeButtons);
    const iconRow = el('div', {className: 'h3csm-row'}, ...this.iconButtons);
    const colorRow = el('div', {className: 'h3csm-row'}, ...this.swatches, this.colorInput);

    this.notice = el('div', {className: 'h3csm-notice'});
    this.canvas = el('canvas', {tabIndex: 0});
    this.stage = el('div', {className: 'h3csm-stage'}, this.canvas);
    this.canvas.addEventListener('pointerdown', event => this.pointerDown(event));
    this.canvas.addEventListener('pointermove', event => this.pointerMove(event));
    this.canvas.addEventListener('pointerup', event => this.pointerUp(event));
    this.canvas.addEventListener('pointercancel', event => this.pointerUp(event));
    this.canvas.addEventListener('keydown', event => this.keyDown(event));

    this.panel = el('div', {className: 'h3csm-panel'});
    this.legendShow = el('input', {type: 'checkbox'});
    this.legendShow.addEventListener('change', () => { this.layout.legend.show = this.legendShow.checked; this.commit(); });
    this.legendPosition = el('select', {}, ...LEGEND_POSITIONS.map(value => el('option', {value, textContent: value.replace('-', ' ')})));
    this.legendPosition.addEventListener('change', () => { this.layout.legend.position = this.legendPosition.value; this.commit(); });
    this.scaleInput = el('input', {type: 'range', min: 0.5, max: 2.5, step: 0.05, title: 'Size of every marker, label and the legend'});
    this.scaleInput.addEventListener('input', () => { this.layout.scale = Number(this.scaleInput.value); this.commit(); });
    const legendRow = el('div', {className: 'h3csm-row'},
      el('label', {}, this.legendShow, 'Legend'), this.legendPosition, el('label', {}, 'Size', this.scaleInput));
    const hint = el('div', {className: 'h3csm-hint', textContent:
      'The arrow is the camera: its tip is the lens. The dashed view cone and aim ring are only shown here, never drawn into the map. '
      + 'Delete removes the selection.'});
    this.root = el('div', {className: 'h3csm'}, pictureRow, toolRow, iconRow, colorRow, this.notice, this.stage, this.panel, legendRow, hint);
    this.renderTools();
  }

  // --- state ----------------------------------------------------------------------------------------------------

  commit() {
    const value = serializeLayout(this.layout);
    if (value !== this.last) {
      this.last = value;
      this.options.onLayout?.(JSON.parse(value));
    }
    this.draw();
  }

  // Replaces the layout without reporting it back; a selected marker stays selected when it is still there.
  setLayout(layout, extra = {}) {
    const marker = this.selectedMarker();
    this.layout = parseLayout(layout);
    this.last = serializeLayout(this.layout);
    if ('ghost' in extra) this.ghost = extra.ghost ? parseLayout(extra.ghost) : null;
    if ('notice' in extra) this.notice.textContent = extra.notice ?? '';
    if (marker) {
      const index = this.layout.markers.findIndex(item => item.id === marker.id);
      this.selected = index >= 0 ? {kind: 'marker', index} : null;
    } else if (this.selected && !this.layout.camera) this.selected = null;
    this.renderPanel();
    this.renderTools();
    this.draw();
  }

  selectedMarker() {
    return this.selected?.kind === 'marker' ? this.layout.markers[this.selected.index] : null;
  }

  select(hit) {
    this.selected = hit;
    const marker = this.selectedMarker();
    if (marker) { this.icon = marker.icon; this.color = marker.color; }
    this.renderPanel();
    this.renderTools();
    this.draw();
  }

  chooseIcon(icon) {
    this.icon = icon;
    const marker = this.selectedMarker();
    if (marker) { marker.icon = icon; this.renderPanel(); this.commit(); }
    if (!marker && this.mode !== 'marker') this.mode = 'marker';
    this.renderTools();
  }

  chooseColor(color) {
    this.color = color;
    const marker = this.selectedMarker();
    if (marker) { marker.color = color; this.commit(); }
    this.renderTools();
  }

  removeSelected() {
    if (this.selected?.kind === 'marker') this.layout.markers.splice(this.selected.index, 1);
    else if (this.selected?.kind === 'camera' || this.selected?.kind === 'target') this.layout.camera = null;
    else return;
    this.select(null);
    this.commit();
  }

  // --- the map picture ------------------------------------------------------------------------------------------

  linked() {
    return Boolean(this.options.linked?.());
  }

  viewUrl(file) {
    const name = file.filename, subfolder = file.subfolder ?? '';
    return this.api.apiURL(`/view?filename=${encodeURIComponent(name)}&type=${file.type}&subfolder=${encodeURIComponent(subfolder)}`);
  }

  async loadImages() {
    let images = [];
    try { images = (await (await this.api.fetchApi('/h3c/scene-map/images')).json()).images ?? []; } catch { images = []; }
    const current = this.image;
    if (current && !images.includes(current)) images.unshift(current);
    this.imageSelect.replaceChildren(el('option', {value: '', textContent: images.length ? '(choose a picture)' : '(no pictures in input)'}),
      ...images.map(name => el('option', {value: name, textContent: name})));
    this.imageSelect.value = current;
  }

  // Shows a picture without reporting it back.
  setImage(name) {
    this.image = name ?? '';
    if (this.imageSelect.value !== this.image) this.imageSelect.value = this.image;
    this.loadPicture();
  }

  chooseImage(name) {
    this.options.onImage?.(name);
    this.setImage(name);
  }

  async upload(file) {
    if (!file) return;
    const body = new FormData();
    body.append('image', file);
    body.append('type', 'input');
    body.append('subfolder', 'maps');
    try {
      const response = await this.api.fetchApi('/upload/image', {method: 'POST', body});
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      const saved = await response.json();
      const name = saved.subfolder ? `${saved.subfolder}/${saved.name}` : saved.name;
      this.chooseImage(name);
      await this.loadImages();
    } catch (error) {
      this.sourceNote.textContent = `Upload failed: ${error.message}`;
    } finally {
      this.fileInput.value = '';
    }
  }

  loadPicture() {
    let file = null;
    const linked = this.linked();
    if (linked) {
      file = this.background;
      this.sourceNote.textContent = file ? 'Showing the connected background from the last run.' : 'Run the node once to show the connected background.';
    } else {
      file = this.image ? inputFile(this.image) : null;
      this.sourceNote.textContent = '';
    }
    this.imageSelect.disabled = linked;
    const url = file ? this.viewUrl(file) : null;
    if (url === this.pictureUrl) return this.draw();
    this.pictureUrl = url;
    this.picture = null;
    this.draw();
    if (!url) return;
    const picture = new Image();
    picture.onload = () => {
      if (this.pictureUrl !== url) return;
      this.picture = picture;
      // The Studio describes the camera from these before the node runs, so keep them with the layout.
      const width = file.width ?? picture.naturalWidth, height = file.height ?? picture.naturalHeight;
      if (this.layout.width !== width || this.layout.height !== height) {
        this.layout.width = width;
        this.layout.height = height;
        this.commit();
      } else this.draw();
    };
    picture.onerror = () => { if (this.pictureUrl === url) this.sourceNote.textContent = 'The map picture could not be loaded.'; };
    picture.src = url;
  }

  // --- drawing --------------------------------------------------------------------------------------------------

  size() {
    return {width: this.layout.width ?? this.picture?.naturalWidth ?? 1600, height: this.layout.height ?? this.picture?.naturalHeight ?? 900};
  }

  frame() {
    const {width, height} = this.size();
    const box = this.canvas.getBoundingClientRect();
    const scale = Math.min(box.width / width, box.height / height) || 1;
    return {width, height, scale, x: (box.width - width * scale) / 2, y: (box.height - height * scale) / 2, box};
  }

  draw() {
    const ratio = window.devicePixelRatio || 1, box = this.canvas.getBoundingClientRect();
    if (!box.width || !box.height) return;
    this.canvas.width = Math.round(box.width * ratio);
    this.canvas.height = Math.round(box.height * ratio);
    const ctx = this.canvas.getContext('2d');
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, box.width, box.height);
    const view = this.frame();
    ctx.save();
    ctx.translate(view.x, view.y);
    ctx.scale(view.scale, view.scale);
    if (this.picture) ctx.drawImage(this.picture, 0, 0, view.width, view.height);
    else {
      ctx.fillStyle = '#26272b';
      ctx.fillRect(0, 0, view.width, view.height);
    }
    if (this.ghost) {
      ctx.save();
      ctx.globalAlpha = 0.35;
      drawLayout(ctx, this.ghost, view.width, view.height, {editor: false});
      ctx.restore();
    }
    drawLayout(ctx, this.layout, view.width, view.height, {selected: this.selected});
    ctx.restore();
    if (!this.picture) {
      ctx.fillStyle = '#aaa';
      ctx.font = '13px system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(this.linked() ? 'Run once to show the connected background' : 'Choose or upload a map picture', box.width / 2, 22);
    }
  }

  renderTools() {
    this.modeButtons.forEach((button, index) => button.classList.toggle('on', MODES[index][0] === this.mode));
    for (const button of this.iconButtons) {
      button.classList.toggle('on', button.dataset.icon === this.icon);
      const ctx = button.firstChild.getContext('2d');
      ctx.clearRect(0, 0, 48, 48);
      badge(ctx, 24, 24, 19, button.dataset.icon, this.color, button.dataset.icon === 'text' ? 'A' : '');
    }
    for (const swatch of this.swatches) swatch.classList.toggle('on', swatch.dataset.color === this.color);
    this.colorInput.value = this.color;
    this.legendShow.checked = this.layout.legend.show;
    this.legendPosition.value = this.layout.legend.position;
    this.scaleInput.value = String(this.layout.scale);
    this.canvas.style.cursor = this.mode === 'move' ? 'default' : 'crosshair';
  }

  field(labelText, input, apply) {
    input.addEventListener(input.type === 'checkbox' ? 'change' : 'input', () => { apply(input); this.commit(); });
    return el('label', {}, labelText, input);
  }

  renderPanel() {
    const marker = this.selectedMarker(), camera = this.selected && this.selected.kind !== 'marker' ? this.layout.camera : null;
    const remove = el('button', {textContent: 'Delete'});
    remove.addEventListener('click', () => this.removeSelected());
    if (marker) {
      const label = el('input', {value: marker.label, placeholder: 'e.g. STRAY', maxLength: 60});
      label.style.width = '150px';
      const text = el('input', {value: marker.text, maxLength: 3, placeholder: '1'});
      text.style.width = '44px';
      const size = el('input', {type: 'range', min: 0.5, max: 2.5, step: 0.05, value: marker.size});
      const legend = el('input', {type: 'checkbox', checked: marker.legend});
      this.panel.replaceChildren(
        this.field('Label', label, input => { marker.label = input.value.trim().slice(0, 60); }),
        marker.icon === 'text' ? this.field('Text', text, input => { marker.text = input.value.trim().slice(0, 3); }) : null,
        this.field('Size', size, input => { marker.size = Number(input.value); }),
        this.field('In legend', legend, input => { marker.legend = input.checked; }), remove);
      this.options.decorate?.(this.panel, marker);
    } else if (camera) {
      const label = el('input', {value: camera.label, maxLength: 40});
      label.style.width = '110px';
      const fov = el('input', {type: 'number', min: 5, max: 170, step: 1, value: Math.round(camera.fov)});
      fov.style.width = '60px';
      const height = el('input', {type: 'number', min: 0, max: 10000, step: 0.1, value: camera.height});
      height.style.width = '64px';
      this.panel.replaceChildren(
        this.field('Label', label, input => { camera.label = input.value.trim().slice(0, 40) || 'CAMERA'; }),
        this.field('Field of view °', fov, input => { const value = Number(input.value); if (value >= 5 && value <= 170) camera.fov = value; }),
        this.field('Lens height m', height, input => { const value = Number(input.value); if (value >= 0) camera.height = value; }), remove);
    } else {
      this.panel.replaceChildren(el('span', {className: 'h3csm-hint', textContent: this.layout.camera
        ? 'Select a marker or the camera to edit it.' : 'Use Place camera to add the camera, then Add marker for each character.'}));
    }
  }

  // --- pointer --------------------------------------------------------------------------------------------------

  point(event) {
    const view = this.frame();
    const x = (event.clientX - view.box.left - view.x) / view.scale, y = (event.clientY - view.box.top - view.y) / view.scale;
    return {x, y, u: Math.min(1, Math.max(0, x / view.width)), v: Math.min(1, Math.max(0, y / view.height)), view};
  }

  pointerDown(event) {
    if (event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    this.canvas.focus();
    this.canvas.setPointerCapture?.(event.pointerId);
    const p = this.point(event);
    if (this.mode === 'marker') {
      const index = addMarker(this.layout, p.u, p.v, {icon: this.icon, color: this.color});
      if (this.options.markerId) this.layout.markers[index].id = this.options.markerId();
      this.drag = {kind: 'marker', index};
      this.select({kind: 'marker', index});
      return;
    }
    if (this.mode === 'camera') {
      placeCamera(this.layout, p.u, p.v);
      this.drag = {kind: 'aim', x: p.u, y: p.v};
      this.select({kind: 'camera'});
      return;
    }
    const hit = hitTest(this.layout, p.view.width, p.view.height, p.x, p.y);
    if (hit?.kind === 'camera') {
      const camera = this.layout.camera;
      this.drag = {kind: 'camera', dx: camera.x - p.u, dy: camera.y - p.v};
    } else if (hit?.kind === 'marker') {
      const marker = this.layout.markers[hit.index];
      this.drag = {kind: 'marker', index: hit.index, dx: marker.x - p.u, dy: marker.y - p.v};
    } else this.drag = hit;
    this.select(hit);
  }

  pointerMove(event) {
    const p = this.point(event);
    const drag = this.drag;
    if (!drag) {
      if (this.mode === 'move') this.canvas.style.cursor = hitTest(this.layout, p.view.width, p.view.height, p.x, p.y) ? 'grab' : 'default';
      return;
    }
    event.stopPropagation();
    const clamp = value => Math.min(1, Math.max(0, value));
    const camera = this.layout.camera;
    if (drag.kind === 'marker') {
      const marker = this.layout.markers[drag.index];
      marker.x = clamp(p.u + (drag.dx ?? 0));
      marker.y = clamp(p.v + (drag.dy ?? 0));
    } else if (drag.kind === 'camera' && camera) {
      camera.x = clamp(p.u + drag.dx);
      camera.y = clamp(p.v + drag.dy);
    } else if (drag.kind === 'target' && camera) {
      camera.tx = p.u;
      camera.ty = p.v;
    } else if (drag.kind === 'aim') {
      placeCamera(this.layout, drag.x, drag.y, p.u, p.v);
    }
    this.moved = true;
    this.draw();
  }

  pointerUp(event) {
    if (!this.drag) return;
    event.stopPropagation();
    this.canvas.releasePointerCapture?.(event.pointerId);
    const added = this.drag.kind === 'marker' && this.mode === 'marker';
    this.drag = null;
    if (this.moved || added || this.mode === 'camera') this.commit();
    this.moved = false;
    if (this.mode === 'camera') { this.mode = 'move'; this.renderTools(); }
  }

  keyDown(event) {
    if (event.key === 'Delete' || event.key === 'Backspace') {
      event.preventDefault();
      event.stopPropagation();
      this.removeSelected();
    } else if (event.key === 'Escape') {
      event.stopPropagation();
      this.select(null);
    }
  }

  destroy() {
    this.observer?.disconnect();
  }
}
