import pytest

import cfet_tcad  # noqa: F401  (sets DEVSIM_MATH_LIBS before devsim loads)


@pytest.fixture()
def fresh_devsim():
    """DEVSIM keeps global state; reset it around every solver test."""
    import devsim
    cfet_tcad.reset()
    yield devsim
    cfet_tcad.reset()
