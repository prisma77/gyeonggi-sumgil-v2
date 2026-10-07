"""Synthetic regressions for an explicit, bounded comparison input."""
import unittest

from compare_input_point import alternative
from test_sources import source, way


class AlternativeInputTests(unittest.TestCase):
    def fixture(self):
        data = source([way(1, [1, 2, 3], [(127, 37), (127.0002, 37), (127.0005, 37)], bridge="yes"),
                       way(2, [3, 4], [(127.0005, 37), (127.001, 37)], foot="designated"),
                       way(3, [10, 11], [(127.00001, 37), (127.00002, 37)], foot="designated")])
        site = {"sample_node_ids": [1], "walk_points": [[127, 37]],
                "walk_points_reviewed": True, "review": {"status": "REVIEWED"},
                "shoreline_offset_m": [5]}
        return data, site

    def test_nearby_disconnected_ground_node_is_not_selected(self):
        data, site = self.fixture()
        result = alternative(data, site, 0)
        self.assertEqual(3, result["input_change"]["alternative_source_node"])
        self.assertFalse(result["walk_points_reviewed"])
        self.assertEqual([1], site["sample_node_ids"])

    def test_input_change_limit_is_not_silently_expanded(self):
        data, site = self.fixture()
        with self.assertRaises(ValueError):
            alternative(data, site, 0, max_move=10)

    def test_wrong_node_coordinate_stops_comparison(self):
        data, site = self.fixture()
        site["walk_points"][0] = [127.1, 37]
        with self.assertRaises(ValueError):
            alternative(data, site, 0)

    def test_old_shoreline_offsets_are_not_reused_for_changed_point(self):
        data, site = self.fixture()
        result = alternative(data, site, 0)
        self.assertNotIn("shoreline_offset_m", result)


if __name__ == "__main__":
    unittest.main()
