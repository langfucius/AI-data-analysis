"""Read-only local preservation/startup audit; not an installer or patcher."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import urllib.request


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    backup = root / ".backups/v3_20261103_142204"
    expected = json.loads((backup / "protected_hashes.json").read_text(encoding="utf-8"))
    checks = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() == digest for name, digest in expected.items()}
    original_changes = []
    for saved in sorted(backup.rglob("*")):
        if saved.is_file() and saved.name != "protected_hashes.json":
            relative = saved.relative_to(backup)
            current = root / relative
            if current.read_bytes() != saved.read_bytes():
                original_changes.append(str(relative))
    with urllib.request.urlopen("http://127.0.0.1:8513/_stcore/health", timeout=10) as response:
        health = {"status": response.status, "body": response.read().decode()}
    result = {"python": sys.executable, "protected_files_unchanged": checks,
              "modified_original_files": original_changes, "streamlit_health": health,
              "advanced_page_exists": (root / "app/ui/pages/2_Advanced_Analytics.py").exists()}
    print(json.dumps(result, ensure_ascii=True, indent=2))
    if not all(checks.values()) or health["status"] != 200:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
