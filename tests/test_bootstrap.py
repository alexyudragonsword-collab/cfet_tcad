"""BLAS bootstrap: DEVSIM_MATH_LIBS resolution logic."""

import os

import cfet_tcad


def test_math_libs_resolved_on_this_platform():
    # the package import already ran the bootstrap; devsim loads in this
    # environment, so the variable must be set to something loadable
    assert os.environ.get("DEVSIM_MATH_LIBS")


def test_find_math_library_returns_existing_name():
    lib = cfet_tcad._find_math_library()
    assert lib
    # on Linux this is a soname resolvable by the loader; a frozen/Windows
    # result is a real path
    assert ("/" not in lib and "\\" not in lib) or os.path.exists(lib)


def test_explicit_env_wins(monkeypatch):
    monkeypatch.setenv("DEVSIM_MATH_LIBS", "libcustom.so")
    # must not overwrite a user-provided value
    cfet_tcad._ensure_devsim_math_libs()
    assert os.environ["DEVSIM_MATH_LIBS"] == "libcustom.so"
