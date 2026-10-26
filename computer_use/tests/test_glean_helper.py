from computer_use.controllers.browser_controller import EdgeWindowInfo
from computer_use.workflow.glean_helper import GleanHelper


def test_suggest_glean_tab_when_stub_has_glean():
    windows = [
        EdgeWindowInfo(handle=1, title="Company Glean — Microsoft Edge", tab_hint="Glean")
    ]
    helper = GleanHelper()
    msg = helper.suggest_open_glean_tab(windows)
    assert "Glean" in msg
    assert "후보" in msg or "candidate" in msg.lower()


def test_suggest_glean_tab_empty_list():
    helper = GleanHelper()
    msg = helper.suggest_open_glean_tab([])
    assert "찾지 못했습니다" in msg or "not" in msg.lower()
