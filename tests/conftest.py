import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# an instance runs from its own dir, so template modules import each other by bare name
sys.path.insert(0, str(ROOT / "template"))
sys.path.insert(0, str(ROOT))
