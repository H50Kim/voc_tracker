"""Vision verify helpers (screen_diff, template_match)."""

from PIL import Image

from computer_use.vision.screen_diff import screen_diff_ratio, screens_unchanged
from computer_use.vision.template_match import template_match


def test_screen_diff_identical():
    img = Image.new("RGB", (32, 32), (128, 64, 32))
    assert screen_diff_ratio(img, img) < 0.01
    assert screens_unchanged(img, img)


def test_screen_diff_changed():
    a = Image.new("RGB", (32, 32), (0, 0, 0))
    b = Image.new("RGB", (32, 32), (255, 255, 255))
    assert screen_diff_ratio(a, b) > 0.5


def test_template_match_finds_patch():
    hay = Image.new("RGB", (100, 100), (200, 200, 200))
    for x in range(40, 60):
        for y in range(40, 60):
            hay.putpixel((x, y), (10, 20, 30))
    needle = hay.crop((40, 40, 60, 60))
    found = template_match(hay, needle, similarity_threshold=0.85)
    assert found == (40, 40)
