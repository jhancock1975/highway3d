## SwarmUI on top of ComfyUI (this image)

Everything in comfyui.md still applies. This image adds **SwarmUI**, a friendlier front
end that drives the same ComfyUI, and fetches two uncensored image models on first boot.

### Services

| Service | Supervisor program | Internal address | Portal port |
|---|---|---|---|
| SwarmUI (Generate tab, model browser, HTTP API) | `swarmui` | `127.0.0.1:17801` | 7801 |
| ComfyUI (node editor, native API) | `comfyui` | `127.0.0.1:18188` | 8188 |

Both wait for provisioning (`/.provisioning`) to finish before starting. SwarmUI has one
backend, "ComfyUI API By URL" at `http://127.0.0.1:18188`, so a generation started in
either UI runs on the same ComfyUI and GPU. SwarmUI's own ComfyUI nodes are installed in
`${WORKSPACE}/ComfyUI/custom_nodes/SwarmComfyCommon` and `SwarmComfyExtra`.

### Models

SwarmUI reads models directly from `${WORKSPACE}/ComfyUI/models`:

| Model | File | Defaults |
|---|---|---|
| Kroma v0.3 turbo (Krea 2 fine-tune) | `diffusion_models/kroma-v0.3-turbo.safetensors` | 8 steps, CFG 1, sigma shift 1.15 |
| Chroma1-HD | `diffusion_models/Chroma1-HD.safetensors` | 26 steps, CFG 3.8 |

Text encoders and VAEs sit under the names SwarmUI resolves automatically
(`text_encoders/qwen3vl_4b.safetensors`, `text_encoders/t5xxl_enconly.safetensors`,
`vae/QwenImage/qwen_image_vae.safetensors`, `vae/Flux/ae.safetensors`). Which set was
fetched is controlled by `IMAGEGEN_MODELS` (`all`, `kroma`, `chroma`, `none`); the
manifests are in `/opt/imagegen/provisioning/`.

### Generating through SwarmUI's API (no auth needed from inside the instance)

```
SID=$(curl -s -X POST -H 'Content-Type: application/json' -d '{}' \
      http://127.0.0.1:17801/API/GetNewSession | python3 -c 'import json,sys; print(json.load(sys.stdin)["session_id"])')
curl -s -X POST -H 'Content-Type: application/json' http://127.0.0.1:17801/API/GenerateText2Image -d "{
  \"session_id\": \"$SID\", \"images\": 1, \"prompt\": \"a lighthouse at dusk, film photo\",
  \"model\": \"kroma-v0.3-turbo\", \"width\": 1024, \"height\": 1024,
  \"steps\": 8, \"cfgscale\": 1, \"sigmashift\": 1.15, \"preferreddtype\": \"default\" }"
# -> {"images": ["View/local/raw/<date>/<file>.png"]}; GET http://127.0.0.1:17801/<that path>
```

Per-model presets ("Kroma turbo", "Chroma1-HD") only apply in the browser UI; API callers
pass the parameters themselves as above. `POST /API/ListBackends` shows the ComfyUI
backend's status, `POST /API/ListModels {"path": "", "depth": 2}` lists models. Full API
docs: https://github.com/mcmonkeyprojects/SwarmUI/blob/master/docs/API.md
