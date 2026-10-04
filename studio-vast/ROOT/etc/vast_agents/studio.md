## The studio (this image)

An uncensored film studio driven by a chat. Everything below runs on this machine; nothing
calls out except model downloads on first boot.

### Services

| Service | Supervisor program | Internal address | Portal port |
|---|---|---|---|
| Studio Chat (Open WebUI 0.11.4) | `openwebui` | `127.0.0.1:18081` | 8081 |
| Director LLM (vLLM, `studio-llm`) | `vllm` | `127.0.0.1:18000` (OpenAI API) | none |
| ComfyUI (Chroma1-HD, Wan2.2-Remix i2v) | `comfyui` | `127.0.0.1:18188` | 8188 |
| studio MCP (pictures, animation, voice, music, the cut) | `studio-mcp-studio` | `http://127.0.0.1:8768/mcp` | none |
| cartoon MCP | `studio-mcp-cartoon` | `http://127.0.0.1:8769/mcp` | none |
| lectern MCP | `studio-mcp-lectern` | `http://127.0.0.1:8767/mcp` | none |
| highway3d MCP | `studio-mcp-highway3d` | `http://127.0.0.1:8766/mcp` | none |
| Jupyter | `jupyter` | `127.0.0.1:18080` | 8080 |

Paths and settings are in `/opt/studio-vast/bin/studio-env.sh` (source it first). The repo's
tools are in `/opt/highway3d`; the media library is `$STUDIO_MEDIA` and finished films are in
`$STUDIO_RENDERS`, both under Open WebUI's static folder so the chat can play them.

### Asking the director's model directly

```
curl -s http://127.0.0.1:18000/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model": "studio-llm", "messages": [{"role": "user", "content": "Plan a three-shot scene"}]}'
```

### Following a studio job

Jobs (animation, extension, composed music, assembly) log to `$STUDIO_WORK/job-<id>.log`:
a `JOB` line, `PROGRESS` lines, then `DONE {...}` or `FAILED reason`.

```
. /opt/studio-vast/bin/studio-env.sh; tail -f "$STUDIO_WORK"/job-*.log
```
