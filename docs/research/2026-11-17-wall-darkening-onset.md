# Wall-darkening onset test — 2026-11-17

## Correct acceptance case

User correctly identified that the earlier clip-30 experiment targeted the camera jump, not accumulated wall darkening. The original full video is exactly 120 seconds, 2,880 frames at 24 fps. Its 0:02 frame is clip 1 (`seg_0001-2`), played frame 48; 0:50 is clip 15, played frame 5. CPU decode gives zero RGB difference between each full-video frame and its saved source frame. The darker, browner wall is already in the generated source, rather than introduced by full-video assembly.

The user requested finding the last bright view and first darkening, then rendering only that range. No full 50-second rerender is selected. Existing clip-30 results remain integration/jump evidence only.

## Locating the onset

Inspected a manifest-backed contact sheet of clips 1–25, then dense frames around the first continuations. Early files with plain names `seg_0002.mp4` / `seg_0003.mp4` are unused legacy material: the current manifest correctly points to `seg_0002-2` / `seg_0003-2`. All scan and fixture selection follows the manifest, not guessed filenames.

Tracked a plaster region left of the central arched window, using SIFT matches on the adjacent window to estimate a planar homography. The reference is clip 1/frame 48; its wall quadrilateral is `(190,40)–(370,140)`. Homographies with fewer than ten inliers are rejected. Camera, light and generated geometry still affect the estimate; this is an observed first decline, not a claim that natural lighting is isolated.

| Source frame | Full-film time | Registered wall luma (0–255) |
| --- | --- | --- |
| Clip 1/frame 48 | 2.000 s | 78.1 |
| Clip 1/frame 89 | 3.708 s | 77.6 |
| Clip 2/frame 0 | 3.750 s | 78.6 |
| Clip 2/frame 1 | 3.792 s | 76.2 |
| Clip 2/frame 6 | 4.000 s | 75.3 |
| Clip 2/frame 12 | 4.250 s | 74.9 |
| Clip 2/frame 24 | 4.750 s | 73.0 |
| Clip 2/frame 42 | 5.500 s | 72.7 |
| Clip 2/frame 60 | 6.250 s | 75.7 |

The original bright source remains stable through clip 1 and clip 2's first guided frame. The first continuation then shows a small decline, with fluctuations as the camera moves, well before the pronounced difference at 0:50. A matching wall view at clip 3/frame 84 gives 66.9; clip 4/frame 42 gives 62.9. Some close views could not be registered reliably and are not assigned a brightness value.

The smallest source-backed onset fixture is therefore **clip 2 only**, approximately full-film 3.75–7.29 seconds, carrying the original bright clip 1. It tests prevention of the initial decline rather than attempted repair after 29 already generated clips.

## Matched fixture

Three independent folders copy only original clip 1; Timeline selects original box 2, with its unchanged 85 played frames, seed, prompt and scene memories. All arms use the same native dense backend and original 10Eros beta7 / Euler8 beta57 / 1152×640 / 39-frame carry / sigma shifts12/3 recipe. Controls: disabled protection; protection at neutral balance1; protection at balance20 on the credited lighting blocks. The shared ComfyUI host and original story remain untouched.

Ignored artifacts: `.tmp/dp2/wall/` stores exact film/source frames, onset scan and registration overlays/data; `.tmp/dp2/onset/` stores the three frozen graphs, submission/history receipts and new logs. This is separate from the earlier clip-30 fixture. GPU owner remains `fec5d642-7e40-4228-9dbf-43bc9479fcd8`; new ticket `9cdd0f62-ac55-434e-9194-8e2c7fcdc1f4` coordinates this narrow run.

## Result: wall-preservation acceptance failed

All three renders completed and saved 85 played frames. Source manifest hash remains unchanged. Saved metadata confirms expected settings; delivered scene memories match across arms. Protected overlap is restored exactly (maximum error 0); baseline overlap differs by at most 1.1920928955078125e-7. All arms use normal sampler output.

| Arm | Prompt receipt | Completed settings |
| --- | --- | --- |
| Baseline | `c0a6535b-dbd6-415a-bd3c-cbadbfb0f6ef` | Protection disabled |
| Protection, balance 1 | `195bc2cf-91d9-4e62-abac-394042f6e510` | Clean source 1, capstone start 6/8, attention unchanged |
| Protection, balance 20 | `98daddb6-7adc-44d5-90e4-421e43c84c99` | Same source/schedule, all 13 selected lighting blocks balanced |

The wall quadrilateral is registered independently in each frame. Reject fewer than 10 inliers, nonconvex/extreme-size projections or any projected corner outside the image. Registration was valid for 34/85 baseline frames, 35/85 neutral frames and 35/85 balance-20 frames. **Only the 30 matching timestamps valid in every native arm** contribute below: frames 0–24, 26, 27, 30, 33, 35. Later the region approaches/leaves the view or registration becomes uncertain; missing values are not extrapolated. Overlays were visually inspected. Mean-color ΔE76 compares the region's mean CIELAB color with the bright clip-1/frame-48 region; lower is closer. Lighting, generated geometry and registration error remain confounders.

| Arm | Common-frame wall luma (0–255) | Common-frame mean-color ΔE76 | Whole-clip mean flow (pixels/frame) |
| --- | --- | --- | --- |
| Baseline | 73.93 | 2.37 | 0.453 |
| Protection, balance 1 | 74.86 | 2.39 | 0.447 |
| Protection, balance 20 | 71.71 | 3.20 | 0.451 |

**Balance 20 worsened measured wall darkening and color deviation in this onset test.** Neutral protection is only slightly brighter than baseline, with effectively unchanged mean-color error; that does not establish a meaningful fix. Subject/camera movement remains visible and flow proxies are similar among the native arms. This range does not show the abrupt composition reset motivating the separate clip-30 test.

The original front anchor was also checked: its registered wall luma is about 80.0 at source frame 0, versus 78.1 at frame 48 and 77.6 at frame 89. The negative result cannot be dismissed as using an obviously dark front frame. It is an empirical limitation of this recipe/model/short test, not proof of a new implementation defect or a general inverse relation between balance and brightness. One seed and partial registration coverage do not support broad model claims.

Keep attention neutral by default and PR #94 in draft. **The native implementation has not passed wall-degradation acceptance; DP2 remains active.** Do not promote Geiru's default 20 or the earlier late-clip whole-frame brightness result as a working recipe for this story. Any further recipe change must improve this fixed onset case's wall-color fidelity as well as preserve motion.

Local artifacts: `.tmp/dp2/onset/comparison.html` (video, registered-wall/flow curves and overlays), `comparison.mp4`, `wall-comparison.png`, `wall-curves.png`, `metrics.json`, `validation.json`, frozen graphs and history receipts. Generated media stays local.

## Cleanup and verification

After all receipts succeeded, the isolated queue was idle. Owned PID 40500 was stopped and confirmed absent; device usage returned to desktop/shared-host baseline (about 1.5 GiB). Ticket `9cdd0f62-ac55-434e-9194-8e2c7fcdc1f4` was finished/released. Shared 8188 remains alive and idle; source story/workflow and parent checkout are untouched. No full-50-second rerender, shared-host restart, merge or release.

Technical checks pass: three successful GPU saves, source/carry/memory validation and strict docs/diff/roadmap checks; product code is unchanged from the reviewed fix with 402 JavaScript + 587 Python and 79 adapter tests. **Visual acceptance failed** as reported above; successful execution is not a passing color result.
