"""Exercise fullscreen layout and the real periodic-table settings dialog."""
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
from ase import Atoms
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QLabel, QLineEdit, QPushButton

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import MainWindow, STYLESHEET
from ball_settings import BallSettingsDialog, element_appearance, load_preferences, periodic_positions
from structure_io import viewer_payload, export_poscar

app = QApplication([])
app.setStyle('Fusion')
app.setFont(QFont('Microsoft YaHei UI', 10))
app.setStyleSheet(STYLESHEET)
temporary = tempfile.TemporaryDirectory()
window = MainWindow(preferences_path=Path(temporary.name) / 'ball_settings.json')
artifacts = Path(__file__).parent / 'artifacts'
artifacts.mkdir(exist_ok=True)
window.show()


def wait_for(predicate, timeout=25):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        app.processEvents()
        if predicate():
            return
        QTest.qWait(40)
    raise AssertionError('GUI did not reach the expected state')


def js(code):
    result = []
    window.web.page().runJavaScript(code, result.append)
    wait_for(lambda: bool(result))
    return result[0]


def run_dialog(callback):
    errors = []

    def edit():
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, BallSettingsDialog)
            callback(dialog)
        except BaseException as error:
            errors.append(error)
            if dialog:
                dialog.reject()
    QTimer.singleShot(200, edit)
    window.open_ball_settings()
    if errors:
        raise errors[0]


try:
    assert len(periodic_positions()) == 118
    for symbol in periodic_positions():
        assert element_appearance(symbol, {}, 'space')['diameter'] > 0
    atoms = Atoms('Cu2O2H2', positions=[[0, 0, 0], [3, 0, 0], [0, 2, 0], [3, 2, 0], [.4, 2.7, 0], [3.4, 2.7, 0]],
                  cell=[7, 6, 5], pbc=True)
    masks = np.zeros((6, 3), bool)
    masks[0] = True
    masks[2] = [True, False, True]
    window.accept_structure(atoms, masks, viewer_payload(atoms), str(Path(temporary.name) / 'Cu-O-H.vasp'))
    wait_for(lambda: window.viewer_ready)
    wait_for(lambda: js("typeof model !== 'undefined' && !!model && model.selectedAtoms({}).length") == 6)
    assert js("document.querySelectorAll('.legend-row').length") == 3
    assert js("!!model.selectedAtoms({index:0})[0].style.sphere")
    ratio = js("meshRadius(structure.atoms[0]) / model.selectedAtoms({index:0})[0].style.sphere.radius")
    assert abs(ratio - 1.12) < 1e-10
    for change_window in (window.showMaximized, window.showFullScreen, window.showNormal):
        change_window()
        QTest.qWait(300)
        sidebar = window.sidebar_scroll.widget()
        for label in sidebar.findChildren(QLabel):
            assert label.height() >= label.fontMetrics().height() + 6, label.text()
            if label.wordWrap():
                assert label.height() >= label.heightForWidth(label.width()), label.text()
        for edit in sidebar.findChildren(QLineEdit):
            # Spin boxes own their padding; their internal editor only needs text height.
            padding = 0 if isinstance(edit.parentWidget(), QAbstractSpinBox) else 20
            assert edit.height() >= edit.fontMetrics().height() + padding
        if window.isFullScreen():
            window.grab().save(str(artifacts / 'fullscreen-appearance.png'))
        window.sidebar_scroll.verticalScrollBar().setValue(window.sidebar_scroll.verticalScrollBar().maximum())
        assert window.vacuum_button.visibleRegion().isEmpty() is False
        window.sidebar_scroll.verticalScrollBar().setValue(0)

    before = Path(temporary.name) / 'POSCAR_before'
    after = Path(temporary.name) / 'POSCAR_after'
    export_poscar(before, window.atoms, window.mask)

    def customize(dialog):
        assert len(dialog.element_buttons) == 118
        QTest.mouseClick(dialog.element_buttons['Cu'], Qt.MouseButton.LeftButton)
        assert dialog.selected == 'Cu'
        with patch('ball_settings.QColorDialog.getColor', return_value=QColor('#4385ed')):
            QTest.mouseClick(dialog.color_button, Qt.MouseButton.LeftButton)
        dialog.diameter.setValue(1.6)
        wait_for(lambda: js("appearance.Cu.diameter") == 1.6)
        assert js("model.selectedAtoms({elem:'Cu'})[0].style.sphere.color") == '#4385ed'
        assert js("model.selectedAtoms({elem:'Cu'})[0].style.sphere.radius") == .8
        assert js("document.querySelector('#legend').innerText.includes('1.6')")
        QTest.qWait(200)
        dialog.grab().save(str(artifacts / 'periodic-table.png'))
        dialog.accept()

    run_dialog(customize)
    assert load_preferences(window.preferences_path)['Cu'] == {'color': '#4385ed', 'diameter': 1.6}
    np.testing.assert_array_equal(window.mask, masks)
    assert not window.dirty
    export_poscar(after, window.atoms, window.mask)
    assert before.read_bytes() == after.read_bytes(), 'Visual settings must never modify POSCAR'

    def cancel(dialog):
        dialog.select_element('Cu')
        dialog.diameter.setValue(3.)
        dialog.reject()
    run_dialog(cancel)
    wait_for(lambda: js('appearance.Cu.diameter') == 1.6)
    assert window.ball_overrides['Cu']['diameter'] == 1.6

    def reset(dialog):
        dialog.select_element('Cu')
        dialog.reset_element()
        assert 'Cu' not in dialog.overrides
        dialog.reject()
    run_dialog(reset)
    wait_for(lambda: js('appearance.Cu.diameter') == 1.6)
    for index in (1, 2, 0):
        window.style_combo.setCurrentIndex(index)
        wait_for(lambda: js('style') == window.style_combo.currentData())
        assert js("model.selectedAtoms({elem:'Cu'})[0].style.sphere.radius") == .8
        assert abs(js('meshRadius(structure.atoms[0])') - .896) < 1e-10
    window.grab().save(str(artifacts / 'customized-elements.png'))
    print('PASS: maximized/fullscreen/normal layout, all 118 elements, retained solid balls, outer mesh ratio, legend, element click/color/diameter, preview/cancel/reset/save, unchanged POSCAR.')
finally:
    window.saved_mask = window.mask.copy()
    window.cell_dirty = False
    window.close()
    app.processEvents()
    temporary.cleanup()
