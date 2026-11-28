---
name: h3-continuity-api
description: Use when driving H3 Continuity Studio programmatically over MCP (h3c-mcp) or HTTP — including h3_capabilities, h3_get_project, h3_save_project, h3_inspect, h3_plan_video, h3_render_video, h3_story, h3_stills, h3_takes, h3_library, Timeline API v1 (/h3c/api/v1), graph preparation (/h3c/timeline/prepare), requires feature flags, revision conflicts and held jobs.
---

# Driving H3 Continuity Studio from code

## MCP workflow (`h3c-mcp`)

Run `h3c-mcp` (from `mcp_adapter`) over stdio (or one-off `python -m h3c_mcp --call TOOL --arguments JSON`). Start with `h3_capabilities`, `h3_read_guidance` (`h3c://docs/MCP.md`), and `skill://<name>/SKILL.md` resources.

1. **Load & inspect:** `h3_list_projects` -> `h3_get_project` returns `document_json` + `revision`. Preserve exact uint64 seeds and opaque metadata. Non-empty `unsupported_features` opens read-only: fork a clean copy via `h3_library` `duplicate` rather than editing in place.
2. **Author & set `requires` flags:** Include the matching `"requires"` feature flag(s) in `timeline` whenever using modern features:
   - `"dialogue-cues-1"` (`timeline.dialogue`), `"box-audio-windows-1"` (`audio_clips[].box_windows`), `"video-layers-1"` (`boxes[].layers` + `switch`), `"timeline-tracks-1"` (`tracks`, `boxes[].track`/`start`, `overlap_switches`, `text_lanes`), `"scene-map-1"` (`boxes[].scene_map` when `on: true`).
3. **Save cleanly:** Call `h3_save_project` with `expected_revision`. Reread on `409` revision/busy/ownership conflicts; never auto-merge (browser autosave and Undo are separate). Register/capture graphs via Studio or `h3_register_workflow` `{ui, api}` (graph edits require deliberate recapture; never invent editor-to-API conversions; manage `H3C_ContinuityProtection` in the captured graph per `h3_inspect` `nodes` + `h3-continuity-joins`).
4. **Mandatory pre-render gate (`h3_inspect` + `h3_plan_video`):** Before queueing any GPU render, run `h3_inspect` (`prompt_fields`, `status`) and `h3_plan_video` (read-only) and verify:
   - Resolved `mode` (`t2va`/`flf2va`/`ref2va`), `tags`, `delivered_range`, and exact `guides`.
   - Zero unbound `<Subject N>` (`prompt_fields`), zero FX/framing/speed/lighting lint warnings, zero `seam_warnings` / `timing_conflicts`.
5. **Render & reconcile:** Keep saved `Idempotency-Key` + returned handle. `h3_render_video` submits **one** unit per call on native profiles (`h3_job_status` / `h3_resume_job` never auto-queue the next); managed profiles progress server-side. Never mask held/ambiguous receipts with a new key/sequence; retain the adapter state directory across restarts. Only explicit human attestation may call managed `h3_abandon_job`. Native global Stop and replacement bridges are unavailable.
6. **Proposals, takes & media:** `h3_story` and `h3_stills` produce proposals that must be explicitly applied/saved (`h3_job_status` -> save). `h3_takes` lists/switches/rates takes and previews scoped deletion before deleting. `h3_upload_asset` uploads bytes from allowed local roots; `h3_download_artifact` verifies hash/size. Browser layout, playback, history, and beat/waveform snap remain browser-only.

## HTTP Timeline API v1 (`/h3c/api/v1`)

For new productions without a custom graph (server holds graph, revisions, durable jobs; see `timeline-api` guide + `examples/timeline_api.py`):

1. `GET /h3c/api/v1/capabilities` — schemas, `limits`, profile readiness/digests (e.g. `native-turbo4`), `jobs: {held, waiting, blocked_by}`. Read task library choices first; pin project profile digest.
2. `POST /h3c/api/v1/assets` — multipart `{kind: picture|guide|audio|video|whisper, file, expected_sha256?}`. Same bytes keep one `asset_id` and accrue `permitted_uses` (`guide`/`plate`/`candidate` bindings require a `guide` PNG upload). Bind in `project.assets` (`picture` `image17+`, `audio_clip` `audio1..3`, `voice_clip` `audio4+`, `guide`, `plate`, `reference_replacement`, `candidate`, `whisper`).
3. `POST /h3c/api/v1/projects` (saved `Idempotency-Key`) — `{name, profile, settings, timeline, assets, consumer?, semantic_boxes?}`. Only `settings.width` & `height` (multiples of 32 within ±5% pixel count of profile) can differ (`409 immutable_profile` / `invalid_production_size` otherwise). `PUT /projects/{id}` updates with `expected_revision` (omit `profile`).
4. `POST /projects/{id}/plan` — `{"expected_revision": N, "selection": {"kind": "all"} | {"kind": "boxes", "ids": [...], "rerender": true}}` -> unit actions (`render`/`reuse`/`blocked`), dependencies, `plan_sha256`.
5. `POST /projects/{id}/jobs` (`Idempotency-Key` + `plan_sha256`) -> poll `GET /jobs/{id}` (`accepted` -> `queued` -> `running` -> `succeeded` | `failed` | `needs_reconciliation`). Verify downloads via `GET /artifacts/{id}` + `.../download` (size, SHA-256, decoded media).
6. **Recovery, takes & export:** Re-poll or `POST /jobs/{id}/resume` after disconnects; never reuse keys with modified bodies (`409 idempotency_conflict`). Held `needs_reconciliation` jobs block later jobs until reconciled or abandoned by a human (`POST /jobs/{id}/abandon` with `confirm_prompt_id`). `GET /projects/{id}/takes?box=ID` + `POST .../takes/use`; `GET /projects/{id}/workflow?mode=fork|attached` (Studio export); `GET|POST /h3c/stories` (+ `/delete`). Always access via authenticated proxy.

## Graph preparation (`/h3c/timeline/prepare`) & Studio transfers

- **`POST /h3c/timeline/prepare`** (see `external-timeline` guide + `examples/external_timeline.py`): validates asset hashes against an owned ComfyUI API graph (`{version, name, timeline, settings, workflow: {api, timeline_node, ui?}, assets, semantic_boxes}`), returns per-box inspection + `fingerprint` without uploading/loading models. Render box-by-box with one `external_timeline.py` owner per unique sequence name (resume with identical command; stop and inspect manually on ambiguous `submitting` receipts). Done = all boxes fresh, `next: null`, expected duration, retrievable `_full.mp4`.
- **Studio UI:** **Export/Import project JSON** moves graph + wiring; **Export/Import generation** moves Story/Timeline/guides/candidates/takes between generator workflows; **New project** clears Timeline/Cast/Story while keeping uploaded assets.
