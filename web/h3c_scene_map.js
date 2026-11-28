// The H3 Scene Map node's editor. Everything is saved in the node's hidden layout and image widgets;
// h3_continuity/scene_map.py draws the output from them.
import {app} from '../../scripts/app.js';
import {api} from '../../scripts/api.js';
import {showOwnElement} from './h3c_dom_widget.mjs?v=961e6d7f3bb7';
import {HEIGHT, SceneMapEditor} from './h3c_scene_map_editor.mjs?v=2cf054593719';

const NODE_TYPE = 'H3C_SceneMap';

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

function write(node, widget, value) {
  if (!widget || widget.value === value) return;
  widget.value = value;
  widget.callback?.(value);
  node.graph?.change?.();
}

function nodeEditor(node) {
  const layoutWidget = findWidget(node, 'layout'), imageWidget = findWidget(node, 'image');
  hide(layoutWidget);
  hide(imageWidget);
  const editor = new SceneMapEditor({
    api, height: HEIGHT, layout: layoutWidget?.value, image: imageWidget?.value ?? '',
    onLayout: layout => { write(node, layoutWidget, JSON.stringify(layout)); node.setDirtyCanvas?.(true, true); },
    onImage: name => write(node, imageWidget, name),
    linked: () => node.inputs?.find(slot => slot.name === 'background')?.link != null,
  });
  const dom = node.addDOMWidget('h3c_scene_map_editor', 'custom', editor.root, {
    serialize: false, hideOnZoom: false, getMinHeight: () => HEIGHT, getMaxHeight: () => HEIGHT,
  });
  dom.serialize = false;
  if (dom.options) dom.options.serialize = false;
  dom.computeSize = width => [width ?? node.size?.[0] ?? 520, HEIGHT];
  dom.computeLayoutSize = () => ({minHeight: HEIGHT, maxHeight: HEIGHT, minWidth: 0});
  editor.reload = () => {
    editor.selected = null;
    editor.setLayout(layoutWidget?.value, {force: true});
    editor.setImage(imageWidget?.value ?? '');
    editor.loadImages();
  };
  return editor;
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
      const editor = this.h3cSceneMap = nodeEditor(this);
      hook(this, 'onConfigure', () => {
        editor.reload();
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
