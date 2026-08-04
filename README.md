# NVIDIA NIM API Key Proxy & Manager 🚀

A high-performance, low-latency API proxy server designed to manage and automatically rotate **multiple NVIDIA NIM API Keys**. Features native dual-protocol compatibility: **OpenAI Compatible** (`/v1/chat/completions`) and **Anthropic Compatible** (`/v1/messages`) for seamless integration with **Claude Code**, Cursor, LibreChat, and custom AI SDKs.

---

### ✨ Features & Key Highlights

- 🔄 **Automatic & Transparent Failover (HTTP 429)**: If an API key hits a rate limit (HTTP 429), the proxy sets `is_rate_limited=True`, automatically rotates to the next available key, and serves the request seamlessly without client-side errors.
- 🎯 **Active Model-Specific Probing (Every 30s)**: When a key enters Rate Limit state, a silent background task probes the target model (`z-ai/glm-5.2`) every 30s using an ultra-lightweight 1-token request. As soon as HTTP 200 is returned, the key is immediately restored to active service.
- 🛡️ **Invalid Key Protection (HTTP 401/403)**: If an invalid or unauthorized key is detected, it is marked as `is_invalid=True` and discarded for the rest of the current server session.
- 🤖 **One-Click Claude Code Integration**: Automatically configures `~/.claude/settings.json` during setup or via `nimproxy claude`.
- 🔐 **Proxy Authentication (`PROXY_API_KEY`)**: Automatically generates and saves a fixed master key in `config.json` / `.env` to secure your proxy endpoints.
- ⚡ **High-Range Default Port (`43100`)**: Runs on port `43100` by default to avoid port collisions with common web development servers.
- ⚡ **Persistent Connection Pooling (Keep-Alive)**: Reuses TCP sockets and TLS handshakes with NVIDIA NIM for near-instant streaming response start times.

---

### 🚀 One-Line Installation (Windows)

Run in PowerShell:
```powershell
irm https://raw.githubusercontent.com/moesuito/api-key-proxy-manager/main/install.ps1 | iex
```

This installs `nimproxy` in `%APPDATA%\nimproxy`, adds `nimproxy` to your `PATH`, and launches the guided setup wizard!

---

### 💻 CLI Commands (`nimproxy`)

```bash
nimproxy                  # Display server status report or auto-start background process
nimproxy setup            # Run interactive guided setup wizard (keys, model, autostart)
nimproxy claude           # Automatically configure Claude Code (~/.claude/settings.json)
nimproxy stop             # Stop background server process
nimproxy restart          # Restart background server process
nimproxy update           # Check GitHub releases for updates
nimproxy version          # Display version
```

---

### 🤖 Integration with Claude Code

Simply run:
```bash
nimproxy claude
```

Or manually configure `~/.claude/settings.json` (or `C:\Users\<YourUser>\.claude\settings.json`):

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:43100",
    "ANTHROPIC_AUTH_TOKEN": "your-PROXY_API_KEY-here",
    "ANTHROPIC_MODEL": "z-ai/glm-5.2"
  }
}
```

---

### 📡 API Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `POST /v1/chat/completions` | `POST` | Native OpenAI compatible chat completions endpoint (`http://localhost:43100/v1/chat/completions`). |
| `POST /v1/messages` | `POST` | Anthropic compatible messages endpoint (`http://localhost:43100/v1/messages`). |
| `GET /v1/models` | `GET` | Returns available models list (OpenAI compatible). |
| `GET /health` | `GET` | Returns proxy health status and key metrics. |
| `GET /api/hello` | `GET/HEAD` | Fast health check endpoint queried by Claude Code on startup. |

---

### 🧪 Running Tests

```bash
.\.venv\Scripts\python.exe -m pytest tests/
```
