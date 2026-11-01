"""Write the deterministic synthetic simulation-measurement calibration fixture."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.ml.compensation import default_calibration_dataset  # noqa: E402

OUTPUT_PATH = PROJECT_ROOT / "data" / "calibration" / "synthetic_calibration_v1.json"


def main() -> int:
    dataset = default_calibration_dataset()
    dataset.save(OUTPUT_PATH)
    print(f"Wrote {len(dataset.cases)} calibration cases to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
