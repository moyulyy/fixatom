"""Real QtWebEngine smoke test. Creates screenshots under tests/artifacts/."""
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import MainWindow, STYLESHEET
from structure_io import export_poscar, load_structure


app = QApplication([])
app.setStyle("Fusion")
app.setStyleSheet(STYLESHEET)
window = MainWindow(preferences_path=Path(__file__).parent / 'artifacts' / 'smoke-preferences.json')
window.show()
window.load_demo()
artifacts = Path(__file__).parent / "artifacts"
artifacts.mkdir(exist_ok=True)


def wait_for(predicate, timeout=20):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        app.processEvents()
        if predicate():
            return
        QTest.qWait(30)
    raise AssertionError("Timed out waiting for GUI")


def js(code):
    result = []
    window.web.page().runJavaScript(code, lambda value: result.append(value))
    wait_for(lambda: bool(result))
    return result[0]


try:
    wait_for(lambda: window.viewer_ready)
    wait_for(lambda: js("typeof model !== 'undefined' && !!model && model.selectedAtoms({}).length") == 64)
    QTest.qWait(900)
    assert js("!!document.querySelector('#viewer canvas')")
    assert js("viewer.getModel().selectedAtoms({}).length") == 64
    assert int(window.mask.all(axis=1).sum()) == 32
    window.grab().save(str(artifacts / "studio-demo.png"))

    # Real pointer click: find the atom hit by the 3Dmol raycaster, then click it.
    window.edit_all("release")
    window.set_mode("point")
    QTest.qWait(250)
    target = json.loads(js("JSON.stringify(viewer.modelToScreen(structure.atoms[63]))"))
    receiver = window.web.focusProxy() or window.web
    QTest.mouseClick(receiver, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(round(target['x']), round(target['y'])))
    wait_for(lambda: window.mask.any())
    assert window.mask.all(axis=1).sum() == 1, "Point click should toggle one atom"
    QTest.mouseClick(receiver, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(round(target['x']), round(target['y'])))
    wait_for(lambda: not window.mask.any())

    # Actual DOM pointer event handlers, with document-space projected coordinates.
    window.set_mode("box")
    QTest.qWait(150)
    js("""(() => {
      const points = structure.atoms.map(a => viewer.modelToScreen(a));
      window.testBounds = {left: Math.min(...points.map(p=>p.x))-3, right: Math.max(...points.map(p=>p.x))+3,
        top: Math.min(...points.map(p=>p.y))-3, bottom: Math.max(...points.map(p=>p.y))+3};
      return true;
    })()""")
    # Qt mouse events exercise pointer capture as well as pointer handlers.
    bounds = json.loads(js("JSON.stringify(testBounds)"))
    start = QPoint(int(bounds['left']), int(bounds['top']))
    end = QPoint(int(bounds['right']), int(bounds['bottom']))
    QTest.mousePress(receiver, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(receiver, end, 100)
    QTest.mouseRelease(receiver, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
    wait_for(lambda: window.mask.all())
    QTest.mousePress(receiver, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, start)
    QTest.mouseMove(receiver, end, 100)
    QTest.mouseRelease(receiver, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, end)
    wait_for(lambda: not window.mask.any())
    window.undo()
    assert window.mask.all()
    window.redo()
    assert not window.mask.any()

    # Rotate and select just half the projection; this catches coordinate offsets.
    js("viewer.rotate(37, 'y'); viewer.render();")
    points = json.loads(js("JSON.stringify(structure.atoms.map(a => viewer.modelToScreen(a)))"))
    left = int(min(p['x'] for p in points)) - 2
    right = int(sum(p['x'] for p in points) / len(points))
    top = int(min(p['y'] for p in points)) - 2
    bottom = int(max(p['y'] for p in points)) + 2
    expected = {i for i, p in enumerate(points) if left <= p['x'] <= right and top <= p['y'] <= bottom}
    assert 0 < len(expected) < 64
    QTest.mousePress(receiver, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(left, top))
    QTest.mouseMove(receiver, QPoint(right, bottom), 100)
    QTest.mouseRelease(receiver, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(right, bottom))
    wait_for(lambda: set(np.flatnonzero(window.mask.all(axis=1))) == expected)
    window.edit_all('release')

    # Stale selections from a previous document must be ignored.
    window.bridge.selectAtoms(json.dumps({"generation": window.generation - 1, "indices": [0], "action": "fix"}))
    assert not window.mask.any()
    window.index_edit.setText("1-8, 12, 16")
    window.edit_typed("fix")
    assert window.mask.all(axis=1).sum() == 10
    export_poscar(artifacts / "POSCAR_smoke", window.atoms, window.mask)
    _, restored = load_structure(artifacts / "POSCAR_smoke")
    np.testing.assert_array_equal(restored, window.mask)
    for index in (1, 2, 0):
        window.style_combo.setCurrentIndex(index)
        QTest.qWait(100)
        assert js("style") == window.style_combo.currentData()

    # Exercise the actual export action and background loading, including partial masks.
    window.mask[20] = [True, False, True]
    with patch('app.QFileDialog.getSaveFileName', return_value=(str(artifacts / 'POSCAR_gui'), '')):
        assert window.save_dialog()
    assert not window.dirty
    window.load_path(artifacts / 'POSCAR_gui')
    wait_for(lambda: not window.loading)
    np.testing.assert_array_equal(window.mask[20], [True, False, True])
    for source in ('Cu111.cif', 'Cu111.xsd'):
        window.load_path(Path(__file__).resolve().parents[1] / 'examples' / source)
        wait_for(lambda: not window.loading)
        assert len(window.atoms) == 64
        assert js('structure.atoms.length') == 64

    window.load_demo()
    window.edit_all("release")
    window.edit_indices(list(range(32)), "fix")
    window.set_mode("point")
    wait_for(lambda: js("mode") == 'point' and js("generation") == window.generation)
    wait_for(lambda: js("masks.filter(m => m.every(Boolean)).length") == 32)
    QTest.qWait(300)
    window.grab().save(str(artifacts / "studio-verified.png"))
    print("PASS: WebGL render, native point toggle, rectangle fix/release, rotated subset selection, undo/redo, index edit, stale event guard, styles, GUI POSCAR export, background CIF/XSD/POSCAR loading.")
finally:
    window.saved_mask = window.mask.copy()
    window.cell_dirty = False
    window.close()
    app.processEvents()
