
"""Initialize the sample SQLite database."""
from pathlib import Path
import sys

# Add the project root to Python's module search path.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.seed import initialize_database


if __name__ == "__main__":
    path = initialize_database(force=True)
    print(f"Sample database created: {path}")
