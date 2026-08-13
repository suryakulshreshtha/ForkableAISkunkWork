"""Visual diffing, skipped cleanly when Pillow is absent."""

from __future__ import annotations

import pytest

from forkable_ai_agent.visual import PIL_AVAILABLE, VisualValidator

pytestmark = pytest.mark.skipif(not PIL_AVAILABLE, reason="Pillow not installed")


def _image(path, colour, size=(60, 40), blob=None):
    from PIL import Image

    img = Image.new("RGB", size, colour)
    if blob:
        for x in range(blob[0], blob[2]):
            for y in range(blob[1], blob[3]):
                img.putpixel((x, y), (255, 0, 0))
    img.save(path)
    return path


def test_identical_images_pass(settings, tmp_path):
    base = _image(tmp_path / "a.png", (250, 250, 250))
    actual = _image(tmp_path / "b.png", (250, 250, 250))
    outcome = VisualValidator(settings).compare_files(base, actual)
    assert outcome.passed and outcome.ratio == 0.0


def test_noise_below_tolerance_passes(settings, tmp_path):
    base = _image(tmp_path / "a.png", (250, 250, 250))
    actual = _image(tmp_path / "b.png", (247, 247, 247))  # within pixel_tolerance
    assert VisualValidator(settings).compare_files(base, actual).passed


def test_large_change_fails_and_writes_a_diff(settings, tmp_path):
    base = _image(tmp_path / "a.png", (250, 250, 250))
    actual = _image(tmp_path / "b.png", (250, 250, 250), blob=(0, 0, 40, 30))
    outcome = VisualValidator(settings).compare_files(base, actual)
    assert not outcome.passed
    assert outcome.ratio > 0.02
    assert outcome.diff_path


def test_size_change_is_reported(settings, tmp_path):
    base = _image(tmp_path / "a.png", (250, 250, 250), size=(60, 40))
    actual = _image(tmp_path / "b.png", (250, 250, 250), size=(80, 40))
    outcome = VisualValidator(settings).compare_files(base, actual)
    assert not outcome.passed and "size changed" in outcome.summary
