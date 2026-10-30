@echo off
rem Авто-запуск прототипа (Windows): проверяет зависимости и стартует Streamlit
cd /d "%~dp0"
if not exist .venv (
    py -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
streamlit run app.py
pause
