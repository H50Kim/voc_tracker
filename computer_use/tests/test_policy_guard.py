import pytest

from computer_use.policy.policy_guard import PolicyGuard, PolicyViolation


def test_blocks_cookie_extraction():
    guard = PolicyGuard()
    with pytest.raises(PolicyViolation):
        guard.check_text_action("read document.cookie")


def test_blocks_new_browser_launch():
    guard = PolicyGuard()
    with pytest.raises(PolicyViolation):
        guard.check_launch_browser(new_process=True)


def test_allows_attach_only_launch_check():
    guard = PolicyGuard()
    guard.check_launch_browser(new_process=False)
