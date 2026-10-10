from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "pipelines", ROOT / "pipelines" / "modeling", ROOT / "pipelines" / "modeling" / "src"):
    sys.path.insert(0, str(path))
