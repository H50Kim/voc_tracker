from computer_use.core.window_enum import StubWindowEnumerator, get_window_enumerator


def test_stub_lists_placeholder():
    enum = StubWindowEnumerator()
    wins = enum.list_windows()
    assert len(wins) >= 1


def test_factory_non_windows_is_stub():
    enum = get_window_enumerator()
    wins = enum.list_windows()
    assert wins
