# Starts the DishGenie backend (port 8000) and frontend (port 5173) in two windows.
$root = $PSScriptRoot
Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$root\backend'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$root\frontend'; npm run dev"
Write-Host "Backend: http://127.0.0.1:8000/docs   Frontend: http://localhost:5173"
