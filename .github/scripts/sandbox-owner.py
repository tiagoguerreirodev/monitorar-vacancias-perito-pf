"""[DEBUG-uf-linux] Compatibility entrypoint for the canonical packaged owner."""
from pathlib import Path
import runpy

if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).resolve().parents[2] /
                       'perito_dashboard/collector/runtime-owner.py'), run_name='__main__')
