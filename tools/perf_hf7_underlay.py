"""HF7 settle-redraw bench on the real drawings (AC12). Windowless, no cursor.

Usage: python tools/perf_hf7_underlay.py <out.txt> <tag> <dxf> [<dxf> ...]
Run from the tree under test, interleaved with the base tree.
"""
import os
import statistics
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.getcwd())
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication

app = QApplication([])
from firepro3d.dxf_import_worker import DxfImportWorker
from firepro3d.model_space import Model_Space
from firepro3d.underlay import Underlay

out, tag, paths = sys.argv[1], sys.argv[2], sys.argv[3:]


def line(text):
    with open(out, "a", encoding="utf-8") as f:
        f.write(f"{tag} {text}\n")


def bench(path):
    geoms = DxfImportWorker.extract_file_sync(path, skip_sanitize=True)
    n_fills = sum(g.get("kind") == "fill" for g in geoms)
    line(f"{os.path.basename(path)} geoms {len(geoms)} fills {n_fills}")
    sc = Model_Space()
    rec = Underlay(type="dxf", path=path)
    t1 = time.time()
    group, layers = sc._underlay_ctl._build_batched_underlay_group(geoms, rec)
    line(f"build {time.time() - t1:.2f}s items {len(group.childItems())}")
    rect = group.sceneBoundingRect()
    img = QImage(1920, 1080, QImage.Format.Format_ARGB32_Premultiplied)
    target = QRectF(0, 0, 1920, 1080)
    zoom = QRectF(rect.center().x() - rect.width() / 16, rect.center().y() - rect.height() / 16,
                  rect.width() / 8, rect.height() / 8)
    for label, src in (("fit", rect), ("zoom8", zoom)):
        times = []
        for _ in range(7):
            img.fill(0)
            p = QPainter(img)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            t = time.perf_counter()
            sc.render(p, target, src, Qt.AspectRatioMode.KeepAspectRatio)
            times.append((time.perf_counter() - t) * 1000)
            p.end()
        line(f"{label} median {statistics.median(times):.1f} min {min(times):.1f} max {max(times):.1f}")


for f in paths:
    bench(f)
