// Draws an H3 Scene Map layout on a 2D canvas the way h3_continuity/scene_map.py bakes it, plus the editor's own
// handles (view cone, target ring, selection), which never reach the output. Keep the two in step.
import {ICONS} from './h3c_scene_map_icons.mjs?v=a943d84d2d3c';
import {cone, heading, legendRows, unit} from './h3c_scene_map_model.mjs?v=e7a88f4152e0';

const FONT = '"Segoe UI", Arial, "DejaVu Sans", sans-serif';
const DARK = 'rgba(20,20,22,0.92)';

function light(hex) {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 > 0.62;
}

function glyph(ctx, cx, cy, k, icon, fg, cut) {
  const at = (x, y) => [cx + (x - 12) * k, cy + (y - 12) * k];
  for (const shape of ICONS[icon]?.shapes ?? []) {
    const fill = shape.cut ? cut : fg;
    ctx.fillStyle = ctx.strokeStyle = fill;
    ctx.beginPath();
    if (shape.circle || shape.ring) {
      const [x, y, r] = shape.circle ?? shape.ring;
      ctx.arc(...at(x, y), r * k, 0, Math.PI * 2);
      if (shape.circle) ctx.fill(); else { ctx.lineWidth = shape.w * k; ctx.stroke(); }
    } else if (shape.poly) {
      for (let i = 0; i < shape.poly.length; i += 2) ctx.lineTo(...at(shape.poly[i], shape.poly[i + 1]));
      ctx.closePath(); ctx.fill();
    } else if (shape.line) {
      for (let i = 0; i < shape.line.length; i += 2) ctx.lineTo(...at(shape.line[i], shape.line[i + 1]));
      ctx.lineWidth = shape.w * k; ctx.lineCap = ctx.lineJoin = 'round'; ctx.stroke();
    }
  }
}

export function badge(ctx, cx, cy, r, icon, color, text = '') {
  const disc = (x, y, radius, fill) => { ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.fillStyle = fill; ctx.fill(); };
  disc(cx + r * 0.06, cy + r * 0.1, r * 1.12, 'rgba(0,0,0,0.43)');
  disc(cx, cy, r * 1.08, DARK);
  disc(cx, cy, r, '#ffffff');
  disc(cx, cy, r * 0.86, color);
  const fg = light(color) ? '#141416' : '#ffffff';
  if (icon === 'text') {
    if (!text) return;
    ctx.fillStyle = fg;
    ctx.font = `bold ${r * (text.length === 1 ? 1 : text.length === 2 ? 0.82 : 0.62)}px ${FONT}`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(text, cx, cy);
  } else glyph(ctx, cx, cy, r * 0.86 * 0.82 / 12, icon, fg, color);
}

export function arrow(ctx, tip, angle, length, width, color) {
  const head = width * 1.5, shaft = width * 0.42, c = Math.cos(angle), s = Math.sin(angle);
  const local = [[0, 0], [-head, -width / 2], [-head, -shaft / 2], [-length, -shaft / 2], [-length, shaft / 2], [-head, shaft / 2], [-head, width / 2]];
  ctx.beginPath();
  for (const [x, y] of local) ctx.lineTo(tip[0] + x * c - y * s, tip[1] + x * s + y * c);
  ctx.closePath();
  ctx.lineWidth = width * 0.16; ctx.lineJoin = 'round'; ctx.strokeStyle = DARK; ctx.stroke();
  ctx.fillStyle = color; ctx.fill();
}

function label(ctx, x, y, text, size, align = 'left', baseline = 'middle') {
  ctx.font = `bold ${size}px ${FONT}`;
  ctx.textAlign = align; ctx.textBaseline = baseline;
  ctx.lineWidth = Math.max(2, size * 0.16) * 2; ctx.lineJoin = 'round'; ctx.strokeStyle = DARK;
  ctx.strokeText(text, x, y);
  ctx.fillStyle = '#ffffff'; ctx.fillText(text, x, y);
}

function legend(ctx, layout, width, height, r) {
  const rows = legendRows(layout);
  if (!rows.length || !layout.legend.show) return null;
  const rl = r * 0.62, rowH = r * 1.7, gap = r * 0.5, swatch = rl * 2.6;
  ctx.font = `bold ${r * 0.72}px ${FONT}`;
  const boxW = gap + swatch + gap * 0.8 + Math.max(...rows.map(row => ctx.measureText(row.text).width)) + gap * 1.2;
  const boxH = gap * 0.9 + r * 0.9 + rows.length * rowH + gap * 0.4, margin = r * 0.8;
  const position = layout.legend.position;
  const x = position.endsWith('left') ? margin : width - boxW - margin;
  const y = position.startsWith('top') ? margin : height - boxH - margin;
  ctx.beginPath(); ctx.roundRect(x, y, boxW, boxH, r * 0.4);
  ctx.fillStyle = 'rgba(16,16,18,0.8)'; ctx.fill();
  ctx.lineWidth = Math.max(1, r * 0.06); ctx.strokeStyle = 'rgba(255,255,255,0.24)'; ctx.stroke();
  ctx.font = `bold ${r * 0.56}px ${FONT}`; ctx.fillStyle = 'rgba(255,255,255,0.67)';
  ctx.textAlign = 'left'; ctx.textBaseline = 'top';
  ctx.fillText('LEGEND', x + gap, y + gap * 0.9);
  rows.forEach((row, index) => {
    const cy = y + gap * 0.9 + r * 0.9 + rowH * (index + 0.5);
    if (row.kind === 'marker') badge(ctx, x + gap + swatch / 2, cy, rl, row.icon, row.color, row.mark);
    else arrow(ctx, [x + gap + swatch, cy], 0, swatch, r * 0.75, row.color);
    ctx.font = `bold ${r * 0.72}px ${FONT}`; ctx.fillStyle = '#ffffff'; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    ctx.fillText(row.text, x + gap + swatch + gap * 0.8, cy);
  });
  return {x, y, width: boxW, height: boxH};
}

// Draws in picture pixels: scale the context to the canvas first. `selected` is {kind, index} or null.
export function drawLayout(ctx, layout, width, height, {selected = null, editor = true} = {}) {
  const r = unit(layout, width, height), camera = layout.camera;
  if (camera && editor) {
    const points = cone(camera, width, height);
    ctx.beginPath(); points.forEach(point => ctx.lineTo(...point)); ctx.closePath();
    ctx.fillStyle = 'rgba(255,255,255,0.12)'; ctx.fill();
    ctx.setLineDash([r * 0.5, r * 0.35]); ctx.lineWidth = Math.max(1, r * 0.08); ctx.strokeStyle = 'rgba(255,255,255,0.85)'; ctx.stroke();
    ctx.setLineDash([]);
    const tx = camera.tx * width, ty = camera.ty * height;
    ctx.beginPath(); ctx.arc(tx, ty, r * 0.55, 0, Math.PI * 2);
    ctx.lineWidth = r * 0.22; ctx.strokeStyle = DARK; ctx.stroke();
    ctx.lineWidth = r * 0.12; ctx.strokeStyle = selected?.kind === 'target' ? '#ffd23f' : '#ffffff'; ctx.stroke();
  }
  if (camera) {
    const px = camera.x * width, py = camera.y * height, angle = heading(camera, width, height);
    arrow(ctx, [px, py], angle, r * 4.2, r * 1.5, camera.color);
    if (editor && selected?.kind === 'camera') {
      ctx.beginPath(); ctx.arc(px, py, r * 0.5, 0, Math.PI * 2); ctx.lineWidth = r * 0.14; ctx.strokeStyle = '#ffd23f'; ctx.stroke();
    }
  }
  layout.markers.forEach((marker, index) => {
    const size = r * marker.size, x = marker.x * width, y = marker.y * height;
    badge(ctx, x, y, size, marker.icon, marker.color, marker.text);
    if (editor && selected?.kind === 'marker' && selected.index === index) {
      ctx.beginPath(); ctx.arc(x, y, size * 1.35, 0, Math.PI * 2);
      ctx.setLineDash([size * 0.3, size * 0.2]); ctx.lineWidth = size * 0.14; ctx.strokeStyle = '#ffd23f'; ctx.stroke(); ctx.setLineDash([]);
    }
  });
  for (const marker of layout.markers) {
    if (marker.label) label(ctx, marker.x * width + r * marker.size * 1.35, marker.y * height, marker.label, r * 0.82);
  }
  if (camera) {
    const angle = heading(camera, width, height);
    label(ctx, camera.x * width - Math.cos(angle) * r * 4.6, camera.y * height - Math.sin(angle) * r * 4.6 + r * 0.2, camera.label,
      r * 0.82, 'center', 'top');
  }
  return legend(ctx, layout, width, height, r);
}
