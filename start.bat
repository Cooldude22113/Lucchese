@echo off
echo Starting Lucchese AI Assistant...

:: Start Ollama
start "Ollama" cmd /k "ollama serve"

:: Start FastAPI backend
start "Backend" cmd /k "cd /d C:\lucchese2\lucchese\backend && .venv\Scripts\activate && uvicorn main:app --reload --host 0.0.0.0 --port 8000"

:: Start Vite frontend
start "Frontend" cmd /k "cd /d C:\lucchese2\lucchese\frontend && npm run dev"

:: Start tunnel
start "Tunnel" cmd /k "cloudflared tunnel run lucchese"

echo All services started!
pause