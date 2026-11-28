"""Compose independent tracks on their shared clock. Native generation and legacy sequence output stay separate."""
import copy
import math
import os
import threading
from fractions import Fraction

import av
import numpy as np
import torch
from comfy_api.latest._input_impl.video_types import set_video_color_properties
from PIL import Image, ImageDraw

from . import tracks, timeline as rules, media, store, stacks, audio_tracks, color
from .timing import FPS

_LOCK = threading.RLock()
_JOBS = {}


def edit_list(parsed, manifest, available=None):
    data = tracks.document(parsed)
    placements = tracks.placements(data)
    priority = {t['id']: i for i, t in enumerate(parsed.tracks)}
    result = []

    def append(start, end, output, sources, sound=None, bridge=None):
        row = dict(start=start, end=end, outputStart=output, outputEnd=output+end-start,
                   sources=sources, sound=sound, bridgeId=bridge)
        if result:
            last = result[-1]
            n = last['outputEnd']-last['outputStart']
            same = (last['outputEnd'] == output and last['sound'] == sound and last['bridgeId'] == bridge
                    and len(last['sources']) == len(sources)
                    and all(a['id'] == b['id'] and a['weight'] == b['weight'] and a['first']+n == b['first']
                            for a, b in zip(last['sources'], sources)))
            if same:
                last['end'] = end; last['outputEnd'] = row['outputEnd']
                return
        result.append(row)

    for span in tracks.output_spans(data):
        if span['bridgeId']:
            count = span['outputEnd']-span['outputStart']
            append(span['start'], span['start']+count, span['outputStart'],
                   [dict(id='bridge:'+span['bridgeId'], first=0, weight=1)], 'bridge:'+span['bridgeId'], span['bridgeId'])
            continue
        for frame in range(span['start'], span['end']):
            active = sorted((p for p in placements if p['start'] <= frame < p['end']), key=lambda p: priority[p['track']])
            sources, sound = [], None
            if active:
                top = active[-1]
                sources = [dict(id=top['id'], first=frame-top['start'], weight=1)]
                sound = top['id']
                for switch in parsed.overlap_switches:
                    a = next((p for p in active if p['id'] == switch['from']), None)
                    b = next((p for p in active if p['id'] == switch['to']), None)
                    if not a or not b or top['id'] not in (a['id'], b['id']):
                        continue
                    weight = rules.layers.weight(switch, dict(at=switch['at']), frame)
                    sources = [dict(id=a['id'], first=frame-a['start'], weight=1-weight),
                               dict(id=b['id'], first=frame-b['start'], weight=weight)]
                    sources = [s for s in sources if s['weight'] > 0]
                    sound = switch['sound'] if switch['sound'] != 'screen' else (b['id'] if frame >= switch['at'] else a['id'])
                    break
            append(frame, frame+1, span['outputStart']+frame-span['start'], sources, sound)
    return result


def _entries(manifest):
    found = {store.box_of(e): e for e in manifest['segments']}
    found.update({'bridge:'+e['box']: e for e in manifest.get('bridges', [])})
    return found


def fingerprint(folder, parsed, manifest, mode, crf=16):
    stamps = []
    for entry in [*manifest['segments'], *manifest.get('layers', []), *manifest.get('bridges', [])]:
        video = entry.get('video') or {}
        files = [video.get('file')]
        overlap_file = (video.get('overlap') or {}).get('file')
        if overlap_file:
            files.append(overlap_file)
        if entry.get('audio_sample_rate'): files.append(entry['stem']+'.safetensors')
        for file in files:
            if not file: continue
            try:
                stat = os.stat(os.path.join(folder, file))
                stamps.append([file, stat.st_size, stat.st_mtime_ns])
            except OSError:
                stamps.append([file, None])
    source=manifest.get('source') or {}
    for file in [source.get('file'),source.get('audio')]:
        if not file: continue
        try:
            stat=os.stat(os.path.join(folder,file));stamps.append([file,stat.st_size,stat.st_mtime_ns])
        except OSError: stamps.append([file,None])
    soundtrack = audio_tracks.marked(parsed, manifest.get('reference_audio'))
    return rules._digest(dict(layout=tracks.document(parsed), layers=parsed.layers, switches=parsed.switches,
                              stamps=stamps, soundtrack=audio_tracks.soundtrack_sources(soundtrack), mode=mode, crf=crf))


def _missing(folder, parsed, row, entries):
    needs = [(s['id'], s['first']) for s in row['sources']]
    if row['sound'] and row['sound'] not in [n for n, _ in needs]:
        p = parsed.placements.get(row['sound'])
        needs.append((row['sound'], row['start']-p['start'] if p else 0))
    count = row['outputEnd']-row['outputStart']
    for identity, first in needs:
        entry = entries.get(identity)
        if not entry or not entry.get('video') or not os.path.isfile(os.path.join(folder, entry['video']['file'])):
            return identity
        if first+count > store.played_frames(entry): return identity
    return None


def _track_frames(path, picks, size, source_space):
    """Decode picked frames of `path` to sRGB uint8 [H, W, 3] at `size`, using BT.709/BT.2020 matrix and
    converting HDR sources through `color.convert`."""
    hdr = source_space in color.HDR_SPACES
    src_cs = 'bt2020' if hdr else 'itu709'
    fmt = 'rgb48le' if hdr else 'rgb24'
    position, last = 0, None
    with av.open(path) as container:
        for number, frame in enumerate(container.decode(video=0)):
            if position >= len(picks):
                break
            if number < picks[position]:
                continue
            arr = frame.reformat(width=size[0], height=size[1], format=fmt, src_colorspace=src_cs).to_ndarray()
            if hdr:
                rgb = color.convert(torch.from_numpy(arr.astype(np.float32) / 65535.0), source_space, 'sRGB')
                last = (rgb * 255.0).round().clamp(0, 255).to(torch.uint8).numpy()
            else:
                last = arr
            while position < len(picks) and picks[position] == number:
                yield last
                position += 1
    if last is None:
        raise ValueError(f'{os.path.basename(path)} has no frames')
    for _ in range(position, len(picks)):
        yield last


def build(folder, name, parsed, manifest, crf, mode='full'):
    """Write a CPU-composed movie, return its record and a user-facing note. Does not mutate the manifest."""
    key = fingerprint(folder, parsed, manifest, mode, crf)
    view = manifest
    if parsed.layers:
        view, waiting = stacks.substitute(folder, parsed, manifest, len(parsed.boxes), crf, partial=mode!='full')
        if waiting and mode == 'full': return None, ' '.join(waiting)
    entries = _entries(view)
    source=manifest.get('source')
    if mode=='partial' and source:
        entries['source']=dict(stem=name+'_source',frames=source['frames'],context_frames=0,
                               video=dict(file=source['file'],fps=24),audio_sample_rate=None)
    spans, rows = edit_list(parsed, view), []
    note = ''
    for row in spans:
        missing = _missing(folder, parsed, row, entries)
        if missing:
            note = f'Missing footage for clip {missing} at {row["start"]/FPS:.2f} s.'
            if mode == 'full': return None, note
            if mode == 'so_far': break
            if source and row['end']<=source['frames'] and os.path.isfile(os.path.join(folder,source['file'])):
                row={**row,'sources':[dict(id='source',first=row['start'],weight=1)],'sound':'source'}
            else:
                row = {**row, 'sources': [], 'sound': None, 'missing': missing}
        rows.append(row)
    if not rows: return None, note or 'No visible footage is ready.'
    used = {s['id'] for row in rows for s in row['sources']}
    sig_by_id = {identity: media._signature(os.path.join(folder, entries[identity]['video']['file'])) for identity in used}
    width = min((s[2] for s in sig_by_id.values()), default=256)
    height = min((s[3] for s in sig_by_id.values()), default=144)
    out_fps = max((float((entries[s].get('video') or {}).get('fps') or FPS)
                   for s in used if s in entries and entries[s].get('video')), default=float(FPS))
    out_rate = Fraction(FPS) if abs(out_fps - FPS) < 1e-3 else Fraction(str(round(out_fps, 6)))
    k_mult = media._fps_multiplier(out_fps)
    decay_len = max(1, round(media.OVERLAP_EXPOSURE_DECAY_SECONDS * out_fps))
    box_index = {box.id: idx for idx, box in enumerate(parsed.boxes)}
    picks = {identity: [] for identity in used}
    row_out_counts = []
    for row in rows:
        out_start, out_count = media.window_at_fps(row['outputStart'], row['outputEnd'] - row['outputStart'], out_fps)
        row_out_counts.append(out_count)
        for source in row['sources']:
            fps = entries[source['id']]['video'].get('fps') or FPS
            fps_frac = Fraction(str(round(float(fps), 6)))
            total_src = max(1, int(entries[source['id']]['video'].get('frames') or 0) or 10**9)
            for out_f in range(out_count):
                tl_offset = (Fraction(out_start + out_f) + Fraction(1, 2)) * Fraction(FPS) / out_rate - Fraction(row['outputStart'])
                src_idx = min(total_src - 1, max(0, int((Fraction(source['first']) + tl_offset) * fps_frac / Fraction(FPS))))
                picks[source['id']].append(src_idx)
    streams = {identity: _track_frames(os.path.join(folder, entries[identity]['video']['file']), frames,
                                       (width, height), sig_by_id[identity][5]) for identity, frames in picks.items()}
    source_sound=None
    if source and source.get('audio'):
        from safetensors import safe_open
        with safe_open(os.path.join(folder,source['audio']),framework='pt') as stream:
            source_sound=(stream.get_tensor('waveform'),int(stream.metadata()['sample_rate']))
    sound_items = []
    prev_sound_id = None
    for row in rows:
        count = row['outputEnd']-row['outputStart']
        entry = entries.get(row['sound'])
        wave = store.load_waveform(folder, entry) if entry and entry.get('audio_sample_rate') else None
        p = parsed.placements.get(row['sound'])
        first = row['start']-p['start'] if p else 0
        rate=entry.get('audio_sample_rate') if wave is not None else None
        is_source = row['sound']=='source' and source_sound
        if is_source:
            wave,rate=source_sound;first=row['start']
        break_seam = bool(row.get('bridgeId') or is_source or entry is None)
        continues_prev = (not break_seam and prev_sound_id in box_index and row['sound'] in box_index
                          and not parsed.boxes[box_index[row['sound']]].cut
                          and rules.previous_index(parsed, box_index[row['sound']]) == box_index[prev_sound_id])
        played = store.played_frames(entry) if entry is not None and not break_seam else None
        sound_items.append((None if is_source else entry, first, count, played, wave, rate, break_seam, continues_prev))
        prev_sound_id = None if break_seam else row['sound']
    sound = media.assemble_entry_audio(sound_items)
    soundtrack = audio_tracks.marked(parsed, manifest.get('reference_audio'))
    if soundtrack:
        coverage = [dict(frames=row['outputEnd']-row['outputStart'], coverage=[] if row['bridgeId'] else
                         [dict(box=s['id'], first=s['first'], frames=row['outputEnd']-row['outputStart']) for s in row['sources'][:1]]) for row in rows]
        sound = audio_tracks.soundtrack_audio(soundtrack, coverage)
    filename = f'tracks@{key}.mp4'
    path = os.path.join(folder, filename)
    temporary = path+f'.{threading.get_ident()}.tmp.mp4'
    def _continuing_pair(prev_row, curr_row):
        if not prev_row or prev_row['bridgeId'] or curr_row['bridgeId']:
            return None
        if len(prev_row['sources']) != 1 or len(curr_row['sources']) != 1:
            return None
        psrc, csrc = prev_row['sources'][0], curr_row['sources'][0]
        if psrc['weight'] != 1 or csrc['weight'] != 1 or csrc['first'] != 0:
            return None
        pentry, centry = entries.get(psrc['id']), entries.get(csrc['id'])
        pidx, cidx = box_index.get(psrc['id']), box_index.get(csrc['id'])
        if not pentry or not centry or pidx is None or cidx is None:
            return None
        if rules.previous_index(parsed, cidx) != pidx or parsed.boxes[cidx].cut:
            return None
        if int(centry.get('context_frames') or 0) <= 0:
            return None
        if psrc['first'] + (prev_row['outputEnd'] - prev_row['outputStart']) != store.played_frames(pentry):
            return None
        return centry if store.has_overlap_video(folder, centry) else None

    def _mux_span_frames(container, video_stream, span_frames):
        for arr in span_frames:
            frame = av.VideoFrame.from_ndarray(arr, format='rgb24')
            frame = frame.reformat(width=width, height=height, format=video_stream.pix_fmt,
                                   dst_colorspace=video_stream.codec_context.colorspace)
            set_video_color_properties(frame, 'sRGB')
            container.mux(video_stream.encode(frame))

    try:
        with av.open(temporary, mode='w') as container:
            video = media._add_video_stream(container, out_rate, width, height, crf, 'sRGB', 'H.264')
            audio = media._add_audio_stream(container, *sound) if sound is not None else None
            pending_frames = pending_row = decay_box_id = None
            incoming_gain, decay_pos = 1.0, 0
            for row, out_count in zip(rows, row_out_counts):
                overlap_entry = _continuing_pair(pending_row, row)
                if overlap_entry is not None and pending_frames:
                    tail_keep = min(len(pending_frames), 3 * k_mult + max(0, k_mult - 1))
                    tail_list = [f.astype(np.float32) / 255.0 for f in pending_frames[-tail_keep:]]
                    overlap_rgb = media._decode_overlap(store.overlap_video_path(folder, overlap_entry),
                                                        'sRGB', width, height, out_rate, color)
                    blended, gain_delta, applied = media._blend_continuation_seam(tail_list, overlap_rgb, k_mult, False)
                    if applied:
                        pending_frames[-tail_keep:] = [np.clip(np.rint(rgb * 255.0), 0, 255).astype(np.uint8) for rgb in blended]
                        incoming_gain, decay_pos = gain_delta, 0
                        decay_box_id = row['sources'][0]['id']
                if pending_frames is not None:
                    _mux_span_frames(container, video, pending_frames)
                curr_id = row['sources'][0]['id'] if (not row['bridgeId'] and len(row['sources']) == 1 and row['sources'][0]['weight'] == 1) else None
                if curr_id != decay_box_id:
                    incoming_gain, decay_pos, decay_box_id = 1.0, 0, None
                slate = None
                if row.get('missing'):
                    slate = Image.new('RGB', (width,height), '#252933')
                    ImageDraw.Draw(slate).text((12,12), f'Missing clip {row["missing"]}', fill='white')
                curr_frames = []
                for _ in range(out_count):
                    if slate is not None:
                        arr = np.asarray(slate)
                    elif row['sources']:
                        picture = sum(next(streams[s['id']]).astype(np.float32)*s['weight'] for s in row['sources'])
                        if incoming_gain != 1.0 and decay_pos < decay_len:
                            w_decay = 0.5 * (1.0 + math.cos(math.pi * (decay_pos + 1) / (decay_len + 1)))
                            picture = picture * (1.0 + (incoming_gain - 1.0) * w_decay)
                            decay_pos += 1
                            if decay_pos >= decay_len:
                                incoming_gain, decay_box_id = 1.0, None
                        arr = np.clip(np.rint(picture),0,255).astype(np.uint8)
                    else:
                        arr = np.zeros((height,width,3), dtype=np.uint8)
                    curr_frames.append(arr)
                pending_frames, pending_row = curr_frames, row
            if pending_frames is not None:
                _mux_span_frames(container, video, pending_frames)
            container.mux(video.encode(None))
            if audio is not None: media._mux_audio(container,audio,*sound)
        os.replace(temporary,path)
    finally:
        for stream in streams.values(): stream.close()
        if os.path.exists(temporary): os.remove(temporary)
    frames = rows[-1]['outputEnd']
    clock = [[s['outputStart'], min(s['outputEnd'],frames)-s['outputStart'],s['start'],0 if s['bridgeId'] else 1]
             for s in tracks.output_spans(tracks.document(parsed)) if s['outputStart']<frames]
    return dict(file=filename,sources=key,frames=frames,fps=round(out_fps, 3) if abs(out_fps - FPS) >= 1e-3 else FPS,
                clock=clock,mode=mode,note=note), note


def ensure(folder, name, parsed, manifest, crf, mode='full', make=True):
    """Nonblocking status/save integration, with immutable content-addressed movie files."""
    key = fingerprint(folder, parsed, manifest, mode, crf)
    record_key = 'track_'+mode
    saved = manifest.get(record_key)
    if saved and saved.get('sources') == key and os.path.isfile(os.path.join(folder,saved['file'])):
        return saved,False,saved.get('note','')
    job_key = (os.path.normcase(folder),mode)
    with _LOCK:
        job = _JOBS.get(job_key) or {}
        if job.get('thread') and job['thread'].is_alive(): return None,True,''
        if job.get('key') == key and job.get('error'): return None,False,job['error']
        if not make: return None,False,''
        snapshot = copy.deepcopy(manifest)

        def run():
            error = ''
            try:
                record,error = build(folder,name,parsed,snapshot,crf,mode)
                if record:
                    from .nodes import SEQUENCE_LOCK
                    with SEQUENCE_LOCK:
                        latest = store.load_manifest(folder)
                        if fingerprint(folder,parsed,latest,mode,crf)==key:
                            latest[record_key]=record;store.write_manifest(folder,latest)
                            discard_superseded(folder,latest)
            except Exception as failure:
                error = f'Track output could not be built: {failure}'
            with _LOCK: _JOBS[job_key] = dict(key=key,error=error)
            from .nodes import _notify
            _notify(name)

        thread = threading.Thread(target=run,name='h3c-tracks-output',daemon=True)
        _JOBS[job_key] = dict(key=key,thread=thread)
        thread.start()
        return None,True,''


def discard_superseded(folder, manifest):
    """Outputs are named by content, so every edit writes a new file; only the recorded ones are kept. A file a
    player still holds (Windows) stays until a later edit."""
    kept = {record['file'] for key,record in manifest.items()
            if key.startswith('track_') and isinstance(record,dict) and record.get('file')}
    for file in os.listdir(folder):
        if file.startswith('tracks@') and file.endswith('.mp4') and file not in kept:
            try: os.remove(os.path.join(folder,file))
            except OSError: pass


def restacker(parsed):
    # Existing save hooks pass this view into rebuild_full_video, which delegates to ensure.
    return lambda folder,manifest,crf,make=True: {**manifest,'_track_timeline':parsed}
