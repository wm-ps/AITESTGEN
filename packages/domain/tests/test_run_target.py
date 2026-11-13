import pytest
from domain.run_target import normalize_browsers, validate_viewport


def test_no_browsers_means_the_default() -> None:
    assert normalize_browsers(None) == ["chromium"]


def test_reference_browser_is_moved_first() -> None:
    assert normalize_browsers(["webkit", "firefox", "chromium"]) == [
        "chromium",
        "webkit",
        "firefox",
    ]


def test_other_browsers_keep_the_order_given() -> None:
    assert normalize_browsers(["webkit", "firefox"]) == ["webkit", "firefox"]


@pytest.mark.parametrize(
    ("browsers", "message"),
    [
        ([], "at least one"),
        (["chromium", "chromium"], "only be selected once"),
        (["chromium", "edge"], "Unknown browser: edge"),
    ],
)
def test_invalid_browsers_are_rejected(browsers: list[str], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        normalize_browsers(browsers)


def test_no_size_means_the_default() -> None:
    assert validate_viewport(None, None) == (1280, 720)


def test_a_valid_size_is_returned() -> None:
    assert validate_viewport(1920, 1080) == (1920, 1080)


@pytest.mark.parametrize(("width", "height"), [(800, 500), (3840, 2160)])
def test_size_bounds_are_inclusive(width: int, height: int) -> None:
    assert validate_viewport(width, height) == (width, height)


@pytest.mark.parametrize(
    ("width", "height", "message"),
    [
        (1280, None, "both a width and a height"),
        (None, 720, "both a width and a height"),
        (799, 720, "Width must be between"),
        (3841, 720, "Width must be between"),
        (1280, 499, "Height must be between"),
        (1280, 2161, "Height must be between"),
    ],
)
def test_invalid_sizes_are_rejected(width: int | None, height: int | None, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_viewport(width, height)
