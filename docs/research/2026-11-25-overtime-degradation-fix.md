# Overtime Visual Degradation Fix — PR #94 (`dp3` / `DP5`)

**Date:** 2026-11-25  
**Branch:** `feat/continuity-protection` ([PR #94](https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/pull/94))  
**Fixtures Validated:**
- Active story `generation_64933481474b4b2abef0f94d0afaff08` (*Stellar Jett - Heavy Things Fall Up* — Veda Sparse Attention + Ref2VA INT8 ConvRot + 8-step Turbo Fusion LoRA)
- Original DP2 observatory onset `generation_2701108ee2f34004be88fe6fbf18f6e9` Clip 2 (native dense `10Eros` beta7)

---

## 1. Root-Cause Diagnosis

Comparison of Clip 1 against sequential continuations (Clips 2–4, `ctx=39`) and visual-memory cuts (Clip 5 and Clip 11, `ctx=0`) revealed three compounding issues:

1. **Single-hop DiT latent drift**: Even when starting directly from a clean Clip 1 anchor, the 8-step denoiser exhibits rapid per-clip drift in three latent components:
   - **Mean luma/chroma shift**: Clip 1 `L=35.80, a=+0.30, b=+1.35` drops to `L=31.16` in Box 2 (`dE=4.64`), `L=27.89, a=+1.75, b=+3.45` in Box 11 (`dE=8.31`), and `L=24.92` in Box 5 (`dE=10.98`).
   - **Channel std inflation (`sR_max`) & shadow crushing**: Channel standard deviation inflates to `1.25–1.61x` anchor std, increasing saturation (`0.191 -> 0.251–0.288`) and shadow crushing (`10.5% -> 18.0%–25.8%`).
   - **High-frequency haloing (`tex_mid`)**: Spatial high-frequency energy overshoots (`1.27x` in Box 11) producing bright edge halos and harsh skin burn.
2. **Ineffectiveness of prior PR #94 mechanisms on Veda + cut-memory blind spot**:
   - The previous `linspace(1, 0)` context-noise + late capstone + `attention_balance` pipeline had zero measurable impact on Veda Sparse Attention Box 2 (`L=31.14, dE=4.66` vs baseline `31.16, dE=4.64`).
   - `ctx=0` visual-memory cuts (`b005, b007, b008, b010, b011`) were completely skipped (`prot=no`), allowing full-strength darkening, brown/green cast, and edge halos across cuts.
3. **Mean-matching trade-off on dark-to-bright camera pans**:
   - In the DP2 observatory orbit (`generation_2701108ee2f34004be88fe6fbf18f6e9`), the camera pans from a darker wall (`L=36.56`) onto a bright window (`tail L=41.84 -> Clip 2 L=43.87`). Matching mean exposure to the darker tail (`mode='full'`, `tail12`) darkened the window wall (`wall_luma=70.50, dE=4.53`). Leaving mean untouched while damping variance and HF overshoot (`mode='contrast_only'`) addresses contrast/halo drift without fighting natural exposure brightening.

---

## 2. Baseline vs Old PR #94 (`Stage 1` Diagnosis)

| Clip / Variant | `L` | `a` | `b` | `dE` | `sat` | `crush` | `tex_mid` | `flow` | `dM` | `sR_max` | `carryErr` | `prot` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **Clip 1 (anchor)** | 35.80 | +0.30 | +1.35 | 0.00 | 0.191 | 10.5% | 1.00x | 0.72 | — | — | — | — |
| **Box 2 (`ctx=39`) baseline** | 31.16 | +0.40 | +1.16 | 4.64 | 0.251 | 18.0% | 0.86x | 0.67 | 0.171 | 1.30 | 1.2e-07 | `no` |
| **Box 2 (`ctx=39`) old PR #94** | 31.14 | +0.40 | +1.16 | 4.66 | 0.251 | 18.0% | 0.86x | 0.67 | 0.174 | 1.29 | 0.0e+00 | `yes` |
| **Box 11 (`ctx=0`) baseline & old PR #94** | 27.89 | +1.75 | +3.45 | 8.31 | 0.277 | 15.7% | 1.27x | 0.67 | 0.317 | 1.50 | — | `no` |

---

## 3. Stage 1 Ablations (Veda Box 2 & Box 11)

- **Box 2 (`stage1_b2`)**:
  - `s065_upper`: `dE=1.56, L=34.24, sat=0.183, flow=0.79`
  - `s080_upper`: `dE=1.08, L=34.72, sat=0.175, flow=0.83`
  - `s065_sym`: `dE=1.56, L=34.24, sat=0.186, flow=0.81`
  - `s065_cn` (`context_noise=0.40`): `dE=1.54, L=34.26, flow=0.76`
- **Box 11 (`stage1_b11`)**:
  - `s065_upper`: `dE=1.40, L=34.43, sat=0.187, crush=10.7%, flow=0.72`
  - `s065_ref1` (`ref_strength=1.55`, full ref stabilization): **`dE=1.35, L=34.49, a=+0.37, b=+1.69, sat=0.181, crush=10.2%, tex_mid=1.15x, flow=0.71`** (halos and warm/green cast eliminated).

---

## 4. Production Implementation

Implemented in [`h3_continuity/protection.py`](../../h3_continuity/protection.py) and [`h3_continuity/disk_cache.py`](../../h3_continuity/disk_cache.py):

- **Root & anchor resolution (`_resolve_root`, `load_anchor_clip`)**:
  - Resolves root clips for both continuations (`ctx > 0`, slicing the last `TAIL_ANCHOR_TOKENS=12` latent tokens when `same_shot=True`) and `ctx=0` `cut_memory` shots (`scene`/`selected`/`cast`, cross-flashback explicit references like `b010 -> b001` across `b009`, and post-cut chains like `b006 -> b001`, using the full played clip).
  - Passes through `new_scene=True` with `memory='off'`, `plate_changes`, bridges, replacements, and layers (`prot=no`).
- **Phase-aware latent & reference stabilization**:
  - Splits latent frames along H3's temporal layout (`t % 5 == 0` 1-frame keyframes vs `t % 5 != 0` 4-frame blocks) via `compute_phase_stats` and `_stabilize_video`.
  - Applies upper-clamped channel std (`min(cur_std, anc_std)`), replicate-padded 3×3 high-frequency overshoot damping (`clamp(anc_hf / cur_hf, max=1.0)`), and optional mean matching (`mode='full'`, omitted in `mode='contrast_only'`) along a tapered denoiser schedule (`_schedule_weight`).
  - Stabilizes `cond_video_latents` (`video`/`video_audio` reference latents only at `strength * REF_STRENGTH_MULTIPLIER` with `REF_STRENGTH_MULTIPLIER = 1.5`; keyframes/`image` left untouched) and runs `cut_memory` sampling without `noise_mask`.
- **Node schema, carry safety & disk cache**:
  - Exposes `strength` (`DEFAULT_STRENGTH=0.70`) and `mode` (`('full', 'contrast_only')`).
  - Preserves exact carried-frame restoration (`_restored`, `carryErr=0.0e+00`) and live `ProtectionReceipt` validation in Save Segment.
  - Excludes `('segment', 'strength', 'mode', 'attention_balance', 'attention_blocks')` from pass-through cache hashing and bypasses disk cache on protected runs.

---

## 5. Final Production-Code GPU Verification (`Stage 2`)

### 5.1 Stellar Jett Sequential 5-Clip Veda Chain (`mode='full'`, `strength=0.70`)

| Clip | Mode / Variant | `L` | `a` | `b` | `dE` | `sat` | `crush` | `tex` | `flow` | `dM` | `sR_max` | `carryErr` |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Clip 1** | Anchor | 35.80 | +0.30 | +1.35 | 0.00 | 0.191 | 10.5% | 1.00x | 0.72 | — | — | — |
| **Clip 2 (`ctx=39`)** | Original | 31.07 | — | — | 4.73 | 0.251 | 18.0% | — | 0.66 | 0.177 | 1.29 | 1.2e-07 |
| **Clip 2 (`ctx=39`)** | **Protected** | **34.74** | +0.38 | +1.08 | **1.09** | **0.213** | 16.8% | **0.98x** | **0.80** | **0.062** | **1.17** | **0.0e+00** |
| **Clip 3 (`ctx=39`)** | Original | 28.65 | — | — | 7.23 | 0.283 | 18.1% | — | 0.46 | 0.314 | 1.25 | 1.2e-07 |
| **Clip 3 (`ctx=39`)** | **Protected** | **34.84** | +0.53 | +1.43 | **0.98** | **0.243** | 16.0% | **1.02x** | **0.61** | **0.062** | **1.16** | **0.0e+00** |
| **Clip 4 (`ctx=39`)** | Original | 29.19 | — | — | 6.71 | 0.279 | 17.4% | — | 0.41 | 0.327 | 1.27 | 1.2e-07 |
| **Clip 4 (`ctx=39`)** | **Protected** | **35.62** | +0.40 | +1.15 | **0.28** | **0.244** | 14.8% | **1.15x** | **0.55** | **0.061** | **1.16** | **0.0e+00** |
| **Clip 5 (`ctx=0`, cut)** | Original | 24.92 | — | — | 10.98 | 0.288 | 25.8% | — | 3.92 | 0.433 | 1.61 | — |
| **Clip 5 (`ctx=0`, cut)** | **Protected** | **34.34** | +0.29 | +1.57 | **1.47** | **0.177** | **4.8%** | **1.03x** | **3.50** | **0.034** | **1.05** | **0.0e+00** |

### 5.2 Fresh-Scene Flashback Pass-Through (`Box 9`, `new_scene=True`, `memory='off'`)

- Protected flag: `prot=no` (unmodified pass-through).
- Output metrics: `L=20.18, a=+1.57, b=-4.02` vs original `L=19.97, a=+1.58, b=-4.03` (`dE_vs_orig=0.21`).

### 5.3 DP2 Observatory Clip 2 (`generation_2701108ee2f34004be88fe6fbf18f6e9`, Native Dense `10Eros`)

- `mode='full'` (`tail12`): `wall_luma=70.50, dE=4.53` (mean matching pulls the bright window pan down toward the darker tail).
- **`mode='contrast_only'`, `strength=0.70`**:
  - Full clip: `valid=39, med_luma=74.54, med_dE=2.64, flow=0.461, carryErr=0.0e+00`
  - Common (`31 frames`): **`wall_luma=75.71`** (vs `dp2_baseline 73.82`, `dp2_pr94 74.68`, bright reference `78.10`), **`dE76=3.04`** (vs `dp2_baseline 2.42`, `dp2_pr94 2.46`).
