"""Execute all notebooks in order (about 5-8 minutes).  Usage:  python run_all.py"""
import subprocess, sys, pathlib
root = pathlib.Path(__file__).resolve().parent
for nb in sorted(root.glob("0*.ipynb")):
    print("running", nb.name, flush=True)
    r = subprocess.run([sys.executable, "-m", "jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace", str(nb),
                        "--ExecutePreprocessor.timeout=1200"], cwd=root)
    if r.returncode:
        sys.exit(f"FAILED: {nb.name}")
print("all notebooks executed")
