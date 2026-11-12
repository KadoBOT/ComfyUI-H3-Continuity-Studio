// The Studio: the page's one full-window view of a Timeline. While open it holds the editor's regions, and the linked
// Story's actions, story and files, in its own layout, and it gives each one back to the place it came from when it
// closes, opens another Timeline or the Timeline's Story changes. Its Story page edits the Story node's inputs.
import { liveBadge, progressText } from './h3c_render_watch.mjs?v=7c8222569836';
import { templateRow } from './h3c_templates.mjs?v=ff7103cdcba7';
import { soundtrackLine, soundtrackSlots } from './h3c_timeline_model.mjs?v=25c8aab2bb32';

import { ideaImagesRow } from './h3c_idea_images.mjs?v=3e6280e44a1b';
import { partialBadge, partialTitle, previewBadge, previewLabel, previewTitle, timelineFrame, videoSeconds } from './h3c_partial_video.mjs?v=201bf0f48645';
import {historyShortcut} from './h3c_history.mjs?v=d639ee9ffd57';
import {setText} from './h3c_dom.mjs?v=584a9bf55653';

const LIBRARY = ['references', 'cast', 'story', 'pictures', 'refmods'];
const CENTER = ['viewer', 'story', 'cast', 'pictures', 'refmods'];
const FOCUS = ['cast', 'story', 'pictures', 'refmods', 'project'];
const CORE_HINT = 'For a moving preview, add KJNodes’ Model Preview Override before the sampler.';
const OLDER_TAKE = 'Outdated take: this clip changed after it rendered. It still plays in the full video; regenerate the clip to update it.';
const MOVING = 'Moving the take…';
const FPS = 24;
// The Timeline frame where box `index` starts.
const boxStart = (state, index) => state.boxes.slice(0, index).reduce((sum, box) => sum + box.frames, 0);
const NO_STORY = 'Link an H3 Story node to this Timeline’s story input to write with a model.';
const STYLE_ID = 'h3cx-style';
const LAYOUT_KEY = 'h3cx-layout';
const TRACK_MIN = 250;
const ZOOM_MAX = 16;
const MOBILE_QUERY = '(max-width:600px), (max-width:1100px) and (max-height:500px)';
const CSS = `
.h3cx-studio { position: fixed; inset: 0; z-index: 1500; display: flex; flex-direction: column; outline: none;
  overflow: hidden; background: #15171c; color: var(--input-text, #ddd); font: 14px/1.45 system-ui, sans-serif; }
.h3cx-studio * { box-sizing: border-box; }
.h3cx-studio[hidden], .h3cx-studio [hidden] { display: none !important; }
.h3cx-new-project { max-width: min(620px, calc(100vw - 24px)); max-height: calc(100vh - 24px); overflow:auto; padding:20px; background:#1d2027; color:var(--input-text, #ddd); font:14px/1.45 system-ui,sans-serif; border:1px solid #535b6c; }
.h3cx-new-project::backdrop { background:#0009; }
.h3cx-new-project button { margin-right:8px; margin-top:8px; }
.h3cx-bar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 6px 10px;
  background: #1d2027; border-bottom: 1px solid #2c313c; }
.h3cx-name { font-weight: 600; white-space: nowrap; }
.h3cx-slot { display: flex; align-items: center; gap: 6px; min-width: 0; }
.h3cx-grow { flex: 1 1 auto; }
.h3cx-progress { color: #aab1bd; white-space: nowrap; }
.h3cx-main { flex: 1 1 auto; min-height: 0; display: grid; grid-template-columns: var(--h3cx-lib) minmax(0, 1fr) var(--h3cx-insp); position: relative;
  --h3cx-lib-min: 256px; --h3cx-insp-min: 346px;
  --h3cx-lib: clamp(var(--h3cx-lib-min), var(--h3cx-lib-w, var(--h3cx-lib-min)), 40vw);
  --h3cx-insp: clamp(var(--h3cx-insp-min), var(--h3cx-insp-w, var(--h3cx-insp-min)), 40vw); }
.h3cx-references-hidden .h3cx-main { grid-template-columns:minmax(0,1fr) var(--h3cx-insp); }
.h3cx-center { display:flex; flex-direction:column; min-width:0; min-height:0; }
.h3cx-center > .h3cx-player, .h3cx-center > .h3cx-focus { flex:1 1 auto; }
.h3cx-player { display: flex; flex-direction: column; gap: 6px; min-width: 0; min-height: 0; overflow-y:auto; padding: 8px 10px; }
.h3cx-player > * { flex-shrink:0; }
.h3cx-inspector { display: flex; flex-direction: column; gap: 6px; min-width:0; min-height: 0; overflow-y: auto; padding: 8px 10px;
  background: #1a1c22; border-left: 1px solid #2c313c; }
.h3cx-switch { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.h3cx-export-status { display:flex; align-items:center; gap:8px; margin:0; overflow-wrap:anywhere; }
.h3cx-export-status progress { width:80px; flex:0 0 80px; accent-color:#729cdd; }
.h3cx-switch .h3ct-button[aria-pressed="true"] { background: #293e60; border-color: #729cdd; }
.h3cx-links { display: inline-flex; flex-wrap:wrap; align-items:center; min-width:0; max-width:100%; gap: 10px; margin-left: 8px; }
.h3cx-stage { position: relative; flex: 1 1 auto; min-height: 120px; overflow: hidden;
  background: #0c0d10; border: 1px solid #2c313c; border-radius: 6px; }
.h3cx-screen { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: #aab1bd; }
.h3cx-screen video, .h3cx-screen img { width: 100%; height: 100%; object-fit: contain; background: #000; }
.h3cx-badge { position: absolute; top: 8px; left: 8px; padding: 2px 8px; border-radius: 4px; font-size: 12px;
  background: rgba(12, 13, 16, .85); pointer-events: none; }
.h3cx-hint, .h3cx-soundtrack { margin: 0; font-size: 12px; color: #aab1bd; }
.h3cx-page { display: flex; flex-direction: column; gap: 6px; }
.h3cx-inputs { display: flex; flex-direction: column; gap: 8px; }
.h3cx-story-advanced > summary { cursor: pointer; color: #aab1bd; }
.h3cx-story-advanced > .h3cx-inputs { margin-top: 8px; }
.h3cx-field { display: flex; flex-direction: column; gap: 2px; }
.h3cx-check { flex-direction: row; align-items: center; gap: 6px; }
.h3cx-label, .h3cx-linked, .h3cx-note { color: #aab1bd; }
.h3cx-linked, .h3cx-note { margin: 0; }
.h3cx-field textarea, .h3cx-field select, .h3cx-field input[type="number"], .h3cx-field input[type="text"] { padding: 4px 6px; font: inherit; color: inherit;
  background: var(--comfy-input-bg, #14161a); border: 1px solid var(--border-color, #333); border-radius: 4px; }
.h3cx-field textarea { width: 100%; min-height: 72px; resize: vertical; }
.h3cx-field input[type="number"] { width: 120px; }
.h3cx-template { display: flex; flex-direction: column; gap: 4px; }
.h3cx-template select { width: 100%; }
.h3cx-template-details p, .h3cx-template-folder { margin: 0; font-size: 12px; color: #aab1bd; }
.h3cx-template-folder { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; overflow-wrap: anywhere; }
.h3cx-track { flex: 0 0 clamp(250px, var(--h3cx-track-h, 250px), 70vh); min-height: 0; max-height: max(250px, 70vh); overflow-y: auto; padding: 6px 10px 8px;
  background: #1d2027; border-top: 1px solid #2c313c; }
.h3cx-track .h3ct-hint { margin-top: 4px; }
.h3cx-track .h3ct-ruler { height:1.2em; }
.h3cx-track .h3ct-tick { height:100%; }
.h3cx-bar { flex: 0 0 auto; min-height: 50px; flex-wrap: wrap; }
.h3cx-bar > * { min-width:0; max-width:100%; }
.h3cx-bar .h3cx-slot { flex-wrap:wrap; }
.h3cx-name { white-space: normal; overflow-wrap: anywhere; }
.h3cx-activity { flex:0 0 auto; display:flex; align-items:center; flex-wrap:wrap; gap:8px; min-height:32px; padding:4px 10px; border-bottom:1px solid #2c313c; }
.h3cx-notice { flex:0 0 auto; padding:0 10px; }
.h3cx-notice > .h3ct-hint { margin:6px 0; }
.h3cx-progress { white-space:normal; }
.h3cx-title { margin:0; font-size:14px; font-weight:600; overflow-wrap:anywhere; }
.h3cx-library { min-width:0; min-height:0; overflow:auto; padding:12px; border-right:1px solid #2c313c; background:#1a1c22; }
.h3cx-library-nav { display:flex; flex-wrap:wrap; gap:6px; margin:10px 0; }
.h3cx-library-nav button[aria-pressed="true"] { background:#293e60; border-color:#729cdd; }
.h3cx-library .h3ct-row, .h3cx-library .h3cr-actions { flex-wrap:wrap; }
.h3cx-focus { display:flex; flex-direction:column; min-width:0; min-height:0; }
.h3cx-focus-head { flex:0 0 auto; display:flex; flex-wrap:wrap; align-items:center; gap:12px; padding:12px 16px; border-bottom:1px solid #2c313c; }
.h3cx-focus-body { min-height:0; overflow:auto; padding:16px; }
.h3cx-focus .h3cx-page { max-width:100%; }
.h3cx-focus .h3cc-cast { min-width:0; }
.h3cx-focus .h3cc-name { white-space:normal; overflow-wrap:anywhere; }
.h3cx-writer-message { min-width:0; overflow-wrap:anywhere; }
.h3cx-focus textarea { min-width:0; }
.h3cx-track-toolbar, .h3cx-audio-toolbar, .h3cx-text-toolbar { display:flex; flex-wrap:wrap; align-items:center; gap:12px; margin-bottom:6px; }
.h3cx-track-toolbar .h3cx-slot { flex-wrap:wrap; }
.h3cx-library-toggle { display:inline-block; }
.h3cx-split { position:absolute; z-index:4; background:transparent; touch-action:none; }
.h3cx-split:hover, .h3cx-split:focus-visible, .h3cx-split.h3cx-dragging { background:#729cdd88; outline:none; }
.h3cx-split-v { top:0; bottom:0; width:7px; cursor:col-resize; }
.h3cx-split-lib { left:calc(var(--h3cx-lib) - 4px); }
.h3cx-split-insp { right:calc(var(--h3cx-insp) - 3px); }
.h3cx-references-hidden .h3cx-split-lib { display:none; }
.h3cx-split-h { flex:0 0 6px; position:relative; margin:-3px 0; z-index:4; cursor:row-resize; }
.h3cx-zoom { display:inline-flex; align-items:center; gap:4px; margin-left:auto; }
.h3cx-zoom output { min-width:4ch; text-align:center; font-size:12px; color:#aab1bd; }
.h3cx-inspector-toggle { display:none; }
.h3cx-studio button, .h3cx-studio input, .h3cx-studio select, .h3cx-studio textarea { font-size:14px; }
.h3cx-studio .h3ct-hint, .h3cx-studio .h3ct-label { font-size:12px; }
.h3cx-studio p, .h3cx-studio summary { overflow-wrap:anywhere; }
.h3cx-studio .h3ct-panel-tabs { flex-wrap:wrap; }
.h3cx-studio .h3ct-button { max-width:100%; white-space:normal; overflow-wrap:anywhere; }
.h3cx-inspector .h3ct-panel { min-width:0; }
.h3cx-inspector input, .h3cx-inspector select, .h3cx-inspector textarea { max-width:100%; }
.h3cx-project-actions { display:flex; flex-wrap:wrap; gap:8px; }
.h3cx-history { width:min(520px,calc(100vw - 24px)); max-height:80dvh; overflow:auto; padding:16px;
  background:#1d2027; color:var(--input-text,#ddd); border:1px solid #535b6c; border-radius:6px; font:14px/1.45 system-ui,sans-serif; }
.h3cx-history::backdrop { background:#0009; }
.h3cx-history-head { display:flex; justify-content:space-between; align-items:center; gap:12px; }
.h3cx-history-list { display:flex; flex-direction:column; gap:4px; padding:0; list-style:none; }
.h3cx-history-list button { width:100%; text-align:left; padding:8px; }
.h3cx-history-list [aria-current="step"] { background:#293e60; border-color:#729cdd; }
.h3cx-history-list .h3cx-future { opacity:.65; }
.h3cx-mobile-nav, .h3cx-mobile-more { display:none; }
.h3cx-focus-body { flex:1; min-width:0; }
@media(max-width:1150px) { .h3cx-main { --h3cx-lib-min:220px; --h3cx-insp-min:310px; } .h3cx-bar .h3cx-slot { font-size:12px; } }
@media(max-width:899px) {
 .h3cx-main, .h3cx-references-hidden .h3cx-main { grid-template-columns:minmax(0,1fr); }
 .h3cx-split { display:none; }
 .h3cx-inspector-toggle { display:inline-block; }
 .h3cx-inspector { display:none; }
 .h3cx-inspector-open .h3cx-inspector { display:flex; position:absolute; inset:0 0 0 auto; width:min(346px,100%); z-index:3; box-shadow:-8px 0 24px #0008; }
 .h3cx-library-toggle { display:inline-block; }
 .h3cx-library { display:none; }
 .h3cx-library-open .h3cx-library { display:block; position:absolute; inset:0 auto 0 0; width:256px; z-index:2; box-shadow:8px 0 24px #0008; }
 .h3cx-bar { flex-wrap:wrap; }
 .h3cx-bar .h3cx-slot { display:none; }
}
@media ${MOBILE_QUERY} {
 .h3cx-studio { height:var(--h3cx-viewport-height,100dvh); top:var(--h3cx-viewport-top,0px); bottom:auto; padding-top:env(safe-area-inset-top); }
 .h3cx-bar { min-height:56px; flex-wrap:nowrap; padding:6px 12px; }
 .h3cx-bar .h3cx-library-toggle, .h3cx-bar .h3cx-inspector-toggle { display:none; }
 .h3cx-bar .h3cx-name { flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
 .h3cx-bar .h3cx-grow { display:none; }
 .h3cx-activity { min-height:0; max-height:20dvh; overflow:auto; padding:4px 12px; gap:4px; font-size:12px; }
 .h3cx-activity.h3cx-empty { display:none; }
 .h3cx-main { display:flex; overflow:hidden; }
 .h3cx-main > .h3cx-center, .h3cx-main > .h3cx-library, .h3cx-main > .h3cx-inspector { display:none; }
 .h3cx-studio[data-mobile-page="viewer"] .h3cx-center, .h3cx-studio[data-mobile-page="focus"] .h3cx-center { display:flex; width:100%; }
 .h3cx-studio[data-mobile-page="references"] .h3cx-library { display:block; }
 .h3cx-studio[data-mobile-page="clip"] .h3cx-inspector { display:flex; }
 .h3cx-main > .h3cx-library, .h3cx-main > .h3cx-inspector { position:static; width:100%; flex:1; box-shadow:none; border:0; }
 .h3cx-center > .h3cx-library-nav { display:none; }
 .h3cx-player { padding:8px 12px; }
 .h3cx-stage { flex:1 0 120px; }
 .h3cx-switch { gap:6px; }
 .h3cx-links { gap:6px; margin-left:0; }
 .h3cx-focus-head { padding:8px 12px; }
 .h3cx-focus-body { padding:12px; scroll-padding:12px; }
 .h3cx-track { display:none; }
 .h3cx-studio[data-mobile-page="timeline"] .h3cx-main { display:none; }
 .h3cx-studio[data-mobile-page="timeline"] .h3cx-track { display:block; flex:1; max-height:none; padding:12px; }
 .h3cx-track .h3ct-lane { overscroll-behavior-x:contain; touch-action:pan-x pan-y; }
 .h3cx-track .h3ct-lane > .h3ct-stills, .h3cx-track .h3ct-lane > .h3ct-ruler,
 .h3cx-track .h3ct-lane > .h3ct-track, .h3cx-track .h3ct-lane > .h3ct-audio { min-width:var(--h3cx-track-width,480px); }
 .h3cx-track .h3ct-track { height:68px; touch-action:pan-x pan-y; }
 .h3cx-track .h3ct-audio { touch-action:pan-x pan-y; }
 .h3cx-track .h3ct-box, .h3cx-track .h3ct-audio-clip { touch-action:pan-x pan-y; }
 .h3cx-track .h3ct-audio-lane { height:56px; }
 .h3cx-track .h3ct-audio-clip { height:48px; }
 .h3cx-track .h3ct-handle, .h3cx-track .h3ct-audio-handle { width:28px; touch-action:none; }
 .h3cx-studio button, .h3cx-studio select, .h3cx-studio input:not([type="checkbox"]), .h3cx-studio summary, .h3cx-studio a.h3ct-link { min-height:44px; }
 .h3cx-studio button, .h3cx-studio summary { padding:8px 10px; }
 .h3cx-studio a.h3ct-link { display:inline-flex; align-items:center; }
 .h3cx-studio input, .h3cx-studio select, .h3cx-studio textarea { font-size:16px; min-width:0; max-width:100%; }
 .h3cx-studio .h3ct-field { flex-wrap:wrap; }
 .h3cx-studio textarea { scroll-margin:12px; }
 .h3cx-new-project { max-height:calc(100dvh - 24px); padding:16px; }
 .h3cx-new-project button, .h3cx-new-project input { min-height:44px; font-size:16px; max-width:100%; }
 .h3cx-mobile-nav { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); flex:0 0 auto; gap:2px; padding:6px 4px calc(6px + env(safe-area-inset-bottom)); background:#1d2027; border-top:1px solid #343a46; }
 .h3cx-mobile-nav button { padding:10px 2px; font-size:12px; border-color:transparent; background:transparent; }
 .h3cx-mobile-nav button[aria-pressed="true"] { background:#293e60; border-color:#729cdd; }
 .h3cx-mobile-more { display:flex; flex-direction:column; gap:12px; flex:1; min-width:0; overflow:auto; padding:16px; }
 .h3cx-mobile-more > button { text-align:left; }
 .h3cx-mobile-more .h3cx-project-actions { display:flex; flex-direction:column; }
}
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

function button(text, title, onClick, className = '') {
  const node = el('button', `h3ct-button ${className}`.trim(), text);
  node.type = 'button';
  if (title) node.title = title;
  node.addEventListener('click', (event) => {
    event.preventDefault();
    onClick();
  });
  return node;
}

function link(className, text, title) {
  const node = el('a', `h3ct-link ${className}`, text);
  node.title = title;
  return node;
}

export class Studio {
  constructor() {
    ensureStyle();
    this.host = null;
    // cover(covered), when set, hears when the Studio comes to fill the page and when it leaves it.
    this.cover = null;
    this.page = 'box';
    this.libraryPage = 'references';
    this.focusPage = null;
    this.inspectorTarget = {kind: 'clip', box: null};
    this.view = null;
    this.bridgeBox = null;
    // The take Play chose on the Box page, {box, bridge, video, label}; Switch flips between it and the take in use.
    this.chosen = null;
    // The replacement candidate a bridge panel played, {box, file, label}; it plays while its box is selected.
    this.candidate = null;
    this.resumeAt = null;
    this.moving = false;
    this.borrowed = [];
    // undefined until the Story slot and page show a Story, or show that there is none (null).
    this.story = undefined;
    this.storyBorrowed = [];
    this.before = null;
    this.blob = null;
    this.blobSrc = null;
    this.trackWidth = 0;
    this.mobileMedia = matchMedia(MOBILE_QUERY);
    this.mobileLayout = this.mobileMedia.matches;
    this.narrowMedia = matchMedia('(max-width:899px)');
    this.mobilePage = 'viewer';
    this.layout = this.loadLayout();
    this.build();
    this.mobileMedia.addEventListener('change', () => this.layoutChanged());
    this.narrowMedia.addEventListener('change', () => this.layoutChanged());
    window.visualViewport?.addEventListener('resize', () => this.resizeViewport());
    window.visualViewport?.addEventListener('scroll', () => this.resizeViewport());
  }

  build() {
    const root = this.root = el('div', 'h3cx-studio');
    root.tabIndex = -1;
    root.hidden = true;
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-modal', 'true');
    root.setAttribute('aria-label', 'H3 Studio');
    root.addEventListener('keydown', (event) => this.key(event));
    // A button that its own click replaces, such as a take's Use, takes the focus with it to the page, where neither the
    // Studio nor ComfyUI hears keys, so while the Studio is open the page's keys come to it.
    document.addEventListener('keydown', (event) => {
      if (root.hidden || (event.target !== document.body && event.target !== document.documentElement)) return;
      root.focus({preventScroll: true});
      this.key(event);
    }, true);
    root.addEventListener('pointerdown', (event) => event.stopPropagation());
    // Selecting an edge also updates the inspector; keep the visible track available to measure and finish the trim.
    root.addEventListener('pointerdown', (event) => {
      if (event.button === 0 && this.mobileMedia.matches && this.mobilePage === 'timeline'
        && event.target.closest('.h3ct-handle, .h3ct-audio-handle')) this.trimmingPointer = event.pointerId;
    }, true);
    for (const name of ['pointerup', 'pointercancel']) root.addEventListener(name, (event) => {
      if (event.pointerId === this.trimmingPointer) this.trimmingPointer = null;
    }, true);
    root.addEventListener('focusin', (event) => {
      this.focusedField = event.target.matches('input, textarea, select') ? event.target : null;
    });
    root.addEventListener('focusout', (event) => {
      this.host?.history.endGroup();
      // CSS can hide a field and blur it before the breakpoint's change event arrives.
      if (this.focusedField === event.target && event.target.getClientRects().length) this.focusedField = null;
    });
    root.addEventListener('h3c-inspect', (event) => this.inspect(event.detail));
    root.addEventListener('h3c-show-page', (event) => this.setPage(event.detail?.page));
    root.addEventListener('h3c-play-bridge', (event) => {
      this.bridgeBox = event.detail?.box ?? null;
      this.setView('bridge');
    });
    root.addEventListener('h3c-play-take', (event) => {
      this.chosen = event.detail ?? null;
      this.setView('chosen');
    });
    root.addEventListener('h3c-play-candidate', (event) => {
      this.candidate = event.detail ?? null;
      this.setView('candidate');
    });
    root.addEventListener('h3c-play-region', (event) => this.playRegion(event.detail));
    root.addEventListener('h3c-seek', (event) => this.seekTimeline(event.detail?.frame));
    root.addEventListener('h3c-takes-listed', () => this.refresh());
    root.addEventListener('h3c-takes-changing', () => this.letGo());
    root.addEventListener('h3c-takes-changed', () => {
      this.moving = false;
      this.chosen = null;
      if (this.view === 'chosen') this.view = 'take';
      this.refresh();
    });

    const close = button('✕', 'Close the Studio (Esc)', () => this.close(), 'h3cx-close');
    close.setAttribute('aria-label', 'Close the Studio');
    this.nameEl = el('span', 'h3cx-name');
    this.summarySlot = el('span', 'h3cx-slot');
    this.savedSlot = el('span', 'h3cx-slot');
    this.progressEl = el('span', 'h3cx-progress');
    this.progressEl.setAttribute('aria-live', 'polite');
    this.stopButton = button('Stop', 'Stop this render and clear every pending run in ComfyUI’s queue, including runs that are not H3’s',
      () => this.host?.stop(), 'h3cx-stop');
    this.storyEl = el('div', 'h3cx-story h3cx-slot');
    this.writeOff = button('Write story', NO_STORY, () => {});
    this.writeOff.disabled = true;
    this.feedbackButton = button('Revise story', 'Ask the Story writer to change the written story', () => this.openFeedback(), 'h3cx-feedback');
    this.actionsSlot = el('span', 'h3cx-slot');
    this.newProjectButton = button('New project', 'Clear the current Timeline for a new project and keep its available sources', () => this.openNewProject());
    this.projectButton = button('Project settings', 'Shared prompt and graph settings', () => this.openFocus('project'));
    this.undoButton = button('Undo', 'Undo the last Timeline edit (Ctrl/Cmd+Z outside text fields)', () => this.host?.undo());
    this.redoButton = button('Redo', 'Redo the last undone edit (Ctrl/Cmd+Shift+Z or Ctrl+Y outside text fields)', () => this.host?.redo());
    this.historyButton = button('History', 'Jump to an earlier or later Timeline state', () => this.openHistory());
    this.downloadVideo = button('Download video', '', () => {
      const download = this.host?.editor.regions().download;
      if (!this.downloadVideo.disabled) download?.click();
    }, 'h3cx-download-video');
    this.referencesVisible = innerWidth >= 900;
    this.libraryToggle = button('References', 'Show or hide References', () => this.setReferencesVisible(!this.referencesVisible), 'h3cx-library-toggle');
    this.libraryToggle.setAttribute('aria-controls', 'h3cx-references');
    this.inspectorVisible = innerWidth >= 900;
    this.inspectorToggle = button('Inspector', 'Show or hide clip, audio and text properties', () => this.setInspectorVisible(!this.inspectorVisible), 'h3cx-inspector-toggle');
    this.inspectorToggle.setAttribute('aria-controls', 'h3cx-inspector');
    const bar = el('header', 'h3cx-bar');
    this.projectActions = el('div', 'h3cx-project-actions');
    this.projectActions.append(this.undoButton, this.redoButton, this.historyButton,
      this.newProjectButton, this.projectButton, this.downloadVideo);
    bar.append(close, this.libraryToggle, this.inspectorToggle, this.nameEl, this.summarySlot, this.savedSlot,
      el('span', 'h3cx-grow'), this.projectActions);
    this.bar = bar;
    this.buildHistory();
    const activity = el('div', 'h3cx-activity');
    this.writerCancel = el('span', 'h3cx-slot');
    this.writerMessage = el('span', 'h3cx-writer-message');
    activity.append(this.progressEl, this.stopButton, this.writerCancel, this.writerMessage, el('span', 'h3cx-grow'), this.feedbackButton);
    this.activity = activity;
    this.notice = el('div', 'h3cx-notice');

    const views = el('div', 'h3cx-switch');
    this.fullButton = button('Full video', 'Play the whole Timeline', () => this.setView('full'));
    this.takeButton = button('Clip take', 'Play the selected clip’s active take', () => this.setView('take'));
    this.switchButton = button('Compare with active take', '', () => this.switchTake());
    this.fullLinks = el('span', 'h3cx-links');
    this.takeOpen = link('h3cx-take-open', 'Open in new tab', 'Open this take in a new tab');
    this.takeOpen.target = '_blank';
    this.takeOpen.rel = 'noopener';
    this.takeDownload = link('h3cx-take-download', 'Download', 'Download this take');
    this.pinButton = button('Pin moment for…', 'Remember the paused moment of this take for a character or place',
      () => this.togglePins(), 'h3cx-pin');
    this.takeLinks = el('span', 'h3cx-links');
    this.takeLinks.append(this.takeOpen, this.takeDownload, this.pinButton);
    this.pinMenu = el('span', 'h3cx-links h3cx-pin-menu');
    this.pinMenu.hidden = true;
    views.append(this.fullButton, this.takeButton, this.switchButton, this.fullLinks, this.takeLinks, this.pinMenu);
    this.exportStatus = el('div', 'h3cx-export-status');
    this.exportStatus.setAttribute('role', 'status');
    this.exportProgress = el('progress');
    this.exportProgress.setAttribute('aria-label', 'Assembling video');
    this.exportMessage = el('span');
    this.exportStatus.append(this.exportProgress, this.exportMessage);
    this.exportStatus.hidden = true;
    const stage = this.stage = el('div', 'h3cx-stage');
    this.screen = el('div', 'h3cx-screen');
    this.badge = el('span', 'h3cx-badge');
    stage.append(this.screen, this.badge);
    this.hint = el('p', 'h3cx-hint', CORE_HINT);
    this.pinNote = el('p', 'h3cx-hint h3cx-pin-note');
    this.pinNote.setAttribute('aria-live', 'polite');
    this.pinNoteBox = null;
    this.soundtrackNote = el('p', 'h3cx-soundtrack');
    const player = el('section', 'h3cx-player');
    player.setAttribute('aria-label', 'Viewer');
    player.id = 'h3cx-page-viewer'; player.setAttribute('role', 'tabpanel');
    player.setAttribute('aria-labelledby', 'h3cx-tab-viewer');
    this.player = player;
    player.append(views, this.exportStatus, stage, this.hint, this.pinNote, this.soundtrackNote);

    this.library = el('aside', 'h3cx-library');
    this.library.id = 'h3cx-references';
    this.library.setAttribute('aria-label', 'References');
    const nav = el('nav', 'h3cx-library-nav');
    nav.setAttribute('role', 'tablist'); nav.setAttribute('aria-label', 'Workspace views');
    this.pageButtons = {};
    this.pages = {};
    for (const name of ['box', 'audio', 'text', 'timeline', ...FOCUS]) {
      this.pages[name] = el('div', 'h3cx-page');
      this.pages[name].dataset.page = name;
    }
    for (const name of CENTER) {
      const label = name === 'refmods' ? 'RefMods' : name[0].toUpperCase() + name.slice(1);
      this.pageButtons[name] = button(label, `Open ${label}`, () => name === 'viewer' ? this.backToViewer() : this.openFocus(name));
      this.pageButtons[name].setAttribute('role', 'tab');
      this.pageButtons[name].id = `h3cx-tab-${name}`;
      this.pageButtons[name].setAttribute('aria-controls', `h3cx-page-${name}`);
      if (this.pages[name]) {
        this.pages[name].id = `h3cx-page-${name}`; this.pages[name].setAttribute('role', 'tabpanel');
        this.pages[name].setAttribute('aria-labelledby', `h3cx-tab-${name}`);
      }
      this.pageButtons[name].addEventListener('keydown', event => {
        if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
        event.preventDefault();
        const index = CENTER.indexOf(name), next = event.key === 'Home' ? 0 : event.key === 'End' ? CENTER.length - 1
          : (index + (event.key === 'ArrowRight' ? 1 : -1) + CENTER.length) % CENTER.length;
        this.pageButtons[CENTER[next]].click(); this.pageButtons[CENTER[next]].focus();
      });
      nav.append(this.pageButtons[name]);
    }
    this.library.append(el('h2', 'h3cx-title', 'References'), this.pages.timeline);
    this.storyPage = el('div', 'h3cx-story-page');
    this.pages.story.append(this.storyEl, this.storyPage);
    this.inspector = el('section', 'h3cx-inspector');
    this.inspector.id = 'h3cx-inspector';
    this.inspector.setAttribute('aria-label', 'Inspector');
    this.inspectorTitle = el('h2', 'h3cx-title h3cx-inspector-title');
    this.clipPromptButton = button('Clip prompt', 'Inspect the selected clip’s prompt', () => {
      const editor = this.host?.editor;
      this.inspect({kind:'clip', box:editor?.box()?.id ?? null});
      editor?.focusClipPrompt();
    });
    this.clipPromptButton.setAttribute('aria-label', 'Inspect selected clip prompt');
    this.emptyInspector = el('p', 'h3cx-note h3cx-empty-inspector',
      'Start with + Clip in the Timeline, or open Story to write prompts.');
    this.inspector.append(this.inspectorTitle, this.clipPromptButton, this.emptyInspector, this.pages.box, this.pages.audio, this.pages.text);
    this.focus = el('section', 'h3cx-focus');
    this.focus.setAttribute('aria-label', 'Project focus');
    this.focusTitle = el('h2', 'h3cx-title');
    this.focusContext = el('span', 'h3cx-note');
    const focusHead = el('div', 'h3cx-focus-head');
    focusHead.append(this.focusTitle, this.focusContext);
    this.focusBody = el('div', 'h3cx-focus-body');
    this.focusBody.append(...FOCUS.map(name => this.pages[name]));
    this.pages.project.append(el('h3', 'h3cx-title', 'Shared prompt · applies to every clip'));
    this.projectPrompt = el('div', 'h3cx-project-prompt');
    this.projectChain = el('div');
    this.projectFiles = el('div', 'h3cx-project-files');
    this.projectFileNote = el('p', 'h3cx-note');
    this.generationButton=button('Start a new generation','Keep this Timeline and all previous videos, with every clip unrendered',()=>this.startGeneration());
    this.generationNote=el('p','h3cx-note');
    this.generationNote.setAttribute('aria-live','polite');
    this.generationHistory=el('div');
    this.pages.project.append(this.projectPrompt, this.projectChain, this.projectFiles, this.projectFileNote,
      el('h3','h3cx-title','Generations'),
      el('p','h3cx-note','Generate another version from the same Timeline and prompts. Previous videos and Takes are kept.'),
      this.generationButton,this.generationNote,this.generationHistory,
      el('p', 'h3cx-note', 'Each Clip is one generation box. Project JSON and backend messages keep the existing box names.'),
      el('p', 'h3cx-note', 'API keys and provider settings are on the linked H3 Story node in the graph. Open its API keys group to Save or Forget keys; advanced inputs hold model, thinking, Vision and memory settings.'),
      el('p', 'h3cx-note', 'Timeline name, width, height, context frames, carry audio and reference image size remain on the H3 Timeline node in the graph.'),
      button('Back to graph', 'Close Studio to edit the node settings', () => this.close()));
    this.focus.append(focusHead, this.focusBody);
    const center = el('section', 'h3cx-center');
    center.append(nav, player, this.focus);
    const main = el('div', 'h3cx-main');
    main.append(this.library, center, this.inspector);
    this.mobileMore = el('section', 'h3cx-mobile-more');
    this.mobileMore.setAttribute('aria-label', 'More Studio tools');
    this.mobileMore.append(el('h2', 'h3cx-title', 'Studio tools'));
    for (const page of FOCUS.filter(name => name !== 'project')) {
      const label = page === 'refmods' ? 'RefMods' : page[0].toUpperCase() + page.slice(1);
      this.mobileMore.append(button(label, `Open ${label}`, () => this.openFocus(page)));
    }
    main.append(this.mobileMore);
    this.mobileNav = el('nav', 'h3cx-mobile-nav');
    this.mobileNav.setAttribute('aria-label', 'Mobile Studio views');
    this.mobileButtons = {};
    for (const [page, label] of [['viewer','Viewer'],['clip','Clip'],['references','References'],['timeline','Timeline'],['more','More']]) {
      const control = this.mobileButtons[page] = button(label, `Open ${label}`, () => {
        if (page === 'viewer') this.backToViewer();
        else if (page === 'clip') this.setPage('box');
        else if (page === 'references') this.setReferencesVisible(true);
        else this.setMobilePage(page);
      });
      this.mobileNav.append(control);
    }
    this.track = el('footer', 'h3cx-track');
    this.track.setAttribute('aria-label', 'Timeline');
    const toolbar = el('div', 'h3cx-track-toolbar');
    this.zoomOut = button('−', 'Zoom the timeline out (Ctrl + scroll)', () => this.zoomBy(1 / 1.25), 'h3cx-zoom-out');
    this.zoomIn = button('+', 'Zoom the timeline in (Ctrl + scroll)', () => this.zoomBy(1.25), 'h3cx-zoom-in');
    this.zoomFit = button('Fit', 'Fit the whole timeline in the panel', () => this.setZoom(1), 'h3cx-zoom-fit');
    this.zoomOut.setAttribute('aria-label', 'Zoom timeline out');
    this.zoomIn.setAttribute('aria-label', 'Zoom timeline in');
    this.zoomText = el('output');
    const zoom = el('span', 'h3cx-zoom');
    zoom.setAttribute('role', 'group'); zoom.setAttribute('aria-label', 'Timeline zoom');
    zoom.append(this.zoomOut, this.zoomText, this.zoomIn, this.zoomFit);
    toolbar.append(el('h2', 'h3cx-title', 'Timeline'), this.actionsSlot, zoom);
    this.track.append(toolbar);
    main.append(this.splitter('lib', 'v', 'References width'), this.splitter('insp', 'v', 'Inspector width'));
    this.splitTrack = this.splitter('track', 'h', 'Timeline height');
    root.append(bar, this.notice, activity, main, this.splitTrack, this.track, this.mobileNav);
    this.applyLayout();
    // Ctrl + scroll over the lane zooms about the pointer; plain scroll still pans.
    this.track.addEventListener('wheel', (event) => {
      const lane = this.host?.editor.laneEl;
      if (!event.ctrlKey || !lane?.contains(event.target)) return;
      event.preventDefault();
      this.zoomBy(event.deltaY < 0 ? 1.15 : 1 / 1.15, event.clientX);
    }, {passive: false});
    this.setReferencesVisible(this.referencesVisible);
    this.setInspectorVisible(this.inspectorVisible);
    if (typeof ResizeObserver === 'function') new ResizeObserver(() => this.trackResized()).observe(this.track);
    this.setLibrary('references');
    this.setPage('box');
  }

  // Layout: pane sizes and the timeline zoom survive a refresh. Each is a size the user chose, never below the original.

  loadLayout() {
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(LAYOUT_KEY) ?? '{}') ?? {}; } catch { saved = {}; }
    const number = (value, min, max) => Number.isFinite(value) ? Math.min(max, Math.max(min, value)) : null;
    return {lib: number(saved.lib, 0, 4000), insp: number(saved.insp, 0, 4000), track: number(saved.track, TRACK_MIN, 4000),
      zoom: number(saved.zoom, 1, ZOOM_MAX) ?? 1};
  }

  saveLayout() {
    try { localStorage.setItem(LAYOUT_KEY, JSON.stringify(this.layout)); } catch { /* storage may be unavailable */ }
  }

  // The smallest and largest size of a pane right now; the minimums are the sizes it had before it could be resized.
  paneLimits(name) {
    const narrow = matchMedia('(max-width:1150px)').matches;
    if (name === 'track') return {min: TRACK_MIN, max: Math.max(TRACK_MIN, innerHeight * .7)};
    return {min: name === 'lib' ? (narrow ? 220 : 256) : (narrow ? 310 : 346), max: innerWidth * .4};
  }

  applyLayout() {
    const style = this.root.style;
    for (const [name, prop] of [['lib', '--h3cx-lib-w'], ['insp', '--h3cx-insp-w'], ['track', '--h3cx-track-h']]) {
      if (this.layout[name] == null) style.removeProperty(prop);
      else style.setProperty(prop, `${this.layout[name]}px`);
    }
    this.zoomText.textContent = `${Math.round(this.layout.zoom * 100)}%`;
    this.zoomOut.disabled = this.layout.zoom <= 1;
    this.zoomFit.disabled = this.layout.zoom === 1;
    this.zoomIn.disabled = this.layout.zoom >= ZOOM_MAX;
    this.applyLaneView();
  }

  applyLaneView() {
    this.host?.editor.setLaneView({zoom: this.layout.zoom});
  }

  splitter(name, axis, label) {
    const node = el('div', `h3cx-split h3cx-split-${axis} h3cx-split-${name}`);
    node.setAttribute('role', 'separator');
    node.setAttribute('aria-orientation', axis === 'v' ? 'vertical' : 'horizontal');
    node.setAttribute('aria-label', label);
    node.title = `${label} — drag, or use the arrow keys · double-click to reset`;
    node.tabIndex = 0;
    // Dragging right grows References and shrinks the Inspector; dragging up grows the Timeline.
    const sign = name === 'lib' ? 1 : -1;
    const size = () => {
      const rect = (name === 'track' ? this.track : name === 'lib' ? this.library : this.inspector).getBoundingClientRect();
      return axis === 'v' ? rect.width : rect.height;
    };
    const set = (value) => {
      const {min, max} = this.paneLimits(name);
      this.layout[name] = Math.round(Math.min(max, Math.max(min, value)));
      this.applyLayout();
    };
    node.addEventListener('pointerdown', (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      node.setPointerCapture(event.pointerId);
      node.classList.add('h3cx-dragging');
      const start = axis === 'v' ? event.clientX : event.clientY, base = size();
      const move = (e) => set(base + sign * ((axis === 'v' ? e.clientX : e.clientY) - start));
      const stop = () => {
        node.classList.remove('h3cx-dragging');
        node.removeEventListener('pointermove', move);
        node.removeEventListener('pointerup', stop);
        node.removeEventListener('pointercancel', stop);
        this.saveLayout();
      };
      node.addEventListener('pointermove', move);
      node.addEventListener('pointerup', stop);
      node.addEventListener('pointercancel', stop);
    });
    node.addEventListener('dblclick', () => {
      this.layout[name] = null;
      this.applyLayout();
      this.saveLayout();
    });
    node.addEventListener('keydown', (event) => {
      const grow = name === 'lib' ? 'ArrowRight' : name === 'insp' ? 'ArrowLeft' : 'ArrowUp';
      const shrink = name === 'lib' ? 'ArrowLeft' : name === 'insp' ? 'ArrowRight' : 'ArrowDown';
      if (event.key !== grow && event.key !== shrink) return;
      event.preventDefault();
      event.stopPropagation();
      set(size() + (event.key === grow ? 24 : -24));
      this.saveLayout();
    });
    return node;
  }

  setZoom(zoom, anchorX) {
    const lane = this.host?.editor.laneEl;
    const next = Math.min(ZOOM_MAX, Math.max(1, zoom));
    if (next === this.layout.zoom) return;
    // Keep the moment under the pointer (or the middle of the view) where it is while the lane grows or shrinks.
    let fraction = 0, offset = 0;
    if (lane) {
      const rect = lane.getBoundingClientRect();
      offset = anchorX == null ? rect.width / 2 : anchorX - rect.left;
      fraction = (lane.scrollLeft + offset) / (lane.scrollWidth || 1);
    }
    this.layout.zoom = next;
    this.applyLayout();
    if (lane) lane.scrollLeft = fraction * lane.scrollWidth - offset;
    this.saveLayout();
  }

  zoomBy(factor, anchorX) {
    this.setZoom(this.layout.zoom * factor, anchorX);
  }

  openNewProject() {
    if (!this.host || this.newProjectDialog?.open) return;
    const host = this.host;
    const dialog = this.newProjectDialog = el('dialog', 'h3cx-new-project');
    dialog.setAttribute('aria-labelledby', 'h3cx-new-project-title');
    dialog.append(Object.assign(el('h2', 'h3cx-title', 'New project'), {id:'h3cx-new-project-title'}),
      el('p', null, "Start a new project in this workflow with a short project name. Timeline clips, Cast, generated Story results and selected references are cleared. Uploaded pictures, connected images and audio, your idea, guide and other Story inputs stay available so you can write a new story immediately. Generated files are kept."),
      el('p', null, 'Unapplied form drafts for the old Timeline are cleared.'));
    const message = el('p', 'h3cx-note');
    message.setAttribute('aria-live', 'polite');
    const cancel = button('Cancel', 'Keep this project open', () => dialog.close());
    const create = button('Create project', 'Reset this Timeline inside the current workflow', async () => {
      create.disabled = true;
      try {
        await host.newProject();
        dialog.close();
      } catch (error) {
        dialog.close();
        dialog.remove();
        this.newProjectDialog = null;
        this.showProjectError(error);
      }
    });
    const reason = host.newProjectBusy?.();
    message.textContent = reason ?? '';
    create.disabled = !!reason;
    dialog.append(message, cancel, create);
    dialog.addEventListener('close', () => { dialog.remove(); this.newProjectDialog = null; });
    this.root.append(dialog);
    dialog.showModal();
    cancel.focus();
  }

  async startGeneration() {
    if(!this.host||this.startingGeneration)return;
    const host=this.host;
    this.startingGeneration=true;this.generationButton.disabled=true;this.generationNote.textContent='';
    try {
      const started=await host.startGeneration();
      if(started&&host===this.host){this.generationNote.textContent='New generation ready. Every clip is unrendered; use Render to begin.';await this.loadGenerations();}
    } catch(error){if(host===this.host)this.generationNote.textContent=error.message;}
    finally{this.startingGeneration=false;this.generationButton.disabled=false;}
  }

  async loadGenerations() {
    const host=this.host, name=host?.sequenceName?.();
    if(!host)return;
    if(this.generationHistoryContext?.host!==host||this.generationHistoryContext?.name!==name){
      this.generationHistory.replaceChildren();
      this.generationHistoryContext={host,name};
    }
    try {
      const result=await host.generationHistory();
      if(host!==this.host||name!==host.sequenceName())return;
      if(!result.ok)throw new Error(result.error??'Previous generations are unavailable.');
      this.generationHistory.replaceChildren();
      if(!result.generations.length)return;
      this.generationHistory.append(el('h4','h3cx-title','Previous generations'));
      for(const generation of result.generations){
        const group=el('details');
        group.append(el('summary',null,`${new Date(generation.created).toLocaleString()} · ${generation.clips.length} clips`));
        const links=el('div','h3cx-links');
        for(const [label,file] of [...(generation.video?[['Joined video',generation.video]]:[]),
          ...generation.clips.map(clip=>[`Clip ${clip.number}`,clip.file])]){
          const link=el('a',null,label);link.href=host.viewUrl(file);link.target='_blank';link.rel='noopener';links.append(link);
        }
        if(!generation.video&&!generation.clips.length)links.append(el('p','h3cx-note','No saved videos in this generation.'));
        group.append(links);this.generationHistory.append(group);
      }
    }catch(error){if(host===this.host&&name===host.sequenceName())this.generationNote.textContent=error.message;}
  }

  showProjectError(error) {
    const dialog = this.projectErrorDialog = el('dialog', 'h3cx-new-project');
    dialog.setAttribute('aria-labelledby', 'h3cx-project-error-title');
    const message = el('p', null, error?.message ?? String(error));
    message.setAttribute('role', 'alert');
    dialog.append(Object.assign(el('h2', 'h3cx-title', 'New project failed'), {id:'h3cx-project-error-title'}), message);
    dialog.append(button('Back to graph', 'Dismiss the error and return to ComfyUI’s workflow tabs', () => { this.close(); dialog.close(); }));
    dialog.addEventListener('close', () => {
      dialog.remove();
      this.projectErrorDialog = null;
      (this.root.hidden ? document.querySelector('canvas') : this.root)?.focus();
    });
    document.body.append(dialog);
    dialog.showModal();
    dialog.querySelector('button').focus();
  }

  // With `link: false` the Cast page leaves boxes without a cast unlinked, as when the Studio follows an Undo.
  open(host, page, {link = true} = {}) {
    this.openRevision = (this.openRevision ?? 0) + 1;
    if (this.host && this.host !== host) this.close();
    const opening = this.root.hidden;
    const remembered = this.remembered?.host === host ? this.remembered.snapshot : null;
    if (this.root.hidden) {
      this.scrollBefore = [document.documentElement, document.body].map(node => ({node, overflow:node.style.overflow}));
      for (const {node} of this.scrollBefore) node.style.overflow = 'hidden';
      this.before = document.activeElement;
      if (!this.root.isConnected) document.body.append(this.root);
      this.root.hidden = false;
      this.cover?.(true);
    }
    if (this.host !== host) {
      this.giveBack();
      this.host = host;
      this.historySignature = null;
      this.libraryPage = 'references';
      this.focusPage = null;
      this.mobilePage = 'viewer';
      this.inspectorTarget = {kind:'clip', box:host.editor.box()?.id ?? null};
      this.view = this.chosen = this.candidate = this.bridgeBox = this.resumeAt = null;
      this.moving = false;
      this.pinMenu.hidden = true;
      this.pinNote.textContent = '';
      this.pinNoteBox = null;
      this.borrow();
      if (remembered) this.restoreSnapshot(remembered, {link:false});
    }
    if (page != null || !remembered) this.setPage(page ?? 'box', {link});
    if (opening && !remembered) this.setInspectorVisible(innerWidth >= 900);
    if (!['box', 'cast'].includes(this.page)) this.host.editor.cast?.refresh({link:page == null && remembered ? false : link});
    this.refresh();
    this.root.focus();
  }

  snapshot() {
    const editor = this.host?.editor;
    const video = this.screen.querySelector('video:not(.h3cx-live)');
    return {
      libraryPage:this.libraryPage, focusPage:this.focusPage, inspectorTarget:{...this.inspectorTarget},
      referencesVisible:this.referencesVisible,
      inspectorVisible:this.inspectorVisible,
      mobilePage:this.mobilePage,
      tab:editor?.activeTab ?? 'prompt', selectedBoxId:editor?.box()?.id ?? null,
      selectedIndex:editor?.selected ?? 0, view:this.view,
      chosen:this.chosen ? {...this.chosen, video:{...this.chosen.video}} : null,
      candidate:this.candidate ? {...this.candidate, file:{...this.candidate.file}} : null,
      bridgeBox:this.bridgeBox, resumeAt:video ? video.currentTime : this.resumeAt?.time ?? null,
    };
  }

  restoreSnapshot(snapshot, {link = false} = {}) {
    if (!this.host || !snapshot) return;
    const editor = this.host.editor, boxes = editor.state.boxes;
    const byId = boxes.findIndex(box => box.id === snapshot.selectedBoxId);
    const index = byId >= 0 ? byId : Math.max(0, Math.min(boxes.length - 1,
      Number.isInteger(snapshot.selectedIndex) ? snapshot.selectedIndex : 0));
    editor.select(index);
    editor.setTab(snapshot.tab ?? 'prompt');
    const box = editor.box(), fallback = {kind:'clip',box:box?.id ?? null};
    const target = snapshot.inspectorTarget;
    if (target?.kind === 'audio' && editor.audioLanes.clips.some(clip => clip.slot === target.slot)) {
      editor.audioLanes.selectAudio(target.slot);
      this.inspectorTarget = {...target};
    } else if (target?.kind === 'text' && editor.state.timed_text) {
      editor.audioLanes.selectText();
      this.inspectorTarget = {kind:'text'};
    } else this.inspectorTarget = fallback;
    this.setLibrary(snapshot.libraryPage ?? 'references', {link});
    const focus = snapshot.focusPage ?? (FOCUS.includes(snapshot.page) ? snapshot.page : null);
    if (FOCUS.includes(focus)) this.openFocus(focus, {link});
    else this.backToViewer();
    this.setReferencesVisible(snapshot.referencesVisible ?? true);
    this.setInspectorVisible(snapshot.inspectorVisible ?? innerWidth >= 900);
    this.setMobilePage(snapshot.mobilePage ?? (focus ? 'focus' : 'viewer'));
    const bridge = snapshot.bridgeBox;
    this.bridgeBox = box?.id === bridge && editor.state.bridges?.some(item => item.before === bridge)
      && (editor.status == null || editor.bridgeStatusOf(bridge)?.video) ? bridge : null;
    const chosen = snapshot.chosen;
    this.chosen = chosen?.box === box?.id && this.chosenAvailable(chosen) ? chosen : null;
    const candidate = snapshot.candidate;
    this.candidate = candidate?.box === box?.id && this.candidateAvailable(candidate) ? candidate : null;
    this.view = ['full','take','chosen','bridge','candidate'].includes(snapshot.view) ? snapshot.view : null;
    if ((this.view === 'chosen' && !this.chosen) || (this.view === 'bridge' && !this.bridgeBox)
      || (this.view === 'candidate' && !this.candidate)) this.view = 'take';
    const mediaValid = this.view === snapshot.view && (this.view === 'full' ? !editor.fullLink.hidden : this.view === 'chosen' ? !!this.chosen
      : this.view === 'bridge' ? !!this.bridgeBox : this.view === 'candidate' ? !!this.candidate
      : box?.id === snapshot.selectedBoxId && !!editor.statusOf(box)?.video);
    this.resumeAt = mediaValid && Number.isFinite(snapshot.resumeAt) && snapshot.resumeAt >= 0
      ? {time:snapshot.resumeAt,playing:false} : null;
    editor.cast?.refresh({link});
    this.refresh();
  }

  buildHistory() {
    const dialog = this.historyDialog = el('dialog', 'h3cx-history');
    dialog.setAttribute('aria-label', 'Timeline history');
    const head = el('div', 'h3cx-history-head');
    head.append(el('h2', 'h3cx-title', 'History'), button('Close', 'Close history', () => dialog.close()));
    this.historyList = el('ol', 'h3cx-history-list');
    dialog.append(head, el('p', 'h3cx-note',
      'Choose a state to restore it. Editing after a jump replaces the later steps. The latest 100 edits are kept for this session.'),
      this.historyList);
    dialog.addEventListener('keydown', event => {
      event.stopPropagation();
      const action = historyShortcut(event);
      if (action) { event.preventDefault(); this.host?.[action](); }
    });
    this.root.append(dialog);
  }

  openHistory() {
    if (!this.host) return;
    document.activeElement?.blur?.();
    this.host.history.endGroup();
    this.historyDialog.showModal();
    this.refreshHistory();
    this.historyList.querySelector('[aria-current="step"]')?.focus();
  }

  refreshHistory() {
    const history = this.host?.history;
    this.undoButton.disabled = !history?.canUndo;
    this.redoButton.disabled = !history?.canRedo;
    if (!this.historyDialog.open) return;
    // Status polling must not rebuild the list and steal keyboard focus.
    const signature = JSON.stringify([history.index, history.entries.map(({label, time}) => [label, time])]);
    if (signature === this.historySignature) return;
    this.historySignature = signature;
    const focused = this.historyList.contains(document.activeElement);
    this.historyList.replaceChildren(...history.entries.map((entry, index) => {
      const item = el('li', index > history.index ? 'h3cx-future' : '');
      const current = index === history.index;
      const control = button(`${index}. ${entry.label}${current ? ' · Current' : ''}`,
        new Date(entry.time).toLocaleTimeString(), () => {
          this.host.jumpHistory(index);
          this.historyList.querySelector('[aria-current="step"]')?.focus();
        });
      if (current) control.setAttribute('aria-current', 'step');
      item.append(control);
      return item;
    }));
    if (focused) this.historyList.querySelector('[aria-current="step"]')?.focus();
  }

  close() {
    if (this.root.hidden) return;
    this.historyDialog.close();
    this.host?.history.endGroup();
    this.trimmingPointer = null;
    this.focusedField = null;
    this.remembered = {host:this.host, snapshot:this.snapshot()};
    this.giveBack();
    this.root.hidden = true;
    this.cover?.(false);
    for (const {node, overflow} of this.scrollBefore ?? []) node.style.overflow = overflow;
    this.scrollBefore = null;
    // The editor's panel goes back to its node, so the Studio won't hear when a take that is moving lands.
    this.moving = false;
    const before = this.before;
    this.before = null;
    if (before?.isConnected && before !== document.body) before.focus();
  }

  setLibrary(page, {link = true} = {}) {
    this.libraryPage = LIBRARY.includes(page) ? page : 'references';
    if (this.libraryPage !== 'references') this.openFocus(this.libraryPage, {link});
    else this.setReferencesVisible(true);
  }

  setReferencesVisible(visible) {
    this.referencesVisible = !!visible;
    this.library.hidden = !this.referencesVisible;
    this.root.classList.toggle('h3cx-references-hidden', !this.referencesVisible);
    this.root.classList.toggle('h3cx-library-open', this.referencesVisible);
    this.libraryToggle.setAttribute('aria-expanded', String(this.referencesVisible));
    if (visible && (innerWidth < 900 || this.mobileMedia.matches) && this.inspectorVisible) this.setInspectorVisible(false);
    if (this.mobileMedia.matches && visible) this.setMobilePage('references');
    else if (this.mobilePage === 'references' && !visible) this.setMobilePage('viewer');
  }

  setInspectorVisible(visible) {
    this.inspectorVisible = !!visible;
    this.root.classList.toggle('h3cx-inspector-open', this.inspectorVisible);
    this.inspectorToggle.setAttribute('aria-expanded', String(this.inspectorVisible));
    if (visible && (innerWidth < 900 || this.mobileMedia.matches) && this.referencesVisible) this.setReferencesVisible(false);
    if (this.mobileMedia.matches && visible) this.setMobilePage('clip');
    else if (this.mobilePage === 'clip' && !visible) this.setMobilePage('viewer');
  }

  setMobilePage(page) {
    if (!['viewer','clip','references','timeline','more','focus'].includes(page)) return;
    if (page !== this.mobilePage) this.focusedField = null;
    this.mobilePage = page;
    this.renderMobile();
  }

  layoutChanged() {
    const field = this.focusedField ?? document.activeElement;
    const enteringMobile = this.mobileMedia.matches && !this.mobileLayout;
    this.mobileLayout = this.mobileMedia.matches;
    if (this.narrowMedia.matches && this.referencesVisible && this.inspectorVisible) this.setReferencesVisible(false);
    if (enteringMobile) {
      const editing = field?.matches('input, textarea, select');
      this.mobilePage = editing && this.inspector.contains(field) ? 'clip'
        : editing && this.library.contains(field) ? 'references' : this.focusPage ? 'focus' : 'viewer';
    }
    this.renderMobile();
    if (this.mobileMedia.matches && field?.isConnected && field.getClientRects().length && this.root.contains(field)
      && field.matches('input, textarea, select')) {
      field.focus({preventScroll:true});
      this.resizeViewport();
    }
    this.trackResized();
  }

  renderMobile() {
    if (!this.mobileNav) return;
    const mobile = this.mobileMedia.matches;
    this.root.dataset.mobilePage = this.mobilePage;
    this.mobileMore.hidden = !mobile || this.mobilePage !== 'more';
    this.activity.classList.toggle('h3cx-empty', !this.progressEl.textContent && !this.writerMessage.textContent && this.stopButton.hidden && !this.writerCancel.textContent);
    const actionParent = mobile ? this.mobileMore : this.bar;
    const feedbackParent = mobile ? this.mobileMore : this.activity;
    if (this.projectActions.parentNode !== actionParent) actionParent.append(this.projectActions);
    if (this.feedbackButton.parentNode !== feedbackParent) feedbackParent.append(this.feedbackButton);
    for (const [page, control] of Object.entries(this.mobileButtons))
      control.setAttribute('aria-pressed', String(page === (this.mobilePage === 'focus' ? 'more' : this.mobilePage)));
    this.root.style.setProperty('--h3cx-track-width', `${Math.max(480, (this.host?.editor.state.boxes.length ?? 0) * 96)}px`);
    const editor = this.host?.editor;
    if (editor) {
      editor.touchPan = mobile;
      editor.renderHint();
    }
    this.resizeViewport();
  }

  resizeViewport() {
    const viewport = window.visualViewport;
    if (!viewport || !this.mobileMedia.matches) return;
    this.root.style.setProperty('--h3cx-viewport-height', `${viewport.height}px`);
    this.root.style.setProperty('--h3cx-viewport-top', `${viewport.offsetTop}px`);
    const field = document.activeElement;
    if (this.root.contains(field) && field.matches('input, textarea, select')) field.scrollIntoView({block:'nearest'});
  }

  openFocus(page, {link = true} = {}) {
    if (!FOCUS.includes(page)) return;
    if(page==='project')this.loadGenerations();
    this.focusPage = page;
    this.libraryPage = page === 'project' ? 'references' : page;
    this.page = page;
    this.focusTitle.textContent = page === 'refmods' ? 'RefMods' : page === 'project' ? 'Project settings'
      : page[0].toUpperCase() + page.slice(1);
    if (page === 'story' && this.host) this.host.editor.feedbackEl.open = true;
    if (page === 'pictures' && this.host) this.host.editor.pictures.root.open = true;
    if (page === 'cast') this.host?.editor.cast?.refresh({link});
    if (this.mobileMedia.matches) this.setMobilePage('focus');
    // Below 900 px the Inspector and References float over the centre, where this page opens.
    else if (this.narrowMedia.matches) { this.setInspectorVisible(false); this.setReferencesVisible(false); }
    this.renderNavigation();
  }

  backToViewer() {
    this.focusPage = null;
    this.page = 'box';
    this.libraryPage = 'references';
    if (this.mobileMedia.matches) this.setMobilePage('viewer');
    this.renderNavigation();
  }

  inspect(target) {
    if (!target || !['clip', 'audio', 'text'].includes(target.kind)) return;
    this.inspectorTarget = target;
    if (this.trimmingPointer == null) this.setInspectorVisible(true);
    this.refresh();
  }

  setPage(page, {link = true} = {}) {
    if (FOCUS.includes(page)) return this.openFocus(page, {link});
    if (page === 'timeline') { this.backToViewer(); this.setLibrary('references'); return; }
    this.backToViewer();
    this.inspect({kind: 'clip', box: this.host?.editor.box()?.id ?? null});
    this.host?.editor.cast?.refresh({link});
  }

  renderNavigation() {
    const focused = !!this.focusPage;
    this.focus.hidden = !focused;
    this.player.hidden = focused;
    this.inspector.hidden = false;
    this.pages.timeline.hidden = false;
    for (const [name, control] of Object.entries(this.pageButtons)) {
      const selected = name === (this.focusPage ?? 'viewer');
      control.setAttribute('aria-pressed', String(selected)); control.setAttribute('aria-selected', String(selected));
      control.tabIndex = selected ? 0 : -1;
    }
    for (const name of FOCUS) this.pages[name].hidden = name !== this.focusPage;
    const target = this.inspectorTarget.kind;
    this.pages.box.hidden = target !== 'clip';
    this.pages.audio.hidden = target !== 'audio';
    this.pages.text.hidden = target !== 'text';
    const editor = this.host?.editor;
    this.clipPromptButton.hidden = target === 'clip' || !editor?.box();
    this.emptyInspector.hidden = target !== 'clip' || !!editor?.box();
    setText(this.inspectorTitle, target === 'audio' ? `Audio @${this.inspectorTarget.slot}`
      : target === 'text' ? 'Timed text' : editor?.box() ? `Clip ${editor.selected + 1}` : 'No clip selected');
    setText(this.focusContext, editor?.box() ? `Selected clip ${editor.selected + 1}` : 'No clip selected');
    this.renderMobile();
  }

  insertReference(text) {
    const editor = this.host?.editor;
    this.inspect({kind: 'clip', box: editor?.box()?.id ?? null});
    if (editor?.focusClipPrompt()) editor.insert(text);
  }

  setView(view) {
    this.view = view;
    if (this.mobileMedia.matches) this.backToViewer();
    this.refresh();
  }

  openFeedback() {
    if (!this.host) return;
    this.setPage('story');
    this.host.editor.feedbackInput.focus();
  }

  refresh() {
    if (this.root.hidden || !this.host) return;
    const host = this.host;
    this.refreshHistory();
    if (this.inspectorTarget.kind === 'clip')
      this.inspectorTarget = {kind: 'clip', box: host.editor.box()?.id ?? null};
    const watch = host.watch();
    this.showStory(host.story?.() ?? null);
    setText(this.nameEl, host.title());
    this.nameEl.title = host.sequenceName?.() ?? '';
    setText(this.progressEl, host.progress?.() ?? progressText(watch, host.runningBox(), (id) => host.titleOf(id)));
    this.stopButton.hidden = host.editor.host.projectAttached === true || !(watch.running && !watch.turn);
    this.feedbackButton.hidden = host.editor.feedbackEl.hidden;
    this.renderNavigation();
    const full = host.editor.fullLink.hidden ? null : host.editor.fullLink.getAttribute('href');
    const partial = full ? host.editor.partialVideo : null;
    const soFar = full ? host.editor.previewVideo : null;
    this.downloadVideo.disabled = !full;
    this.downloadVideo.title = partial ? `Download the partial video: ${partialTitle(partial)}`
      : soFar ? `Download the ${previewBadge(soFar).toLowerCase()}`
      : full ? 'Download the existing assembled full video' : 'No assembled full video is available yet.';
    this.downloadVideo.dataset.file = full ? host.editor.fullDownloadLink.download : '';
    const cancel = this.story?.panel?.cancelButton;
    if (cancel) {
      this.placeCancel(cancel, !!watch.turn || !cancel.hidden);
      if (!cancel.hidden) this.stopButton.hidden = true;
    }
    this.refreshPlayer(watch);
  }

  placeCancel(cancel, held) {
    if (held && !this.cancelBorrowed) {
      this.cancelBorrowed = [];
      this.place(cancel, this.writerCancel, this.cancelBorrowed);
    } else if (!held && this.cancelBorrowed) {
      this.restore(this.cancelBorrowed);
      this.cancelBorrowed = null;
    }
  }

  // Borrowing

  place(node, parent, borrowed = this.borrowed) {
    if (!node) return;
    // Pictures opens as a dedicated page; keep the graph's original disclosure state.
    borrowed.push({node, parent: node.parentNode, next: node.nextSibling, open: node === this.host?.editor.pictures?.root ? node.open : undefined});
    parent.append(node);
  }

  // Each part goes back in the reverse order it left, so every recorded next sibling is in place again.
  restore(borrowed) {
    for (const {node, parent, next, open} of [...borrowed].reverse()) {
      if (open !== undefined) node.open = open;
      if (!parent) node.remove();
      else parent.insertBefore(node, next?.parentNode === parent ? next : null);
    }
  }

  borrow() {
    const regions = this.host.editor.regions();
    this.place(regions.summary, this.summarySlot);
    this.place(this.host.savedBar, this.savedSlot);
    for (const name of ['add', 'next', 'all']) this.place(regions[name], this.actionsSlot);
    this.place(regions.open, this.fullLinks);
    this.place(regions.download, this.fullLinks);
    this.place(regions.panel, this.pages.box);
    this.place(regions.cast, this.pages.cast);
    this.place(regions.feedback, this.pages.story);
    this.place(regions.references, this.pages.timeline);
    this.place(regions.pictures, this.pages.pictures);
    this.place(regions.refmods, this.pages.refmods);
    this.place(regions.sharedPrompt, this.projectPrompt);
    this.place(regions.chainSettings, this.projectChain);
    this.place(regions.readOnly, this.notice);
    this.place(regions.stillPrompts, this.track);
    this.place(regions.lane, this.track);
    this.place(regions.hint, this.track);
    this.place(regions.audioSettings, this.pages.audio);
    this.place(regions.dialogueSettings, this.pages.audio);
    this.place(regions.timedTextSettings, this.pages.text);
    regions.references.open = true;
    regions.refmods.open = true;
    regions.chainSettings.open = true;
    this.setLibrary('references');
    this.trackWidth = this.track.clientWidth;
    this.applyLaneView();
    this.host.editor.renderTrack();
  }

  giveBack() {
    this.returnStory();
    this.restore(this.borrowed);
    this.borrowed = [];
    this.endLive();
    this.setScreen();
    const editor = this.host?.editor;
    editor?.setLaneView();
    this.host = null;
    this.trackWidth = 0;
    if (editor) editor.touchPan = false;
    editor?.renderTrack();
    editor?.renderHint();
  }

  trackResized() {
    const width = this.track.clientWidth;
    if (!this.host || !width || width === this.trackWidth) return;
    this.trackWidth = width;
    this.host.editor.renderTrack();
  }

  // Story

  showStory(story) {
    if (story === this.story) return;
    this.returnStory();
    this.story = story;
    if (!story) {
      this.projectFileNote.textContent = 'Save or open this project using ComfyUI’s native workflow Save/Open controls. Project JSON export requires a linked H3 Story.';
      this.storyEl.replaceChildren(this.writeOff);
      this.storyPage.replaceChildren(el('p', 'h3cx-note', NO_STORY));
      return;
    }
    this.place(story.panel.actionsEl, this.storyEl, this.storyBorrowed);
    this.place(story.panel.messageEl, this.writerMessage, this.storyBorrowed);
    this.storyPage.replaceChildren(this.inputsOf(story));
    if(story.panel.libraryEl){this.place(story.panel.libraryEl,this.storyPage,this.storyBorrowed);this.storyPage.prepend(story.panel.libraryEl);}
    this.place(story.panel.storyEl, this.pages.story, this.storyBorrowed);
    this.place(story.panel.filesEl, this.projectFiles, this.storyBorrowed);
    this.projectFileNote.textContent = 'Project JSON includes workflow wiring. Media and RefMods remain file references.';
  }

  returnStory() {
    if (this.cancelBorrowed) { this.restore(this.cancelBorrowed); this.cancelBorrowed = null; }
    this.restore(this.storyBorrowed);
    this.storyBorrowed = [];
    this.storyEl.replaceChildren();
    this.storyPage.replaceChildren();
    this.story = undefined;
  }

  inputsOf(story) {
    const form = el('div', 'h3cx-inputs');
    const advanced = el('details', 'h3cx-story-advanced');
    const advancedInputs = el('div', 'h3cx-inputs');
    advanced.append(el('summary', null, 'Advanced'), advancedInputs);
    story.panel.refreshSettings?.();
    for (const input of story.inputs()) {
      const parent = input.advanced ? advancedInputs : form;
      const shared = story.panel.settingField?.(input.name);
      if (shared) { this.place(shared, parent, this.storyBorrowed); continue; }
      const label = el('span', 'h3cx-label', input.label);
      if (input.linked != null) {
        const field = el('div', 'h3cx-field');
        field.title = input.tooltip ?? '';
        field.append(label, el('p', 'h3cx-linked', `Linked from ${input.linked}`));
        parent.append(field);
        continue;
      }
      const check = input.kind === 'boolean';
      const field = el(['template', 'images'].includes(input.kind) ? 'div' : 'label', check ? 'h3cx-field h3cx-check' : 'h3cx-field');
      const control = this.control(input, (value) => story.setInput(input.name, value));
      field.title = control.title = input.tooltip ?? '';
      control.setAttribute('aria-label', input.label);
      field.append(...(check ? [control, label] : [label, control]));
      parent.append(field);
    }
    if (advancedInputs.childElementCount) form.append(advanced);
    return form;
  }

  control(input, set) {
    if (input.kind === 'images') return ideaImagesRow(input, set);
    if (input.kind === 'template') return templateRow(input, set);
    if (input.kind === 'string') {
      const node = Object.assign(el('input'), {type: 'text', value: input.value ?? ''});
      node.addEventListener('input', () => set(node.value));
      return node;
    }
    if (input.kind === 'text') {
      const node = el('textarea');
      node.rows = 4;
      node.value = input.value ?? '';
      node.addEventListener('input', () => set(node.value));
      return node;
    }
    if (input.kind === 'number') {
      const node = Object.assign(el('input'), {type: 'number', min: input.min, max: input.max, step: 1, value: input.value ?? 0});
      node.addEventListener('change', () => {
        const value = Math.round(Number(node.value));
        if (!Number.isFinite(value)) return;
        node.value = Math.min(input.max, Math.max(input.min, value));
        set(Number(node.value));
      });
      return node;
    }
    if (input.kind === 'combo') {
      const node = el('select');
      const options = input.value == null || input.options.includes(input.value) ? input.options : [input.value, ...input.options];
      node.append(...options.map((option) => Object.assign(el('option', null, option), {value: option})));
      node.value = input.value;
      node.addEventListener('change', () => set(node.value));
      return node;
    }
    const node = Object.assign(el('input'), {type: 'checkbox', checked: input.value !== false});
    node.addEventListener('change', () => set(node.checked));
    return node;
  }

  // Keys: Esc leaves a field first, then a mention card, then the Studio. Plain keys stay inside the Studio,
  // so ComfyUI's canvas shortcuts (Delete, Backspace and the rest) do not act on the graph behind it.
  key(event) {
    if (this.newProjectDialog?.open) {
      event.stopPropagation();
      if (event.key === 'Escape') { event.preventDefault(); this.newProjectDialog.close(); }
      return;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      const field = event.target.closest?.('input, textarea, select, [contenteditable]:not([contenteditable="false"])');
      if (!this.pinMenu.hidden) this.pinMenu.hidden = true;
      else if (this.host?.editor.card.root.isConnected) this.host.editor.card.hide();
      else if (this.host?.editor.clipActions?.open) this.host.editor.clipActions.open = false;
      else if (field) {
        field.blur();
        this.root.focus();
      } else if (this.focusPage) this.backToViewer();
      else if (this.mobileMedia.matches && this.mobilePage !== 'viewer') this.backToViewer();
      else this.close();
      return;
    }
    const action = historyShortcut(event);
    if (action) {
      event.preventDefault();
      event.stopPropagation();
      this.host?.[action]();
      return;
    }
    if (!event.ctrlKey && !event.metaKey && !event.altKey) event.stopPropagation();
  }

  // Player

  // A take may reopen before its list arrives. Retain that provisional descriptor,
  // then reconcile only a successful, idle list for its owner. Failed/busy or
  // another clip's results do not establish that a file has been deleted.
  chosenAvailable(chosen) {
    const editor = this.host.editor;
    if (!chosen?.video?.filename || !editor.state.boxes.some(box => box.id === chosen.box)
      || (chosen.bridge && !editor.state.bridges?.some(bridge => bridge.before === chosen.box))) return false;
    const list = editor.takes.list;
    if (list?.box !== chosen.box || !list.found || list.found.ok === false || list.found.busy) return true;
    const section = list.found[chosen.bridge ? 'bridge' : 'box'];
    if (list.found.ok !== true && !Array.isArray(section?.takes)) return true;
    return (section?.takes ?? []).some(take => take.video?.filename === chosen.video.filename
      && take.video?.subfolder === chosen.video.subfolder && take.video?.type === chosen.video.type);
  }

  // A candidate stays playable while the status lists one of its files; before the status arrives it is kept.
  candidateAvailable(candidate) {
    const editor = this.host.editor;
    if (!candidate?.file?.filename || !editor.state.bridges?.some(bridge => bridge.before === candidate.box)) return false;
    if (editor.status == null) return true;
    const same = file => file?.filename === candidate.file.filename && file?.subfolder === candidate.file.subfolder;
    return (editor.bridgeStatusOf(candidate.box)?.candidates ?? []).some(item =>
      [item.video, item.preview?.file, item.preview?.original].some(same));
  }

  // The full video from `start` to `end` seconds: a replacement's region with a second either side.
  playRegion({start, end} = {}) {
    if (!Number.isFinite(start) || !Number.isFinite(end)) return;
    this.setView('full');
    const video = this.screen.querySelector('video:not(.h3cx-live)');
    if (!video) return;
    const stop = () => {
      if (video.currentTime < end) return;
      video.pause();
      video.removeEventListener('timeupdate', stop);
    };
    video.currentTime = start;
    video.addEventListener('timeupdate', stop);
    video.addEventListener('seeking', () => {
      if (video.currentTime < start || video.currentTime > end) video.removeEventListener('timeupdate', stop);
    });
    video.play().catch(() => {});
  }

  refreshPlayer(watch) {
    const {editor} = this.host;
    const box = editor.box();
    if (this.candidate && (this.candidate.box !== box?.id || !this.candidateAvailable(this.candidate))) {
      this.candidate = null;
      if (this.view === 'candidate') this.view = 'take';
    }
    if (this.chosen && !this.chosenAvailable(this.chosen)) {
      this.chosen = this.resumeAt = null;
      if (this.view === 'chosen') {
        this.view = 'take';
        this.setScreen();
      }
    }
    // The bridge view plays the take of the selected box's bridge; while the status is fetched again it keeps it.
    if (this.view === 'bridge' && (box?.id !== this.bridgeBox
      || (editor.status != null && !editor.bridgeStatusOf(this.bridgeBox)?.video))) this.view = 'take';
    // A chosen take plays only while its box is selected.
    const chosen = box && this.chosen?.box === box.id ? this.chosen : null;
    if (this.view === 'chosen' && !chosen) this.view = 'take';
    const entry = this.view === 'bridge' ? editor.bridgeStatusOf(this.bridgeBox) : box ? editor.statusOf(box) : null;
    const take = this.view === 'chosen' ? chosen.video : this.view === 'candidate' ? this.candidate.file
      : entry?.video?.file ?? null;
    const takeUrl = take ? this.host.viewUrl(take) : null;
    const fullUrl = editor.fullLink.hidden ? null : editor.fullLink.getAttribute('href');
    const partial = fullUrl ? editor.partialVideo : null;
    // The video so far plays once asked for; the take of the selected clip stays the default while clips render.
    const soFar = fullUrl ? editor.previewVideo : null;
    const building = !!(editor.status?.preview_video_building || editor.status?.full_video_building);
    const exportError = editor.status?.preview_error || editor.status?.export_error || '';
    const previewPending = !!(editor.status?.preview_video_building || editor.status?.preview_error);
    const exportName = previewPending ? 'video so far' : 'full video';
    setText(this.exportMessage, building ? `${fullUrl ? 'Updating' : 'Building'} the ${exportName}…`
      : exportError);
    this.exportProgress.hidden = !building;
    this.exportStatus.hidden = !this.exportMessage.textContent;
    const view = this.view ?? (fullUrl && !soFar ? 'full' : 'take');
    this.fullButton.setAttribute('aria-pressed', String(view === 'full'));
    this.takeButton.setAttribute('aria-pressed', String(view === 'take'));
    setText(this.takeButton, box ? `Clip ${editor.selected + 1} · active take` : 'Clip take');
    this.fullButton.disabled = !fullUrl;
    this.fullButton.setAttribute('aria-busy', String(building));
    setText(this.fullButton, soFar ? previewLabel(soFar) : previewPending
      ? `Video so far · ${building ? 'building…' : 'unavailable'}` : 'Full video');
    this.fullButton.title = partial ? `Play the partial video: ${partialTitle(partial)}`
      : soFar ? previewTitle(soFar)
      : fullUrl ? 'Play the whole Timeline'
      : this.exportMessage.textContent || 'No video yet: render the first clip to watch the video so far.';
    this.takeButton.disabled = !box;
    const inUse = chosen?.bridge ? editor.bridgeStatusOf(chosen.box) : chosen ? editor.statusOf(box) : null;
    this.switchButton.hidden = !inUse?.video || !['chosen', chosen.bridge ? 'bridge' : 'take'].includes(view);
    setText(this.switchButton, view === 'chosen' ? 'Compare with active take' : 'Back to selected take');
    this.switchButton.title = view === 'chosen' ? 'Play the take in use from the same moment'
      : 'Play the chosen take from the same moment';
    this.fullLinks.hidden = view !== 'full';
    this.takeLinks.hidden = view === 'full' || !takeUrl;
    for (const node of [this.takeOpen, this.takeDownload]) {
      if (takeUrl) node.href = takeUrl;
      else node.removeAttribute('href');
    }
    if (takeUrl) this.takeDownload.download = take.filename;
    else this.takeDownload.removeAttribute('download');

    const runningBox = this.host.runningBox();
    const preview = watch.running && box && runningBox === editor.selected + 1 ? watch.preview : null;
    const pinnable = view === 'take' && !!takeUrl && entry.status === 'done' && !preview
      && editor.cast.pinTargets(editor.selected).length > 0;
    this.pinButton.hidden = !pinnable;
    if (!pinnable || this.pinMenu.dataset.box !== box.id) this.pinMenu.hidden = true;
    if (this.pinNoteBox !== box?.id) [this.pinNoteBox, this.pinNote.textContent] = [null, ''];
    this.pinNote.hidden = !this.pinNote.textContent;
    setText(this.soundtrackNote, view === 'full' ? soundtrackLine(soundtrackSlots(editor.state)) : '');
    this.soundtrackNote.hidden = !this.soundtrackNote.textContent;
    this.hint.hidden = preview?.source !== 'core';
    if (preview) {
      this.showLive(preview);
      setText(this.badge, liveBadge(watch, runningBox));
    } else if (this.moving) {
      this.endLive();
      this.showMessage(MOVING);
      setText(this.badge, '');
    } else {
      this.endLive();
      // While the status is being fetched again after an edit, the playing video stays as it is.
      if (editor.status == null && this.screen.querySelector('video:not(.h3cx-live)')) return;
      const src = view === 'full' ? fullUrl : takeUrl;
      // A video so far that grows while it plays carries on from the same moment.
      const playing = this.screen.querySelector('video:not(.h3cx-live)');
      if (view === 'full' && src && !this.resumeAt && playing?.dataset.view === 'full' && playing.getAttribute('src') !== src) {
        this.resumeAt = {time: playing.currentTime, playing: !playing.paused};
      }
      if (src) this.showVideo(src, {view, box: view === 'bridge' ? this.bridgeBox : box?.id ?? ''});
      else this.showMessage(view === 'full' ? (this.exportMessage.textContent
        || 'No video yet: render the first clip to watch the video so far.') : 'Not rendered yet');
      setText(this.badge, view === 'chosen' ? this.chosenLabel(chosen) : view === 'candidate' ? this.candidate.label
        : view === 'bridge'
        ? `Bridge before clip ${editor.selected + 1}${!entry || entry.status === 'done' ? '' : ' · older take'}`
        : view === 'take' && takeUrl && entry.status !== 'done' ? OLDER_TAKE
        : view === 'full' && partial ? partialBadge(partial)
        : view === 'full' && soFar ? previewBadge(soFar) : '');
    }
    this.badge.hidden = !this.badge.textContent;
  }

  chosenLabel(chosen) {
    const editor = this.host.editor;
    const prefix = chosen.bridge ? `Bridge before clip ${editor.selected + 1}` : `Clip ${editor.selected + 1}`;
    const list = editor.takes.list;
    const section = list?.box === chosen.box ? list.found?.[chosen.bridge ? 'bridge' : 'box'] : null;
    const sameFile = file => file?.filename === chosen.video.filename && file?.subfolder === chosen.video.subfolder
      && file?.type === chosen.video.type;
    const number = (section?.takes ?? []).findIndex(take => sameFile(take.video)) + 1;
    // A retained event can outlive a refreshed list; keep its descriptive label without inventing a take number.
    return number ? `${prefix} · take ${number}` : `${prefix} · ${chosen.label.replace(/^.*?take /i, 'take ')}`;
  }

  // Switch keeps the moment: the other take starts where this one is, playing if this one was.
  switchTake() {
    const video = this.screen.querySelector('video:not(.h3cx-live)');
    this.resumeAt = video ? {time: video.currentTime, playing: !video.paused} : null;
    if (this.view !== 'chosen') return this.setView('chosen');
    if (this.chosen.bridge) this.bridgeBox = this.chosen.box;
    this.setView(this.chosen.bridge ? 'bridge' : 'take');
  }

  // Before a take's files move, the player lets go of its video, which Windows would otherwise keep from moving.
  letGo() {
    this.moving = true;
    this.setScreen();
    this.refresh();
  }

  // A take's video taken off the screen stops loading first, so the server lets go of its file and the take can move.
  setScreen(...nodes) {
    for (const video of this.screen.querySelectorAll('video:not(.h3cx-live)')) {
      video.pause();
      video.removeAttribute('src');
      video.load();
    }
    this.screen.replaceChildren(...nodes);
    this.host?.editor.setPlayhead?.(null);
  }

  // The Timeline frame `video` shows: through the full video's clock, or from the start of the take's clip; a bridge
  // holds at the cut it plays across. Null for a candidate.
  timelineFrameOf(video) {
    const editor = this.host?.editor;
    if (!editor) return null;
    const time = video.currentTime || 0, view = video.dataset.view;
    if (view === 'full') return timelineFrame(editor.videoClock, time);
    const index = editor.state.boxes.findIndex((box) => box.id === video.dataset.box);
    if (index < 0 || !['take', 'chosen', 'bridge'].includes(view)) return null;
    const start = boxStart(editor.state, index);
    return view === 'bridge' ? start : start + Math.min(time * FPS, editor.state.boxes[index].frames);
  }

  syncPlayhead(video) {
    if (this.screen.firstElementChild !== video) return;
    this.host?.editor.setPlayhead?.(this.timelineFrameOf(video));
  }

  // The ruler moved the playhead to Timeline `frame`: the selected clip's take seeks there while the moment is inside
  // that clip; otherwise the video so far (or the full video) plays from there, or from its end when it stops sooner.
  seekTimeline(frame) {
    const editor = this.host?.editor;
    if (!editor || !Number.isFinite(frame)) return;
    const shown = this.screen.querySelector('video:not(.h3cx-live)');
    if (shown && ['take', 'chosen'].includes(shown.dataset.view)) {
      const index = editor.state.boxes.findIndex((box) => box.id === shown.dataset.box);
      const start = boxStart(editor.state, index);
      if (index >= 0 && frame >= start && frame < start + editor.state.boxes[index].frames) {
        shown.currentTime = (frame - start) / FPS;
        return;
      }
    }
    if (editor.fullLink.hidden) {
      editor.setPlayhead(frame);
      return;
    }
    let seconds = videoSeconds(editor.videoClock, frame);
    if (seconds == null) {
      const last = editor.videoClock?.[editor.videoClock.length - 1];
      seconds = last ? Math.max(0, last[0] + last[1] - 1) / FPS : 0;
    }
    if (shown?.dataset.view !== 'full') this.setView('full');
    const video = this.screen.querySelector('video:not(.h3cx-live)');
    if (video?.dataset.view === 'full') {
      video.currentTime = seconds;
      this.syncPlayhead(video);
    }
  }

  togglePins() {
    const {editor} = this.host;
    const box = editor.box();
    this.pinMenu.hidden = !this.pinMenu.hidden;
    if (this.pinMenu.hidden) return;
    this.pinMenu.dataset.box = box.id;
    this.pinMenu.replaceChildren(...editor.cast.pinTargets(editor.selected).map(({id, name}) =>
      button(name, `Pin this moment for ${name}`, () => this.pinFor(id, box.id))));
  }

  // The pin's frame is the paused time of the take, which holds only the box's own frames.
  async pinFor(entityId, boxId) {
    const {editor} = this.host;
    const video = this.screen.querySelector('video:not(.h3cx-live)');
    this.pinMenu.hidden = true;
    await editor.cast.pin(entityId, boxId, video?.currentTime ?? 0);
    [this.pinNoteBox, this.pinNote.textContent] = [boxId, editor.cast.note];
    this.refresh();
  }

  // `shown` is {view, box}: what the video is, for the playhead.
  showVideo(src, shown = {}) {
    const current = this.screen.firstElementChild;
    const resume = this.resumeAt;
    this.resumeAt = null;
    if (current?.matches('video:not(.h3cx-live)') && current.getAttribute('src') === src) {
      if (current.dataset.view !== (shown.view ?? '') || current.dataset.box !== (shown.box ?? '')) {
        Object.assign(current.dataset, {view: shown.view ?? '', box: shown.box ?? ''});
        this.syncPlayhead(current);
      }
      return;
    }
    const video = el('video');
    video.controls = true;
    video.preload = 'metadata';
    video.src = src;
    Object.assign(video.dataset, {view: shown.view ?? '', box: shown.box ?? ''});
    if (resume) [video.currentTime, video.autoplay] = [resume.time, resume.playing];
    // The playhead follows the video: on each frame while it plays, and whenever it seeks.
    const sync = () => this.syncPlayhead(video);
    for (const type of ['loadedmetadata', 'timeupdate', 'seeking', 'seeked']) video.addEventListener(type, sync);
    video.addEventListener('play', () => {
      const tick = () => {
        if (video.paused || !video.isConnected) return;
        sync();
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
    this.setScreen(video);
    sync();
  }

  showMessage(text) {
    const current = this.screen.firstElementChild;
    if (current?.matches('.h3cx-message') && current.textContent === text) return;
    this.setScreen(el('span', 'h3cx-message', text));
  }

  showLive(preview) {
    const moving = preview.mime === 'video/mp4';
    if (preview.source === 'kj') this.dropObjectUrl();
    const src = preview.source === 'kj' ? `data:${preview.mime};base64,${preview.data}` : this.objectUrl(preview.blob);
    let node = this.screen.firstElementChild;
    if (!node?.matches(moving ? 'video.h3cx-live' : 'img.h3cx-live')) {
      node = el(moving ? 'video' : 'img', 'h3cx-live');
      if (moving) Object.assign(node, {autoplay: true, loop: true, muted: true, playsInline: true});
      else node.alt = 'Live preview';
      this.setScreen(node);
    }
    if (node.getAttribute('src') !== src) node.src = src;
  }

  endLive() {
    if (this.screen.querySelector('.h3cx-live')) this.setScreen();
    this.dropObjectUrl();
  }

  objectUrl(blob) {
    if (this.blob !== blob) {
      this.dropObjectUrl();
      this.blob = blob;
      this.blobSrc = URL.createObjectURL(blob);
    }
    return this.blobSrc;
  }

  dropObjectUrl() {
    if (this.blobSrc) URL.revokeObjectURL(this.blobSrc);
    this.blob = null;
    this.blobSrc = null;
  }
}

let instance = null;

export function studio() {
  instance ??= new Studio();
  return instance;
}
