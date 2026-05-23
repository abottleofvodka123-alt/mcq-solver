@echo off
set GROQ_API_KEY=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
pip install -r requirements.txt -q
PsExec64.exe -s -i python mcq_solver_free.py
pause