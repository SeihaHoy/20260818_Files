#!/usr/bin/env bash
# Creates .venv, installs requirements and registers a Jupyter kernel.  Usage: bash setup_env.sh   (Python 3.10+)
set -e
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m ipykernel install --user --name aml-fraud --display-name "Python (aml-fraud venv)"
echo "Done. Activate with:  source .venv/bin/activate   then:  jupyter lab   (or: python run_all.py)"
