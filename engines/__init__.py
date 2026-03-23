"""AnnaSEO engines package — adds this folder to sys.path on import."""
import sys
from pathlib import Path
_here = str(Path(__file__).parent)
if _here not in sys.path:
    sys.path.insert(0, _here)
