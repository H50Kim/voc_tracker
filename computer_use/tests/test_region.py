from computer_use.core.region import ScreenRegion


def test_from_drag_normalizes():
    r = ScreenRegion.from_drag(10, 20, 110, 220)
    assert r.left == 10 and r.top == 20
    assert r.width == 100 and r.height == 200


def test_relative_point():
    r = ScreenRegion(100, 50, 200, 150)
    assert r.relative_point(10, 20) == (110, 70)


def test_clamp_to_monitor():
    r = ScreenRegion(-10, -10, 500, 500)
    c = r.clamp_to_monitor(0, 0, 400, 300)
    assert c.left >= 0 and c.top >= 0
    assert c.width <= 400
