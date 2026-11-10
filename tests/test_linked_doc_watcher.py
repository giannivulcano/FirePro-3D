"""LinkedDocWatcher: folder watch + debounce + (mtime, size) compare (design D4)."""
from __future__ import annotations

import os
import time

from tests._linked_doc_helpers import (
    build_fixture_pdf, pump_until, rewrite_by_rename,
)


def _watch(path, debounce_ms=300):
    from firepro3d.linked_doc_watcher import LinkedDocWatcher
    st = os.stat(path)
    w = LinkedDocWatcher(debounce_ms=debounce_ms)
    hits = []
    w.changed.connect(hits.append)
    w.set_files({str(path): (st.st_mtime, st.st_size)})
    return w, hits


def test_temp_file_rename_fires_once_after_the_debounce(qapp, tmp_path):
    src = build_fixture_pdf(tmp_path / "spec.pdf", 2)
    w, hits = _watch(src)
    rewrite_by_rename(src, 3, "BETA")
    t0 = time.monotonic()
    assert pump_until(lambda: hits, 5)
    assert time.monotonic() - t0 >= 0.25            # debounced, not immediate
    pump_until(lambda: False, 0.6)                   # let any extra events drain
    assert len(hits) == 1
    assert os.path.normcase(hits[0]) == os.path.normcase(str(src))


def test_burst_of_saves_coalesces(qapp, tmp_path):
    src = build_fixture_pdf(tmp_path / "spec.pdf", 1)
    w, hits = _watch(src)
    for tag in ("B1", "B2-LONGER", "B3-LONGEST"):
        rewrite_by_rename(src, 1, tag)
    assert pump_until(lambda: hits, 5)
    pump_until(lambda: False, 0.6)
    assert len(hits) == 1


def test_other_files_in_the_folder_do_not_fire(qapp, tmp_path):
    src = build_fixture_pdf(tmp_path / "spec.pdf", 1)
    w, hits = _watch(src)
    (tmp_path / "~$spec.docx").write_bytes(b"lock file")
    (tmp_path / "notes.txt").write_text("x")
    pump_until(lambda: hits, 1.0)
    assert hits == []


def test_set_baseline_silences_an_applied_change(qapp, tmp_path):
    src = build_fixture_pdf(tmp_path / "spec.pdf", 1)
    w, hits = _watch(src)
    rewrite_by_rename(src, 2, "BETA")
    st = os.stat(src)
    w.set_baseline(str(src), st.st_mtime, st.st_size)  # the refresh took it
    pump_until(lambda: hits, 1.0)
    assert hits == []


def test_set_files_replaces_the_watched_folders(qapp, tmp_path):
    a = build_fixture_pdf(tmp_path / "a" / "spec.pdf", 1)
    b = build_fixture_pdf(tmp_path / "b" / "spec.pdf", 1)
    w, _hits = _watch(a)
    st = os.stat(b)
    w.set_files({str(b): (st.st_mtime, st.st_size)})
    dirs = {os.path.normcase(d) for d in w.watched_dirs()}
    assert dirs == {os.path.normcase(str(b.parent))}
    w.set_files({})
    assert w.watched_dirs() == []
