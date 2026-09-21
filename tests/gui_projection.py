"""Verify actual camera projection, screen-space picking, fog, and ICO loading."""
import json
import struct
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from ase import Atoms
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QIcon
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import MainWindow, ROOT, STYLESHEET
from structure_io import viewer_payload

app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLESHEET)
temporary = tempfile.TemporaryDirectory()
window = MainWindow(preferences_path=Path(temporary.name) / 'ball_settings.json')
window.show()
artifacts = Path(__file__).parent / 'artifacts'
artifacts.mkdir(exist_ok=True)


def wait_for(predicate):
    until = time.monotonic() + 25
    while time.monotonic() < until:
        app.processEvents()
        if predicate():
            return
        QTest.qWait(35)
    raise AssertionError('Timed out waiting for projection state')


def js(code):
    result = []
    window.web.page().runJavaScript(code, result.append)
    wait_for(lambda: bool(result))
    return result[0]


try:
    icon = ROOT / 'assets' / 'fixatoms.ico'
    assert struct.unpack('<HHH', icon.read_bytes()[:6]) == (0, 1, 7)
    assert not window.windowIcon().isNull()
    assert len(QIcon(str(icon)).availableSizes()) == 7
    assert not QIcon(str(icon)).pixmap(32, 32).isNull()
    atoms = Atoms('C4', positions=[[-2, 0, -4], [2, 0, -4], [-2, 0, 4], [2, 0, 4]], cell=[10, 10, 12])
    window.accept_structure(atoms, np.zeros((4, 3), bool), viewer_payload(atoms), str(Path(temporary.name) / 'projection.vasp'))
    wait_for(lambda: window.viewer_ready)
    wait_for(lambda: js("typeof model !== 'undefined' && !!model && model.selectedAtoms({}).length") == 4)
    js('let v = viewer.getView(); v.splice(4, 4, 0, 0, 0, 1); viewer.setView(v); viewer.render();')
    ratios = []
    for mode in ('orthographic', 'perspective'):
        window.projection_combo.setCurrentIndex(window.projection_combo.findData(mode))
        wait_for(lambda: js('cameraState.projection') == mode)
        assert js('viewer.camera.ortho') == (mode == 'orthographic')
        assert window.view_angle.isEnabled() == (mode == 'perspective')
        points = json.loads(js('JSON.stringify(structure.atoms.map(a => viewer.modelToScreen(a)))'))
        widths = [abs(points[1]['x'] - points[0]['x']), abs(points[3]['x'] - points[2]['x'])]
        ratios.append(max(widths) / min(widths))
        window.set_mode('box')
        wait_for(lambda: js('mode') == 'box')
        receiver = window.web.focusProxy() or window.web
        left = int(min(p['x'] for p in points)) - 3
        right = int(sum(p['x'] for p in points) / 4)
        top = int(min(p['y'] for p in points)) - 8
        bottom = int(max(p['y'] for p in points)) + 8
        expected = {i for i, p in enumerate(points) if left <= p['x'] <= right and top <= p['y'] <= bottom}
        QTest.mousePress(receiver, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(left, top))
        QTest.mouseMove(receiver, QPoint(right, bottom), 100)
        QTest.mouseRelease(receiver, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(right, bottom))
        wait_for(lambda: set(np.flatnonzero(window.mask.all(axis=1))) == expected)
        assert expected == {0, 2}
        window.edit_all('release')
        wait_for(lambda: js('masks.some(m => m.some(Boolean))') is False)
    assert abs(ratios[0] - 1) < 1e-8, ratios
    assert ratios[1] > 1.05, ratios
    window.view_angle.setValue(60)
    wait_for(lambda: js('viewer.camera.fov') == 60)
    window.depth_check.setChecked(True)
    window.depth_slider.setValue(85)
    wait_for(lambda: js('cameraState.depthIntensity') == 85)
    assert js('viewer.config.disableFog') is False
    assert js('viewer.scene.fog.near < viewer.scene.fog.far')
    window.depth_check.setChecked(False)
    wait_for(lambda: js('viewer.config.disableFog') is True)
    assert not window.depth_slider.isEnabled()
    window.load_demo()
    wait_for(lambda: js('structure.atoms.length') == 64)
    assert js('cameraState.projection') == 'perspective'
    assert js('viewer.camera.fov') == 60
    window.set_mode('rotate')
    window.view_angle.setValue(45)
    window.depth_check.setChecked(True)
    window.depth_slider.setValue(60)
    window.sidebar_scroll.verticalScrollBar().setValue(window.sidebar_scroll.verticalScrollBar().maximum())
    wait_for(lambda: js('cameraState.depthIntensity') == 60)
    js('viewer.zoomTo(); viewer.render();')
    QTest.qWait(250)
    window.grab().save(str(artifacts / 'projection-settings.png'))
    print(f'PASS: 7-size ICO, window icon, equal orthographic scale, perspective foreshortening (ratios={ratios}), both projection rectangle picks, FOV, fog on/off, camera retained on new document.')
finally:
    window.saved_mask = window.mask.copy()
    window.cell_dirty = False
    window.close()
    app.processEvents()
    temporary.cleanup()
