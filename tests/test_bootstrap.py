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


def test_doctor_reports_healthy(capsys):
    from cfet_tcad.workflow.cli import main

    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "all checks passed" in out
    assert "tiny end-to-end solve" in out


def test_explicit_env_wins(monkeypatch):
    monkeypatch.setenv("DEVSIM_MATH_LIBS", "libcustom.so")
    # must not overwrite a user-provided value
    cfet_tcad._ensure_devsim_math_libs()
    assert os.environ["DEVSIM_MATH_LIBS"] == "libcustom.so"


def test_frozen_windows_returns_bare_filename(tmp_path, monkeypatch):
    """Windows result must be a filename, never a path: DEVSIM reads
    DEVSIM_MATH_LIBS as a narrow string, so full paths break under
    non-ASCII install directories (e.g. a Chinese user name)."""
    internal = tmp_path / "_internal"
    internal.mkdir()
    (internal / "mkl_rt.2.dll").write_bytes(b"")
    monkeypatch.setattr(cfet_tcad.sys, "frozen", True, raising=False)
    monkeypatch.setattr(cfet_tcad.sys, "executable",
                        str(tmp_path / "cfet-tcad.exe"))
    monkeypatch.setattr(cfet_tcad, "_IS_WINDOWS", True)
    added, preloaded = [], []
    monkeypatch.setattr(cfet_tcad.os, "add_dll_directory",
                        lambda d: added.append(d), raising=False)
    monkeypatch.setattr(cfet_tcad, "_preload",
                        lambda dll: preloaded.append(dll))
    assert cfet_tcad._find_math_library() == "mkl_rt.2.dll"
    assert added == [str(internal)]  # directory registered with loaders
    assert os.environ["PATH"].startswith(str(internal))
    assert preloaded == [internal / "mkl_rt.2.dll"]  # full-path preload
