"""Visual UI validation.

Screenshot comparison with a per-channel noise tolerance and a changed-pixel
ratio threshold - antialiasing and cursor blink should not fail a build, a
moved button should. First run for a given name writes the baseline and passes,
which makes adopting visual checks a one-command operation.

Pillow is an optional dependency: without it the check degrades to a warning
instead of taking the suite down.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageChops
    PIL_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised on minimal installs
    Image = None  # type: ignore[assignment]
    ImageChops = None  # type: ignore[assignment]
    PIL_AVAILABLE = False


@dataclass
class VisualOutcome:
    name: str
    passed: bool
    ratio: float = 0.0
    summary: str = ""
    baseline_path: str = ""
    actual_path: str = ""
    diff_path: str = ""
    created_baseline: bool = False


class VisualValidator:
    def __init__(self, settings) -> None:
        self.settings = settings
        self.baseline_dir = settings.path(settings.visual.baseline_dir)
        self.diff_dir = settings.path(settings.visual.diff_dir)

    @staticmethod
    def available() -> bool:
        return PIL_AVAILABLE

    # ------------------------------------------------------------------
    def check(self, page: Any, name: str, full_page: bool = False, update: bool = False) -> VisualOutcome:
        if not PIL_AVAILABLE:
            return VisualOutcome(name=name, passed=True, summary="skipped: Pillow not installed")

        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name) or "page"
        self.baseline_dir.mkdir(parents=True, exist_ok=True)
        self.diff_dir.mkdir(parents=True, exist_ok=True)
        baseline = self.baseline_dir / f"{safe}.png"
        actual = self.diff_dir / f"{safe}.actual.png"

        page.screenshot(path=str(actual), full_page=full_page)

        if update or not baseline.exists():
            Image.open(actual).save(baseline)
            return VisualOutcome(
                name=name,
                passed=True,
                summary=f"baseline {'updated' if update else 'created'}: {baseline.name}",
                baseline_path=str(baseline),
                actual_path=str(actual),
                created_baseline=True,
            )
        return self.compare_files(baseline, actual, safe)

    # ------------------------------------------------------------------
    def compare_files(self, baseline: Path, actual: Path, safe: str | None = None) -> VisualOutcome:
        if not PIL_AVAILABLE:
            return VisualOutcome(name=str(actual), passed=True, summary="skipped: Pillow not installed")

        name = safe or Path(actual).stem
        base_img = Image.open(baseline).convert("RGB")
        actual_img = Image.open(actual).convert("RGB")

        if base_img.size != actual_img.size:
            return VisualOutcome(
                name=name,
                passed=False,
                ratio=1.0,
                summary=f"size changed {base_img.size} -> {actual_img.size}",
                baseline_path=str(baseline),
                actual_path=str(actual),
            )

        diff = ImageChops.difference(base_img, actual_img).convert("L")
        tolerance = self.settings.visual.pixel_tolerance
        mask = diff.point(lambda v: 255 if v > tolerance else 0)
        changed = sum(mask.point(lambda v: 1 if v else 0).getdata())
        total = base_img.size[0] * base_img.size[1]
        ratio = changed / total if total else 0.0
        passed = ratio <= self.settings.visual.max_diff_ratio

        diff_path = ""
        if not passed:
            overlay = actual_img.copy()
            red = Image.new("RGB", overlay.size, (255, 0, 90))
            overlay.paste(red, mask=mask)
            self.diff_dir.mkdir(parents=True, exist_ok=True)
            out = self.diff_dir / f"{name}.diff.png"
            overlay.save(out)
            diff_path = str(out)

        return VisualOutcome(
            name=name,
            passed=passed,
            ratio=ratio,
            summary=f"{ratio * 100:.2f}% pixels changed (limit {self.settings.visual.max_diff_ratio * 100:.2f}%)",
            baseline_path=str(baseline),
            actual_path=str(actual),
            diff_path=diff_path,
        )
