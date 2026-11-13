# Stills with MiniMax H3 Image

**MiniMax H3 Image Still** wraps the official native ComfyUI image workflow in
one node. Its **still_recipe** output connects directly to the Timeline's
**still_recipe** input. Its **image** output can also feed Preview or Save Image.
Load `examples/minimax_h3_image_story_studio.json` for an already connected example.

## Install

Update ComfyUI to a version that includes **MiniMaxH3ImageConditioning** (native
support added November 10, 2026), then restart ComfyUI. The node reports a missing
core node when an older installation attempts image generation. No additional
custom image nodes are needed.

Download the weights from [Comfy-Org/MiniMax-H3-Image](https://huggingface.co/Comfy-Org/MiniMax-H3-Image):

| Component | File | ComfyUI folder |
| --- | --- | --- |
| Diffusion model | `minimax_h3_image_pruned_int8_convrot.safetensors` (about 21 GB) | `models/diffusion_models` |
| Text encoder | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | `models/text_encoders` |
| Image VAE | `minimax_h3_image_vae_fp16.safetensors` (about 1.2 GB) | `models/vae` |

The bf16 and W4A8 diffusion variants also work. Reuse your existing official
Qwen3-VL MiniMax H3 text encoder if installed; bf16 and int8_convrot encoder
variants are also supported. The image VAE and diffusion model are different
from the H3 video and Pruna P-H3-Image files.

For example, downloading just the diffusion model and image VAE:

```bash
hf download Comfy-Org/MiniMax-H3-Image diffusion_models/minimax_h3_image_pruned_int8_convrot.safetensors vae/minimax_h3_image_vae_fp16.safetensors --local-dir ComfyUI/models
```

Read the [MiniMax H3 Image license](https://huggingface.co/MiniMaxAI/MiniMax-H3-Image/blob/main/LICENSE),
which differs from the video model's license.

## Generate a guide

Select your diffusion model, text encoder and image VAE on **MiniMax H3 Image
Still**, then connect its **still_recipe** output to Timeline **still_recipe**.
In the Studio, select a First, Last or Shot marker, choose **Generate candidates**,
and accept an image with **Use as guide**.

Optionally connect a **LORA_STACK** output, such as Easy Use's LoRA stack, to
**lora_stack**. Each entry is `(filename, model strength, CLIP strength)`. Entries
apply in order to the diffusion model and conditioning text encoder for both
direct images and Studio candidates. Use LoRAs compatible with MiniMax H3 Image.
An unconnected or empty stack leaves generation unchanged; entries named `None`
and entries with both strengths at zero are skipped.

The Studio uses the selected clip's prompt exactly, without adding shared text,
reference descriptions or the generator's instruction. It fills the seed and reference images for each request. It
preserves scene and character reference roles, putting the location first when
one is available. Prompts use native `<Picture 1>`, `<Picture 2>` labels and
describe a new still composed for the requested camera: every image, including
Cast sheets and location grids, is a reference for its role, never the image to
edit. Reference images retain their original canvas until native conditioning
scales them. Up to eight references are exposed here.
Sampling follows the [official workflow](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_minimax_h3_image_t2i.json):
six Euler steps, simple schedule, CFG 1. Dimensions are explicit, default to
2048 × 2048 and must be multiples of 32. Studio generation uses these dimensions
unless the request supplies a still size. There is no implicit P-H3 8 MP resize.
The official template starts at a reduced size and recommends about 16 MP for
quality when memory permits (4096 × 4096 square or 5472 × 3072 widescreen).

Set **megapixels** above 0 to generate at that area instead. Width and height
then only set the aspect ratio, so you can connect the video size directly: 1152
× 640 at 20 MP generates 6016 × 3328. Each side is rounded to a multiple of 32
and must stay within 8192. At 0, width and height are used exactly.

Reference images are separately resized to 4 MP and aligned to a multiple of 32,
matching the [official edit workflow](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_minimax_h3_image_edit.json).
The requested output remains native resolution: a 20 MP output is sampled at
20 MP. Candidate metadata records the separate reference resize setting.

No still-prompt preparation or prompt-enhancer download is required. Video rendering does not execute or
load the connected still model.
