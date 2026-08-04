# NVIDIA NIM API Key Proxy & Manager 🚀

A high-performance, low-latency API proxy server designed to manage and automatically rotate **multiple NVIDIA NIM API Keys**. Features native dual-protocol compatibility: **OpenAI Compatible** (`/v1/chat/completions`) and **Anthropic Compatible** (`/v1/messages`) for seamless integration with **Claude Code**, Cursor, LibreChat, and custom AI SDKs.

---

### ✨ Features & Key Highlights

- 🔄 **Automatic & Transparent Failover (HTTP 429)**: If an API key hits a rate limit (HTTP 429), the proxy sets `is_rate_limited=True`, automatically rotates to the next available key, and serves the request seamlessly without client-side errors.
- 🎯 **Adaptive Exponential Backoff Probing (30s ➔ 60s ➔ 120s)**: Probes rate-limited keys using adaptive exponential backoff to minimize network overhead. As soon as HTTP 200 is returned, the key is immediately restored to active service.
- 📊 **Real-Time Terminal Dashboard (`nimproxy stats`)**: Interactive live terminal dashboard with 1000ms polling showing live token metrics, served requests, and key pool status. Press `q` anytime to return to terminal.
- 🎛️ **Quick CLI Commands (`nimproxy model` & `nimproxy key`)**: Instantly switch active models or add/remove API keys on the fly without running full setup.
- 🛡️ **Invalid Key Protection (HTTP 401/403)**: If an invalid or unauthorized key is detected, it is marked as `is_invalid=True` and discarded for the rest of the current server session.
- 🧹 **Automatic Log Retention**: Automatically limits session logs to a maximum of 20 log files and 30 days of retention.
- 🤖 **One-Click Claude Code Integration**: Automatically configures `~/.claude/settings.json` during setup or via `nimproxy claude`.
- ⚡ **High-Range Default Port (`43100`)**: Runs on port `43100` by default to avoid port collisions with common web development servers.

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
nimproxy stats            # Launch real-time live stats dashboard (1000ms polling, 'q' to exit)
nimproxy model            # List available models or view active model
nimproxy model set <name> # Switch active model instantly (e.g. meta/llama-3.3-70b-instruct)
nimproxy key list         # List all configured API keys
nimproxy key add <key>    # Add a new API key to failover pool
nimproxy key remove <key> # Remove an API key from pool
nimproxy setup            # Run interactive guided setup wizard
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
