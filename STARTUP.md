# AlphaHive Startup Guide

## 🚀 Quick Start

The most reliable way to run AlphaHive is a hybrid approach (Docker for backend, Local for frontend):

### 1. Start Backend & Infrastructure (Docker)
```powershell
docker compose up -d
```
*Wait for the containers to initialize. This starts Postgres, Redis, Ollama, and the FastAPI Backend.*

### 2. Pull LLM Models (Required once)
Models are not bundled with the Ollama image. Run these commands while Docker is active:
```powershell
docker exec alphahive-ollama-1 ollama pull llama3.2:3b
docker exec alphahive-ollama-1 ollama pull llama3.1:8b
```

### 3. Start Frontend (Local)
The Docker frontend container can be unstable in some environments. Run it locally for better performance:
```powershell
cd frontend
npm install
npm run dev -- --port 3001
```

**Access the app at:** [http://localhost:3001](http://localhost:3001)

---

## 🛠️ Service Architecture

| Service | Host Port | Internal Port | Description |
| :--- | :--- | :--- | :--- |
| **Frontend** | `3001` | `3000` | Next.js Dashboard (on 3001 to avoid Grafana conflicts) |
| **Backend** | `8000` | `8000` | FastAPI Intelligence Engine |
| **Ollama** | `11434` | `11434` | Local LLM Server |
| **Postgres** | - | `5432` | Signal History & Agent Memory |
| **Redis** | - | `6379` | Cache & Pub/Sub for SSE |

---

## 🔍 Health Checks

Verify your setup by visiting these URLs:
- **Backend Health:** [http://localhost:8000/health](http://localhost:8000/health)
- **Watchlist Data:** [http://localhost:8000/watchlist](http://localhost:8000/watchlist)

## 💡 Troubleshooting

- **"API OFFLINE"**: Ensure the backend is running. If using `localhost` fails, try `127.0.0.1:8000`.
- **500 Errors on /analyze**: Check that both `llama3.2:3b` and `llama3.1:8b` are fully pulled on the Ollama server.
- **Hot Reload Issues**: Since the project is on OneDrive, hot-reloading in the browser may lag. A manual refresh usually resolves this.

---

> **SEBI Disclaimer:** For educational purposes only. Not investment advice. AlphaHive is not SEBI-registered. All trading decisions are entirely your own.