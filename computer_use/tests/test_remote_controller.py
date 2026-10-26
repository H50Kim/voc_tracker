"""Remote desktop controller — Linux stubs (no Win32)."""

from __future__ import annotations

import pytest
from PIL import Image

from computer_use.controllers.remote_controller import (
    RemoteClientKind,
    RemoteController,
    SessionHealthAction,
    StubRemoteWindowEnumerator,
    classify_remote_client,
    detect_black_screen,
    detect_session_health_from_title,
)
from computer_use.core.region import ScreenRegion


def test_classify_rdp_by_process():
    kind = classify_remote_client(
        title="My VM",
        process_name="msrdc.exe",
        window_class="",
    )
    assert kind == RemoteClientKind.RDP


def test_classify_citrix_by_title():
    kind = classify_remote_client(title="Apps - Citrix Workspace", process_name="")
    assert kind == RemoteClientKind.CITRIX


def test_detect_disconnect_title():
    signal = detect_session_health_from_title("Session Disconnected - Remote Desktop")
    assert signal is not None
    assert signal.action == SessionHealthAction.STOP


def test_detect_lock_title():
    signal = detect_session_health_from_title("Windows Security")
    assert signal is not None
    assert signal.action == SessionHealthAction.PAUSE


def test_stub_lists_remote_window():
    enum = StubRemoteWindowEnumerator()
    wins = enum.list_remote_windows()
    assert len(wins) == 1
    assert wins[0].handle == 9100
    assert wins[0].client_kind == RemoteClientKind.RDP


def test_binding_from_gui_selection():
    ctrl = RemoteController(enumerator=StubRemoteWindowEnumerator())
    user = ScreenRegion(100, 60, 400, 300)
    binding = ctrl.binding_from_gui_selection(window_handle=9100, user_screen_region=user)
    assert binding is not None
    assert binding.inner_relative.width == 400
    assert binding.inner_relative.left == 50


def test_capture_region_intersection():
    ctrl = RemoteController(enumerator=StubRemoteWindowEnumerator())
    inner = ScreenRegion(10, 10, 500, 400)
    cap = ctrl.capture_region_for(
        window_handle=9100,
        inner_relative=inner,
        user_region=ScreenRegion(200, 100, 200, 200),
    )
    assert cap is not None
    assert cap.width == 200


def test_session_health_minimized_stub():
    class MinStub(StubRemoteWindowEnumerator):
        def is_window_minimized(self, handle: int) -> bool:
            return handle == 9100

    ctrl = RemoteController(enumerator=MinStub())
    signal = ctrl.check_session_health(9100)
    assert signal is not None
    assert signal.action == SessionHealthAction.PAUSE


def test_black_screen_detection():
    black = Image.new("RGB", (64, 64), (0, 0, 0))
    assert detect_black_screen(black) is True
    white = Image.new("RGB", (64, 64), (240, 240, 240))
    assert detect_black_screen(white) is False


def test_coordinate_mapper_roundtrip():
    ctrl = RemoteController(enumerator=StubRemoteWindowEnumerator())
    inner = ScreenRegion(20, 30, 800, 600)
    mapper = ctrl.coordinate_mapper(window_handle=9100, inner_relative=inner)
    assert mapper is not None
    cap = mapper.capture_region()
    assert cap is not None
    screen = mapper.capture_relative_to_screen(10, 10)
    assert screen is not None
    back = mapper.screen_to_capture_relative(screen[0], screen[1])
    assert back == (10, 10)


@pytest.mark.windows
def test_remote_enumerator_import_on_windows():
    import sys

    if sys.platform != "win32":
        pytest.skip("windows only")
    from computer_use.controllers.remote_controller import Win32RemoteWindowEnumerator

    enum = Win32RemoteWindowEnumerator()
    assert isinstance(enum.list_remote_windows(), list)
