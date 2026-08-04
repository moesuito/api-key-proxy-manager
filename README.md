# NVIDIA NIM API Key Proxy & Manager 🚀

A high-performance, low-latency API proxy server designed to manage and automatically rotate **multiple NVIDIA NIM API Keys**. Features native dual-protocol compatibility: **OpenAI Compatible** (`/v1/chat/completions`) and **Anthropic Compatible** (`/v1/messages`) for seamless integration with **Claude Code**, Cursor, LibreChat, and custom AI SDKs.

---

### ✨ Features & Key Highlights

- 🔄 **Automatic & Transparent Failover (HTTP 429)**: If an API key hits a rate limit (HTTP 429), the proxy sets `is_rate_limited=True`, automatically rotates to the next available key, and serves the request seamlessly without client-side errors.
- 🎯 **Active Model-Specific Probing (Every 30s)**: When a key enters Rate Limit state, a silent background task probes the target model (`z-ai/glm-5.2`) every 30s using an ultra-lightweight 1-token request. As soon as HTTP 200 is returned, the key is immediately restored to active service.
- 🛡️ **Invalid Key Protection (HTTP 401/403)**: If an invalid or unauthorized key is detected, it is marked as `is_invalid=True` and discarded for the rest of the current server session.
- 🔐 **Proxy Authentication (`PROXY_API_KEY`)**: Automatically generates and saves a fixed master key in `.env` to secure your proxy endpoints.
- ⚡ **Persistent Connection Pooling (Keep-Alive)**: Reuses TCP sockets and TLS handshakes with NVIDIA NIM for near-instant streaming response start times.
- 📝 **Real-Time Per-Session Logging**: Generates session log files in `logs/` tracking token consumption (prompt, completion, total) and key rotation events without log spam.

---

### ⚙️ Configuration (`.env`)

Create or edit `.env` in the project root directory (refer to `.env.example`):

```env
# Register API Keys in individual lines (numbered):
NVIDIA_API_KEY_1=nvapi-your-key-1
NVIDIA_API_KEY_2=nvapi-your-key-2
NVIDIA_API_KEY_3=nvapi-your-key-3

# Fixed Default Model
DEFAULT_MODEL=z-ai/glm-5.2

# NVIDIA NIM Base URL
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1

# Probe interval in seconds for rate-limited keys
PROBE_INTERVAL_SECONDS=30

HOST=0.0.0.0
PORT=8000

# Fixed Proxy Master API Key (auto-generated on first launch)
PROXY_API_KEY=sk-nim-...
```

---

### 🚀 How to Run

#### Windows (using batch script):
Double click **`start.bat`**.

#### Terminal (manual):
```bash
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\python.exe -m app.main
```

---

### 🤖 Integration with Claude Code

Configure `~/.claude/settings.json` (or `C:\Users\<YourUser>\.claude\settings.json`):

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:8000",
    "ANTHROPIC_AUTH_TOKEN": "your-PROXY_API_KEY-here",
    "ANTHROPIC_MODEL": "z-ai/glm-5.2",
    "CLAUDE_CODE_MAX_CONTEXT_TOKENS": "1000000"
  }
}
```

---

### 📡 API Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `POST /v1/chat/completions` | `POST` | Native OpenAI compatible chat completions endpoint. |
| `POST /v1/messages` | `POST` | Anthropic compatible messages endpoint (used by Claude Code). |
| `GET /v1/models` | `GET` | Returns available models list (OpenAI compatible). |
| `GET /health` | `GET` | Returns proxy health status and key metrics. |
| `GET /api/hello` | `GET/HEAD` | Fast health check endpoint queried by Claude Code on startup. |

---

### 🧪 Running Tests

```bash
.\.venv\Scripts\python.exe -m pytest tests/
```
