from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "photo-deconstruct-svg" / "scripts" / "deconstruct_photo.py"
SPEC = importlib.util.spec_from_file_location("photo_deconstruct_micro_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class MicroContourFilterTests(unittest.TestCase):
    def radial_contour(self, radius: float = 30.0, count: int = 64) -> np.ndarray:
        angles = np.linspace(0.0, 2.0 * np.pi, count, endpoint=False)
        return np.column_stack((radius * np.cos(angles), radius * np.sin(angles)))

    def filtered(self, points: np.ndarray) -> np.ndarray:
        return np.asarray(
            MODULE.suppress_micro_contour_roughness(
                [tuple(point) for point in points],
                curve_smoothing=0.82,
                passes=2,
            )
        )

    def test_already_smooth_curve_is_unchanged(self) -> None:
        contour = self.radial_contour()
        displacement = np.linalg.norm(self.filtered(contour) - contour, axis=1)
        self.assertLess(float(displacement.max()), 1e-9)

    def test_micro_spike_is_reduced(self) -> None:
        contour = self.radial_contour()
        contour[0] *= 1.08
        displacement = np.linalg.norm(self.filtered(contour)[0] - contour[0])
        self.assertGreater(float(displacement), 1.0)

    def test_large_peak_is_preserved(self) -> None:
        contour = self.radial_contour()
        contour[0] *= 1.35
        displacement = np.linalg.norm(self.filtered(contour)[0] - contour[0])
        self.assertLess(float(displacement), 1e-9)


if __name__ == "__main__":
    unittest.main()
