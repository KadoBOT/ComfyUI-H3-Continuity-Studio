# Third-party notices

## H3 Continuity Protection techniques

The clean keystone/capstone anchors and late locking in `h3_continuity/protection.py` follow public ideas developed by **roycho87** in [Geiru Context Suite](https://github.com/roycho87/geiru_context_suite), inspected initially at [e03cda9](https://github.com/roycho87/geiru_context_suite/tree/e03cda9f643afe55430ee4ccdff228888d1cdae1). Sampler-synchronized context noise is credited to **ethanfel / Lumifel** and [ComfyUI-MiniMaxH3-Context-Loop](https://github.com/ethanfel/ComfyUI-MiniMaxH3-Context-Loop), also credited by Geiru.

This is an independent native implementation against ComfyUI APIs. No Geiru source, example workflows or other GPL-3.0 material are vendored into this MIT project. Geiru retains its own license and attribution; credit here describes the ideas that informed our implementation.

The optional `attention_balance` in the same file follows Geiru's **Keystone Attention** (reviewed at [099da1b](https://github.com/roycho87/geiru_context_suite/commit/099da1be92f2da22a775076a0d533d29b4d97268)): re-splitting only the attention shared by clean anchors and held carried frames, on Geiru's published lighting blocks 31-33, 36-44 and 47. Keystone Attention is in turn based on an idea by **ckinpdx**: biasing H3's attention by part of its sequence, published as **Carry Attention** in [ComfyUI-MMH3Tools](https://github.com/ckinpdx/ComfyUI-MMH3Tools) (MIT). Our version is written independently on ComfyUI's attention override hook; no Geiru or MMH3Tools source is included.

The [2026-11-16 upstream review](docs/research/2026-11-16-geiru-upstream-review.md) also records Geiru's Hybrid Windows memory changes, built on **kijai**'s core context windows and **JalenBrunson**'s HybridWindows work. Those are not implemented here; this notice does not imply their code or results are included.

## Other sources

The shot-writing guidance in `h3_continuity/story_prompts.py` is adapted from the [MiniMax H3 Singularity prompt-writing specification](https://huggingface.co/WarmBloodAban/Minimax-h3_Singularity/blob/af671d9214a6e41ab8c2f43e9f871ea56246115f/MiniMax_H3_Singularity_Prompt_Writing_Specification_Enhanced_EN.md) by WarmBloodAban. The upstream repository's model card at that revision identifies Apache-2.0. A copy of the [Apache License 2.0](APACHE-2.0.txt) is provided. The guidance in this project has been adapted; no upstream model weights are included.

The public release omits the MiniMax prompt-guide text. If installed separately, those guides and the MiniMax H3 model have their own terms; see `h3_continuity/h3_guide/NOTICE` and `h3_continuity/h3_guide/LICENSE` and the upstream distribution. Other dependencies and models have their own licenses.

The texture measure in `h3_continuity/check_frames.py` (`texture`) is a NumPy port of `texture_band_rms` from [ComfyUI-MiniMaxH3-PrefixStream](https://github.com/knoic/ComfyUI-MiniMaxH3-PrefixStream), used under the MIT License:

> MIT License
>
> Copyright (c) 2026 knoic
>
> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Paired context noise, audio feather, take ratings and lineage, and per-box video windows follow ideas from the same project. H3 Sigmas Tail follows an idea from [ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context) (GPL-3.0); it is an independent implementation and contains none of that project's code.
