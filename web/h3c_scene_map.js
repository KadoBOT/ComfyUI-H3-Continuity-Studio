// The H3 Scene Map editor: pick a map picture, place markers and the camera, and edit the legend. Everything is saved
// in the node's hidden layout and image widgets; h3_continuity/scene_map.py draws the output from them.
import {app} from '../../scripts/app.js';
import {api} from '../../scripts/api.js';
import {showOwnElement} from './h3c_dom_widget.mjs?v=961e6d7f3bb7';
import {LEGEND_POSITIONS, PALETTE, addMarker, hitTest, iconNames, parseLayout, placeCamera, serializeLayout} from './h3c_scene_map_model.mjs?v=e7a88f4152e0';
import {badge, drawLayout} from './h3c_scene_map_draw.mjs?v=7143aaa9f4a0';

const NODE_TYPE = 'H3C_SceneMap';
const HEIGHT = 640;
const MODES = [['move', 'Move', 'Drag markers, the camera arrow or its aim ring'], ['marker', 'Add marker', 'Click the map to add a marker'],
  ['camera', 'Place camera', 'Press where the camera stands and drag towards where it looks']];
const STYLE = `
.h3csm{box-sizing:border-box;display:flex;flex-direction:column;gap:6px;height:${HEIGHT}px;padding:4px;font:12px/1.3 system-ui,sans-serif;color:#ddd}
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
.h3csm select.h3csm-image{max-width:260px}
`;

function findWidget(node, name) {
  return node.widgets?.find(widget => widget.name === name);
}

function hide(widget) {
  if (!widget) return;
  widget.hidden = true;
  widget.computeSize = () => [0, -4];
  widget.computeLayoutSize = () => ({minHeight: 0, maxHeight: 0, minWidth: 0});
  widget.options = widget.options || {};
  widget.options.hidden = true;
}

function el(tag, props = {}, ...children) {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children.filter(child => child != null));
  return node;
}

function viewUrl(file) {
  const name = file.filename, subfolder = file.subfolder ?? '';
  return api.apiURL(`/view?filename=${encodeURIComponent(name)}&type=${file.type}&subfolder=${encodeURIComponent(subfolder)}`);
}

function inputFile(value) {
  const parts = String(value).split('/');
  return {filename: parts.pop(), subfolder: parts.join('/'), type: 'input'};
}

class SceneMapEditor {
  constructor(node) {
    this.node = node;
    this.layoutWidget = findWidget(node, 'layout');
    this.imageWidget = findWidget(node, 'image');
    hide(this.layoutWidget);
    hide(this.imageWidget);
    this.layout = parseLayout(this.layoutWidget?.value);
    this.selected = null;
    this.mode = 'move';
    this.icon = 'dot';
    this.color = PALETTE[0];
    this.picture = null;
    this.pictureUrl = null;
    this.background = null;
    this.build();
    const dom = node.addDOMWidget('h3c_scene_map_editor', 'custom', this.root, {
      serialize: false, hideOnZoom: false, getMinHeight: () => HEIGHT, getMaxHeight: () => HEIGHT,
    });
    dom.serialize = false;
    if (dom.options) dom.options.serialize = false;
    dom.computeSize = width => [width ?? node.size?.[0] ?? 520, HEIGHT];
    dom.computeLayoutSize = () => ({minHeight: HEIGHT, maxHeight: HEIGHT, minWidth: 0});
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
    this.imageSelect.addEventListener('change', () => this.setImage(this.imageSelect.value));
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
    this.root = el('div', {className: 'h3csm'}, pictureRow, toolRow, iconRow, colorRow, this.stage, this.panel, legendRow, hint);
    this.renderTools();
  }

  // --- state ----------------------------------------------------------------------------------------------------

  commit() {
    const value = serializeLayout(this.layout);
    if (this.layoutWidget && this.layoutWidget.value !== value) {
      this.layoutWidget.value = value;
      this.layoutWidget.callback?.(value);
      this.node.graph?.change?.();
    }
    this.node.setDirtyCanvas?.(true, true);
    this.draw();
  }

  reload() {
    this.layout = parseLayout(this.layoutWidget?.value);
    this.selected = null;
    this.loadPicture();
    this.renderPanel();
    this.renderTools();
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

  backgroundLinked() {
    return this.node.inputs?.find(slot => slot.name === 'background')?.link != null;
  }

  async loadImages() {
    let images = [];
    try { images = (await (await api.fetchApi('/h3c/scene-map/images')).json()).images ?? []; } catch { images = []; }
    const current = this.imageWidget?.value ?? '';
    if (current && !images.includes(current)) images.unshift(current);
    this.imageSelect.replaceChildren(el('option', {value: '', textContent: images.length ? '(choose a picture)' : '(no pictures in input)'}),
      ...images.map(name => el('option', {value: name, textContent: name})));
    this.imageSelect.value = current;
  }

  setImage(name) {
    if (!this.imageWidget) return;
    this.imageWidget.value = name;
    this.imageWidget.callback?.(name);
    this.node.graph?.change?.();
    this.loadPicture();
  }

  async upload(file) {
    if (!file) return;
    const body = new FormData();
    body.append('image', file);
    body.append('type', 'input');
    body.append('subfolder', 'maps');
    try {
      const response = await api.fetchApi('/upload/image', {method: 'POST', body});
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      const saved = await response.json();
      const name = saved.subfolder ? `${saved.subfolder}/${saved.name}` : saved.name;
      this.setImage(name);
      await this.loadImages();
    } catch (error) {
      this.sourceNote.textContent = `Upload failed: ${error.message}`;
    } finally {
      this.fileInput.value = '';
    }
  }

  loadPicture() {
    let file = null;
    if (this.backgroundLinked()) {
      file = this.background;
      this.sourceNote.textContent = file ? 'Showing the connected background from the last run.' : 'Run the node once to show the connected background.';
    } else {
      const name = this.imageWidget?.value;
      file = name ? inputFile(name) : null;
      this.sourceNote.textContent = '';
    }
    this.imageSelect.disabled = this.backgroundLinked();
    const url = file ? viewUrl(file) : null;
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
    drawLayout(ctx, this.layout, view.width, view.height, {selected: this.selected});
    ctx.restore();
    if (!this.picture) {
      ctx.fillStyle = '#aaa';
      ctx.font = '13px system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(this.backgroundLinked() ? 'Run once to show the connected background' : 'Choose or upload a map picture', box.width / 2, 22);
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

function hook(node, name, after) {
  const before = node[name];
  node[name] = function (...args) {
    const result = before?.apply(this, args);
    after.apply(this, args);
    return result;
  };
}

app.registerExtension({
  name: 'h3c.scene_map',
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_TYPE) return;
    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function (...args) {
      const result = onNodeCreated?.apply(this, args);
      const editor = this.h3cSceneMap = new SceneMapEditor(this);
      hook(this, 'onConfigure', () => {
        editor.reload();
        editor.loadImages();
        setTimeout(() => showOwnElement(this, editor.root, '.h3csm', app.canvas?.graph), 0);
      });
      hook(this, 'onExecuted', message => {
        const file = message?.h3c_scene_map?.[0];
        if (file) { editor.background = file; editor.loadPicture(); }
      });
      hook(this, 'onConnectionsChange', () => editor.loadPicture());
      hook(this, 'onRemoved', () => editor.destroy());
      this.setSize?.([Math.max(this.size?.[0] ?? 0, 560), Number(this.computeSize?.()?.[1]) || HEIGHT + 120]);
      return result;
    };
  },
});
