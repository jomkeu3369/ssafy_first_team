import os
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_main_import_does_not_eagerly_load_vector_libraries() -> None:
    code = "import sys; import main; assert 'faiss' not in sys.modules; assert 'numpy' not in sys.modules"
    result = subprocess.run([sys.executable, "-c", code], cwd=PROJECT_ROOT, env=os.environ.copy(), capture_output=True, text=True, timeout=30, check=False)

    assert result.returncode == 0, result.stderr


def test_start_script_limits_threads_workers_and_concurrency() -> None:
    script = (PROJECT_ROOT / "scripts" / "start.sh").read_text(encoding="utf-8")

    assert "OPENBLAS_NUM_THREADS=1" in script
    assert "OMP_NUM_THREADS=1" in script
    assert "WEB_CONCURRENCY=1" in script
    assert "--workers 1" in script
    assert "--limit-concurrency" in script


def test_remote_vector_server_import_does_not_eagerly_load_vector_libraries() -> None:
    code = "import sys; import src.mcp_servers.remote_vector_server; assert 'faiss' not in sys.modules; assert 'numpy' not in sys.modules"
    result = subprocess.run([sys.executable, "-c", code], cwd=PROJECT_ROOT, env=os.environ.copy(), capture_output=True, text=True, timeout=30, check=False)

    assert result.returncode == 0, result.stderr
