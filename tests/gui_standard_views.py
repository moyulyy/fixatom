"""Click all six view buttons and check actual 3Dmol screen projection."""
import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from ase import Atoms
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import MainWindow, STYLESHEET
from camera_views import STANDARD_VIEWS, standard_view
from structure_io import viewer_payload, export_poscar

app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLESHEET)
temporary = tempfile.TemporaryDirectory()
window = MainWindow(preferences_path=Path(temporary.name) / 'preferences.json')
window.show()
artifacts = Path(__file__).parent / 'artifacts'
artifacts.mkdir(exist_ok=True)


def wait_for(predicate):
    until = time.monotonic() + 25
    while time.monotonic() < until:
        app.processEvents()
        if predicate():
            return
        QTest.qWait(25)
    raise AssertionError('Timed out waiting for standard view')


def js(code):
    result = []
    window.web.page().runJavaScript(code, result.append)
    wait_for(lambda: bool(result))
    return result[0]


def current_quaternion():
    return json.loads(js('JSON.stringify(viewer.getView().slice(4,8))'))


try:
    assert not any(button.isEnabled() for button in window.standard_view_buttons.values())
    wait_for(lambda: window.viewer_ready)
    rotation = np.array([[.36, -.8, .48], [.8, 0, -.6], [.48, .6, .64]])
    cells = [np.diag([8., 10., 12.]), np.diag([8., 10., 12.]) @ rotation,
             np.array([[8., 0., 0.], [3., 10., 0.], [2., 1., 12.]]) @ rotation]
    for cell in cells:
        atoms = Atoms('Cu8', scaled_positions=[[x, y, z] for x in (.2, .8) for y in (.2, .8) for z in (.2, .8)], cell=cell, pbc=True)
        mask = np.zeros((8, 3), bool)
        mask[0] = True
        window.accept_structure(atoms, mask, viewer_payload(atoms), str(Path(temporary.name) / 'POSCAR'))
        wait_for(lambda: js('generation') == window.generation)
        before = Path(temporary.name) / 'POSCAR_before'
        after = Path(temporary.name) / 'POSCAR_after'
        export_poscar(before, window.atoms, window.mask)
        for projection in ('orthographic', 'perspective'):
            window.projection_combo.setCurrentIndex(window.projection_combo.findData(projection))
            wait_for(lambda: js('cameraState.projection') == projection)
            for name, (_, horizontal, sign, vertical) in STANDARD_VIEWS.items():
                # Disturb the orientation before every click, including identical top/bottom.
                js("viewer.rotate(23, 'x'); viewer.rotate(11, 'z'); viewer.render();")
                QTest.mouseClick(window.standard_view_buttons[name], Qt.MouseButton.LeftButton)
                expected = standard_view(cell, name)
                wait_for(lambda: np.allclose(current_quaternion(), expected['quaternion'], atol=1e-10))
                points = np.array([[0., 0., 0.], cell[horizontal], cell[vertical]])
                raw = json.dumps([dict(zip(('x', 'y', 'z'), point)) for point in points])
                projected = json.loads(js(f'JSON.stringify(viewer.modelToScreen({raw}))'))
                origin, h, v = [np.array([p['x'], p['y']]) for p in projected]
                self_h, self_v = h - origin, v - origin
                assert self_h[0] * sign > 0, (name, projection, self_h)
                # 3Dmol uses Float32 transform matrices: allow 0.001 CSS pixel.
                assert abs(self_h[1]) < 1e-3, (name, projection, self_h)
                assert self_v[1] < 0, (name, projection, self_v)
                if not expected['skewed']:
                    assert abs(self_v[0]) < 1e-3, (name, projection, self_v)
                assert js('cameraState.projection') == projection
        export_poscar(after, window.atoms, window.mask)
        assert before.read_bytes() == after.read_bytes()
        # Native rectangle picking after the last camera change.
        window.edit_all('release')
        window.set_mode('box')
        wait_for(lambda: js('mode') == 'box')
        points = json.loads(js('JSON.stringify(structure.atoms.map(a => viewer.modelToScreen(a)))'))
        left, right = int(min(p['x'] for p in points)) - 2, int(sum(p['x'] for p in points) / len(points))
        top, bottom = int(min(p['y'] for p in points)) - 2, int(max(p['y'] for p in points)) + 2
        expected_ids = {i for i, p in enumerate(points) if left <= p['x'] <= right and top <= p['y'] <= bottom}
        assert 0 < len(expected_ids) < 8
        receiver = window.web.focusProxy() or window.web
        QTest.mousePress(receiver, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(left, top))
        QTest.mouseMove(receiver, QPoint(right, bottom), 80)
        QTest.mouseRelease(receiver, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(right, bottom))
        wait_for(lambda: set(np.flatnonzero(window.mask.all(axis=1))) == expected_ids)
        window.saved_mask = window.mask.copy()
    molecule = Atoms('H2', positions=[[0, 0, 0], [0, 0, .74]])
    window.accept_structure(molecule, np.zeros((2, 3), bool), viewer_payload(molecule), 'molecule.xsd')
    assert not any(button.isEnabled() for button in window.standard_view_buttons.values())
    window.load_demo()
    wait_for(lambda: js('generation') == window.generation)
    window.projection_combo.setCurrentIndex(0)
    window.set_mode('rotate')
    QTest.mouseClick(window.standard_view_buttons['front'], Qt.MouseButton.LeftButton)
    wait_for(lambda: np.allclose(current_quaternion(), standard_view(window.atoms.cell.array, 'front')['quaternion']))
    QTest.qWait(250)
    window.grab().save(str(artifacts / 'standard-views.png'))
    print('PASS: all six buttons, both projection modes, axis-aligned/rotated/skew cells, exact screen directions, top=bottom, unchanged POSCAR, post-view rectangle picking, no-cell disabled.')
finally:
    window.saved_mask = window.mask.copy()
    window.cell_dirty = False
    window.close()
    app.processEvents()
    temporary.cleanup()
