# H3 Continuity

H3 Continuity is a ComfyUI custom node pack for authoring and rendering sequences with MiniMax H3. Its Timeline organizes clips and carries context across continuing clips; the Studio adds story, reference and timeline editing. It also includes nodes for saved segments, stills and H3 context windows.

Visual memory can bring selected moments from earlier clips into a later shot, including after an exterior scene or a camera-angle change. H3 Story can plan and write the Timeline through an OpenAI-compatible endpoint, local or cloud.

For long continuing chains, the optional [H3 Continuity Protection](guide/continuity/long-chains.md#h3-continuity-protection) node uses sampler-level context noise and original chain anchors to target accumulated color/detail drift. It requires no extra node pack or model; protected sampling bypasses disk cache and does not support Context Windows. Render quality still needs checking on your model.

[Watch the contest demo (under two minutes)](https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/releases/download/v0.1.0/H3-Continuity-demo-contest.mp4) · [Full demo](https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/releases/download/v0.1.0/H3-Continuity-demo-full.mp4) · [Reproduce the example](docs/MEMORY-DEMO.md)

![The same room from another camera angle](docs/media/memory-comparison.png)

## Installation

Install a current ComfyUI with working MiniMax H3 support and its model files. Clone this repository into `ComfyUI/custom_nodes/ComfyUI-H3-Continuity-Studio`, or extract the source archive there. Run `python -m pip install -r requirements.txt` from this folder using the same Python environment as ComfyUI. On Windows portable installations, use the portable installation's `python_embeded/python.exe` instead of a system Python.

Restart ComfyUI, load `examples/h3_story_studio.json`, and select the H3 diffusion model, text encoder, video VAE, audio VAE and optional LoRA installed on your system. This example records model names from its original environment; they are not downloaded automatically. It also includes an optional still-image subgraph and may require additional models. The source package was checked in an isolated CPU-only ComfyUI startup; a GPU and suitable model files are required for generation.

The Story writer requires a separately configured compatible language model endpoint. Models, provider services and their terms are separate from this node pack. Context Windows requires a ComfyUI version containing the core MiniMax H3 Context Windows node.

## First sequence

1. Start ComfyUI and open `examples/h3_story_studio.json` through its workflow loader.
2. In the model loader nodes, select compatible H3 diffusion, text encoder, video VAE and audio VAE files available on your installation. Configure the example LoRA only if it matches your model. The workflow also contains a still-image recipe; its additional model is optional for video-only work.
3. Open the Timeline Studio, add or edit a box and supply a prompt. Render the first box through the connected H3 workflow. Add another box configured to continue, then render it and inspect the join. Start with short clips and enough GPU memory for your chosen model.
4. Story is optional. To use it, configure a compatible language-model endpoint and model in the Story node. An external endpoint receives the story text and, when enabled, reference pictures. Check the provider's privacy and pricing terms.

Model names and paths in examples are illustrative; select files available in your own installation. ComfyUI and the chosen model determine the required hardware and software versions. H3 Continuity does not download model weights or provider credentials.

Avoid installing a second copy beside an existing H3 Continuity installation: both copies register the same nodes and routes. Back up projects before replacing an existing installation. Keep ComfyUI behind your usual authenticated access boundary if you expose it remotely.

## MCP for AI agents

Codex and Claude Code can launch the standalone stdio adapter against a local or remote Studio. Update the node on the serving ComfyUI host first, then install the adapter with Python 3.11+ in its own environment, separate from ComfyUI:

```sh
uv run --project "/absolute/path/ComfyUI-H3-Continuity-Studio/mcp_adapter" h3c-mcp --studio-url http://127.0.0.1:8188 --check
```

The adapter exposes saved-project editing, render/Story/still tools and the existing seven skills through the MCP Skills extension and ordinary resources. Browser synchronization is not required. Client skill activation depends on extension support; ordinary guidance reads and the filesystem installer remain available.

See [installation and Codex/Claude Code setup](guide/automation/mcp.md) for uv/venv launchers, Windows paths, remote URLs, bearer environment variables and diagnostics. The [MCP reference](docs/MCP.md) covers tools, snapshots, revisions and retained submission receipts.

## Documentation

The full user guide, with screenshots of every feature, is at **https://kadobot.github.io/ComfyUI-H3-Continuity-Studio/**. Its source is in [`guide/`](guide/).

Deeper reference notes: [Story Studio](docs/QWEN-STORY-STUDIO.md), [external Timeline](docs/EXTERNAL-TIMELINE.md), and [continuity checks](docs/CONTINUITY-CHECK.md). Generation quality and continuity vary with the model, inputs and settings; inspect the resulting joins.

## Credits

**H3 Continuity Protection** builds on the public keystone/capstone anchor and late-locking ideas in **[roycho87's Geiru Context Suite](https://github.com/roycho87/geiru_context_suite)**. Sampler-synchronized context noise is credited to **ethanfel / Lumifel**, whose [H3 Context Loop work](https://github.com/ethanfel/ComfyUI-MiniMaxH3-Context-Loop) Geiru also credits. Our native implementation is independent; it does not vendor Geiru's GPL-3.0 source or require its node pack.

The optional **attention balance** follows Geiru's **Keystone Attention**, which is based on an idea by **ckinpdx**: biasing H3's attention by part of its sequence, published as **[ckinpdx's Carry Attention](https://github.com/ckinpdx/ComfyUI-MMH3Tools)** in ComfyUI-MMH3Tools. The default blocks are Geiru's published lighting blocks. Ours is again an independent native implementation; see the [upstream review](docs/research/2026-11-16-geiru-upstream-review.md). Geiru's Hybrid Windows changes are not included. See [third-party notices](THIRD_PARTY_NOTICES.md) for this project's other sources and attributions.

## License and third-party material

Original project code is offered under the [MIT License](LICENSE). The public release does not include the optional MiniMax H3 prompt guides. If you have obtained them under terms that permit your use, place `base-en.txt` and `ref-en.txt` in `h3_continuity/h3_guide/` and restart ComfyUI. Without them, the node pack runs and its instruction bundle explicitly reports the missing guides. The guides and H3 model are subject to MiniMax terms, including territorial restrictions; see the [upstream project](https://github.com/MiniMax-AI/MiniMax-H3) and the included [notice](h3_continuity/h3_guide/NOTICE). Model weights and external dependencies have separate licenses. Review those terms before use or redistribution. See [third-party notices](THIRD_PARTY_NOTICES.md) for adapted guidance and attribution.
