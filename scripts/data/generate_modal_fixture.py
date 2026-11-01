"""Write the deterministic synthetic modal dataset fixture."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.ml.modal_inversion import default_modal_dataset  # noqa: E402

OUTPUT_PATH = PROJECT_ROOT / "data" / "modal" / "synthetic_modes_v1.json"


def main() -> int:
    dataset = default_modal_dataset()
    dataset.save(OUTPUT_PATH)
    print(f"Wrote {len(dataset.modes)} modes to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
