# NVIDIA NIM API Key Proxy & Manager 🚀

Um servidor proxy de alta performance e baixa latência projetado para gerenciar e rotacionar automaticamente **múltiplas API Keys da NVIDIA NIM**. Oferece interface com dupla compatibilidade nativa: **OpenAI Compatible** (`/v1/chat/completions`) e **Anthropic Compatible** (`/v1/messages`) para integração perfeita com o **Claude Code**, Cursor, LibreChat e SDKs de IA.

---

### ✨ Destaques & Funcionalidades

- 🔄 **Rotação Automática Silenciosa (HTTP 429)**: Se uma chave atingir o Rate Limit (429), o proxy altera a flag `is_rate_limited=True`, faz o failover automático para a próxima chave disponível e atende a requisição sem erros para o usuário.
- 🎯 **Sondagem Ativa por Modelo (Probe a cada 30s)**: Quando uma chave entra em Rate Limit, o sistema sonda o modelo específico (`z-ai/glm-5.2`) em background a cada 30s com um teste ultra-leve de 1 token. Assim que retornar `HTTP 200`, a chave é reativada instantaneamente.
- 🛡️ **Segurança contra Keys Inválidas (HTTP 401/403)**: Se uma chave inválida ou não autorizada for detectada, ela é marcada como `is_invalid=True` e descartada automaticamente durante a sessão atual.
- 🔐 **Autenticação Proxy (`PROXY_API_KEY`)**: Gera e salva automaticamente uma chave mestre fixa no `.env` para proteger seus endpoints.
- ⚡ **Pool de Conexões HTTP Reutilizáveis (Keep-Alive)**: Reutilização de conexões TCP e TLS handshakes com a NVIDIA NIM, garantindo respostas rápidas em streaming.
- 📝 **Logging por Sessão em Tempo Real**: Gera um arquivo de log único por sessão em `logs/` registrando consumo de tokens (prompt, completion, total) e eventos de rotação sem spam.

---

### ⚙️ Configuração (`.env`)

Edite ou crie o arquivo `.env` na raiz do projeto (veja o `.env.example` para referência):

```env
# Insira suas chaves em linhas individuais (numeradas):
NVIDIA_API_KEY_1=nvapi-sua-chave-1
NVIDIA_API_KEY_2=nvapi-sua-chave-2
NVIDIA_API_KEY_3=nvapi-sua-chave-3

# Modelo Padrão fixo
DEFAULT_MODEL=z-ai/glm-5.2

# URL Base da NVIDIA NIM API
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1

# Intervalo em segundos para sondar chaves em Rate Limit
PROBE_INTERVAL_SECONDS=30

HOST=0.0.0.0
PORT=8000

# Chave de autenticação do seu servidor Proxy (gerada automaticamente na 1ª execução)
PROXY_API_KEY=sk-nim-...
```

---

### 🚀 Como Executar

#### Windows (com script executável):
Dê dois cliques no arquivo **`start.bat`**.

#### Terminal (manual):
```bash
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\python.exe -m app.main
```

---

### 🤖 Integração com o Claude Code

Configure o arquivo `~/.claude/settings.json` (ou `C:\Users\<SeuUsuario>\.claude\settings.json`):

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:8000",
    "ANTHROPIC_AUTH_TOKEN": "sua-PROXY_API_KEY-aqui",
    "ANTHROPIC_MODEL": "z-ai/glm-5.2",
    "CLAUDE_CODE_MAX_CONTEXT_TOKENS": "1000000"
  }
}
```

---

### 📡 Endpoints Disponíveis

| Endpoint | Método | Descrição |
| :--- | :--- | :--- |
| `POST /v1/chat/completions` | `POST` | Endpoint nativo compatível com a API da OpenAI. |
| `POST /v1/messages` | `POST` | Endpoint compatível com a API da Anthropic (usado pelo Claude Code). |
| `GET /v1/models` | `GET` | Retorna a lista de modelos disponíveis (compatível OpenAI). |
| `GET /health` | `GET` | Retorna o status do proxy e estatísticas de uso de cada chave. |
| `GET /api/hello` | `GET/HEAD` | Endpoint de ping rápido/healthcheck para o Claude Code. |

---

### 🧪 Executar Testes

```bash
.\.venv\Scripts\python.exe -m pytest tests/
```
