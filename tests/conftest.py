import sys
from pathlib import Path

# GitHub's self-hosted runner invokes the installed `pytest` console script,
# whose sys.path does not reliably include the checkout root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
