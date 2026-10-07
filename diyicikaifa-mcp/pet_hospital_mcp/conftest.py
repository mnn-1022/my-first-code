"""Make ``src`` importable so ``cd pet_hospital_mcp && pytest -q`` works even
without installing the package. Kept intentionally tiny; it is a no-op once the
package is installed."""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_ROOT, "src")

for _path in (_SRC, _ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)
