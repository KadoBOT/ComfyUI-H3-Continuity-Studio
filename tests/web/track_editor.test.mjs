import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {snapPlacement,visibleSpans,placeClip} from '../../web/h3c_track_editor.mjs';
const fixture=()=>JSON.parse(fs.readFileSync(new URL('../fixtures/timeline_tracks.json',import.meta.url)));
test('cross-track edges snap and Shift bypass preserves exact drag position',()=>{
 const s=fixture();let p=snapPlacement(s,{id:'C',track:'v2',start:49,end:97,tolerance:3});assert.equal(p.start,48);assert.equal(p.end,96);assert.equal(p.guide,48);
 p=snapPlacement(s,{id:'C',track:'v2',start:49,end:97,tolerance:3,bypass:true});assert.equal(p.start,49);assert.equal(p.guide,null);
});
test('placement rejects same-track collisions without partial edits',()=>{
 const s=fixture(),before=structuredClone(s);assert.throws(()=>placeClip(s,'C','v1',20),/overlap/);assert.deepEqual(s,before);
 placeClip(s,'C','v2',48);assert.equal(s.boxes[1].start,48);
});
test('combined row represents uppermost picture and lower return with stable IDs',()=>{
 const s=fixture();assert.deepEqual(visibleSpans(s).map(p=>[p.start,p.end,p.id]),[[0,24,'A'],[24,72,'C'],[72,120,'B']]);
});
