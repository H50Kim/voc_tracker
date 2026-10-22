import pytest

from computer_use.core.capture import ScreenCapture
from computer_use.core.region import ScreenRegion


@pytest.fixture
def capture():
    try:
        return ScreenCapture()
    except Exception as exc:  # mss may fail on headless CI
        pytest.skip(f"Screen capture unavailable: {exc}")


def test_capture_primary_monitor(capture: ScreenCapture):
    w, h = capture.primary_monitor_size()
    assert w > 0 and h > 0
    img = capture.capture_screen()
    assert img.width > 0 and img.height > 0


def test_capture_small_region(capture: ScreenCapture):
    region = ScreenRegion(0, 0, 50, 50)
    img = capture.capture_region(region)
    assert img.width == 50 and img.height == 50
