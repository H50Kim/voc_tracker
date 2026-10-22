from PIL import Image

from computer_use.core.validator import ResultValidator


def test_identical_images_high_similarity():
    img = Image.new("RGB", (64, 64), color=(10, 20, 30))
    v = ResultValidator(similarity_threshold=0.99)
    result = v.validate_unchanged(img, img.copy())
    assert result.passed
    assert result.before_hash == result.after_hash


def test_different_images_detect_change():
    a = Image.new("RGB", (32, 32), color=(0, 0, 0))
    b = Image.new("RGB", (32, 32), color=(255, 255, 255))
    v = ResultValidator()
    result = v.validate_changed(a, b, change_threshold=0.9)
    assert result.passed
