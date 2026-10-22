from computer_use.modes.browser import edge_attach_policy


def test_edge_attach_only():
    p = edge_attach_policy()
    assert p.attach_to_existing_edge_only is True
    assert p.allow_new_process_launch is False
    assert p.allow_cdp is False
