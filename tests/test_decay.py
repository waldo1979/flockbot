import pytest

from utils.time_helpers import decay_weight


@pytest.mark.parametrize(
    "weeks,expected",
    [
        (0.0, 1.0),
        (1.0, 1.0),
        (2.0, 1.0),
        (2.1, 0.75),
        (3.0, 0.75),
        (4.0, 0.75),
        (4.1, 0.50),
        (5.0, 0.50),
        (6.0, 0.50),
        (6.1, 0.25),
        (7.0, 0.25),
        (8.0, 0.25),
        (8.1, 0.0),
        (12.0, 0.0),
        (100.0, 0.0),
    ],
)
def test_decay_weight(weeks, expected):
    assert decay_weight(weeks) == expected
