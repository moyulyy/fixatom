import unittest

import numpy as np

from camera_views import STANDARD_VIEWS, standard_view


def quaternion_matrix(q):
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y*y + z*z), 2 * (x*y - z*w), 2 * (x*z + y*w)],
        [2 * (x*y + z*w), 1 - 2 * (x*x + z*z), 2 * (y*z - x*w)],
        [2 * (x*z - y*w), 2 * (y*z + x*w), 1 - 2 * (x*x + y*y)],
    ])


class CameraViewTests(unittest.TestCase):
    def test_directions_for_rotated_orthogonal_cells(self):
        rng = np.random.default_rng(42)
        for _ in range(12):
            basis, _ = np.linalg.qr(rng.normal(size=(3, 3)))
            cell = np.diag([8, 10, 12]) @ basis
            for name, (_, horizontal, sign, vertical) in STANDARD_VIEWS.items():
                with self.subTest(name=name):
                    result = standard_view(cell, name)
                    rotation = quaternion_matrix(result['quaternion'])
                    np.testing.assert_allclose(rotation @ rotation.T, np.eye(3), atol=1e-12)
                    self.assertAlmostEqual(np.linalg.det(rotation), 1)
                    np.testing.assert_allclose(rotation @ cell[horizontal], [sign * np.linalg.norm(cell[horizontal]), 0, 0], atol=1e-12)
                    np.testing.assert_allclose(rotation @ cell[vertical], [0, np.linalg.norm(cell[vertical]), 0], atol=1e-12)
                    self.assertFalse(result['skewed'])

    def test_skewed_cell_plane_and_real_angle_preserved(self):
        cell = np.array([[7., 0., 0.], [2., 8., 0.], [1., 3., 10.]])
        original = cell.copy()
        for name, (_, horizontal, sign, vertical) in STANDARD_VIEWS.items():
            result = standard_view(cell, name)
            rotation = quaternion_matrix(result['quaternion'])
            h, v = rotation @ cell[horizontal], rotation @ cell[vertical]
            np.testing.assert_allclose(h[1:], 0, atol=1e-12)
            self.assertGreater(h[0] * sign, 0)
            self.assertAlmostEqual(v[2], 0)
            self.assertGreater(v[1], 0)
            self.assertAlmostEqual(np.dot(h, v), np.dot(cell[horizontal], cell[vertical]))
            self.assertTrue(result['skewed'])
        np.testing.assert_array_equal(cell, original)

    def test_bottom_matches_explicit_top_definition(self):
        cell = np.diag([3, 4, 5])
        np.testing.assert_allclose(standard_view(cell, 'bottom')['quaternion'], standard_view(cell, 'top')['quaternion'])

    def test_invalid_cell_and_view(self):
        for cell in (np.zeros((3, 3)), np.eye(2), np.full((3, 3), np.nan)):
            with self.assertRaises(ValueError):
                standard_view(cell, 'front')
        with self.assertRaises(ValueError):
            standard_view(np.eye(3), 'invalid')


if __name__ == '__main__':
    unittest.main()
