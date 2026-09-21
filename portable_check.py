"""Optional diagnostics that run inside the actual portable EXE."""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

import numpy as np
from PySide6.QtWidgets import QApplication

from ball_settings import BallSettingsDialog
from camera_views import standard_view
from structure_io import export_poscar, load_structure


def run_check(window, output: Path, examples: Path):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance()
    report = {'passed': False, 'frozen': bool(getattr(sys, 'frozen', False)),
              'executable': sys.executable, 'checks': []}
    load_errors = []

    def load_failed(message):
        load_errors.append(message)
        window.loading = False
    window.load_failed = load_failed

    def wait_for(predicate, timeout=35):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            if load_errors:
                raise RuntimeError(load_errors[-1])
            if predicate():
                return
            time.sleep(.015)
        raise TimeoutError('Timed out waiting for the portable GUI / WebGL renderer')

    def js(code):
        result = []
        window.web.page().runJavaScript(code, result.append)
        wait_for(lambda: bool(result))
        return result[0]

    try:
        wait_for(lambda: window.viewer_ready)
        assert not window.windowIcon().isNull(), 'Missing window icon'
        report['checks'].append('QtWebEngine, QWebChannel and custom icon initialized')
        for name in ('Cu111.cif', 'Cu111.xsd', 'POSCAR_Cu111'):
            window.load_path(examples / name)
            wait_for(lambda: not window.loading)
            wait_for(lambda: js('generation') == window.generation)
            assert len(window.atoms) == 64
            assert js('model.selectedAtoms({}).length') == 64
            assert js("!!document.querySelector('#viewer canvas')")
            report['checks'].append(f'{name}: ASE loading + 64 atoms rendered')
        window.edit_all('release')
        window.edit_indices([0, 1, 2], 'fix')
        window.mask[3] = [True, False, True]
        window.send_state()
        wait_for(lambda: js('masks.filter(m => m.every(Boolean)).length') == 3)
        target = output / 'POSCAR_selftest'
        export_poscar(target, window.atoms, window.mask)
        _, restored = load_structure(target)
        np.testing.assert_array_equal(restored, window.mask)
        window.saved_mask = window.mask.copy()
        report['checks'].append('Selective dynamics: full and partial constraints round-trip')
        for name in window.standard_view_buttons:
            window.set_standard_view(name)
            expected = standard_view(window.atoms.cell.array, name)['quaternion']
            wait_for(lambda: np.allclose(json.loads(js('JSON.stringify(viewer.getView().slice(4,8))')), expected))
        window.projection_combo.setCurrentIndex(1)
        wait_for(lambda: js('viewer.camera.ortho') is False)
        window.projection_combo.setCurrentIndex(0)
        wait_for(lambda: js('viewer.camera.ortho') is True)
        report['checks'].append('Six standard views and orthographic/perspective cameras')
        dialog = BallSettingsDialog(window.ball_overrides, {'Cu': 64}, 'ball', window)
        assert len(dialog.element_buttons) == 118
        dialog.deleteLater()
        report['checks'].append('Periodic table: 118 elements')
        window.load_demo()
        wait_for(lambda: js('generation') == window.generation)
        wait_for(lambda: js('model.selectedAtoms({}).length') == 64)
        app.processEvents()
        time.sleep(.3)
        app.processEvents()
        window.grab().save(str(output / 'portable-window.png'))
        report['checks'].append('Bundled ASE Cu(111) demo and screenshot')
        report['passed'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        window.grab().save(str(output / 'portable-error.png'))
    finally:
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        window.saved_mask = window.mask.copy()
        window.cell_dirty = False
        window.loading = False
        window.close()
        app.processEvents()
    return 0 if report['passed'] else 1
