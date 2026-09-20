@echo off
REM Creates .venv, installs requirements and registers a Jupyter kernel.  Usage: setup_env.bat   (Python 3.10+)
python -m venv .venv || goto :err
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt || goto :err
python -m ipykernel install --user --name aml-fraud --display-name "Python (aml-fraud venv)"
echo Done. Activate with:  .venv\Scripts\activate   then:  jupyter lab   (or: python run_all.py)
goto :eof
:err
echo Setup failed & exit /b 1
