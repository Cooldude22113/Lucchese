@echo off
echo Starting Lucchese AI Assistant...

:: Start Ollama
start "Ollama" cmd /k "ollama serve"

:: Start FastAPI backend
start "Backend" cmd /k "cd /d C:\Lucchese\backend && venv\Scripts\activate && uvicorn main:app --reload --port 8000"

:: Start Vite frontend
start "Frontend" cmd /k "cd /d C:\Lucchese\frontend && npm run dev"

echo All services started!
echo   Ollama:   http://localhost:11434
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:5173
pause