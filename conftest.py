import sys
from pathlib import Path

# Make sure the repo root is on the path so `import mcp` and `import agent` work
sys.path.insert(0, str(Path(__file__).parent))
