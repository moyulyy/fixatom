"""Run with python -m unittest discover -s tests -v."""
import tempfile
import unittest
import json
from pathlib import Path

import numpy as np
from ase import Atoms
from ase.constraints import FixAtoms, FixScaled
from ase.io import write

from structure_io import constraint_mask, export_poscar, has_valid_cell, load_structure, viewer_payload


class StructureIOTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Repeated element groups and a triclinic cell detect accidental sorting.
        self.atoms = Atoms("CuOCuH", scaled_positions=[[.1, .2, .3], [.3, .3, .3], [.6, .6, .6], [.8, .8, .8]],
                           cell=[[8, 0, 0], [1, 9, 0], [.5, 1, 10]], pbc=True)

    def test_poscar_roundtrip_partial_and_full_constraints(self):
        mask = np.array([[True, True, True], [False, True, False], [False, False, False], [True, False, True]])
        path = self.root / "POSCAR"
        export_poscar(path, self.atoms, mask)
        actual, locks = load_structure(path)
        self.assertEqual(actual.get_chemical_symbols(), self.atoms.get_chemical_symbols())
        np.testing.assert_allclose(actual.positions, self.atoms.positions, atol=1e-12)
        np.testing.assert_allclose(actual.cell, self.atoms.cell, atol=1e-12)
        np.testing.assert_array_equal(locks, mask)
        self.assertIn("Selective dynamics", path.read_text())
        self.assertEqual(self.atoms.constraints, [])

    def test_cif_and_xsd_to_poscar(self):
        for fmt in ("cif", "xsd"):
            with self.subTest(fmt=fmt):
                path = self.root / f"输入结构.{fmt}"
                write(path, self.atoms, format=fmt)
                imported, mask = load_structure(path)
                self.assertEqual(len(imported), 4)
                np.testing.assert_allclose(imported.positions, self.atoms.positions, atol=1e-8)
                mask[1] = True
                output = self.root / f"POSCAR_{fmt}"
                export_poscar(output, imported, mask)
                restored, locks = load_structure(output)
                np.testing.assert_array_equal(locks, mask)
                self.assertEqual(restored.get_chemical_symbols(), imported.get_chemical_symbols())

    def test_empty_locks_explicit_selective_dynamics(self):
        path = self.root / "unlocked.vasp"
        export_poscar(path, self.atoms, np.zeros((4, 3), bool))
        self.assertIn("Selective dynamics", path.read_text())
        self.assertFalse(load_structure(path)[1].any())

    def test_invalid_cell_does_not_overwrite_existing_file(self):
        path = self.root / "POSCAR"
        path.write_text("original")
        molecule = Atoms("H2", positions=[[0, 0, 0], [0, 0, .74]])
        self.assertFalse(has_valid_cell(molecule))
        with self.assertRaises(ValueError):
            export_poscar(path, molecule, np.zeros((2, 3), bool))
        self.assertEqual(path.read_text(), "original")

    def test_constraints_and_input_order(self):
        self.atoms.set_constraint([FixAtoms(indices=[0]), FixScaled(1, [True, False, True])])
        mask = constraint_mask(self.atoms)
        np.testing.assert_array_equal(mask[0], [True, True, True])
        np.testing.assert_array_equal(mask[1], [True, False, True])
        payload = viewer_payload(self.atoms)
        json.dumps(payload, allow_nan=False)
        self.assertEqual([a["index"] for a in payload["atoms"]], [0, 1, 2, 3])
        self.assertEqual([a["elem"] for a in payload["atoms"]], ["Cu", "O", "Cu", "H"])

    def test_no_periodic_long_bonds(self):
        atoms = Atoms("HH", positions=[[.1, 0, 0], [9.9, 0, 0]], cell=[10, 10, 10], pbc=True)
        self.assertEqual([a["bonds"] for a in viewer_payload(atoms)["atoms"]], [[], []])


if __name__ == "__main__":
    unittest.main()
