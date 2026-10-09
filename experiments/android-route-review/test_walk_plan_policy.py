"""Distance/lap policy only: synthetic inspection metrics, no external calls."""
import copy
import math
import unittest

from walk_plan_policy import (MAX_LAPS, MAX_TARGET_DISTANCE_M, MIN_WALK_DISTANCE_M,
                              distance_bounds, inspect_walk_plan, make_walk_plan)


def valid_lap(distance):
    return dict(distance_m=distance, geometry_check='PASS', failures=[], unresolved=[],
                lap_validation=dict(status='PASS_GEOMETRY_ONLY', failures=[], unresolved=[]),
                paths=[[[127.0, 37.0], [127.001, 37.0], [127.0, 37.0]]])


class WalkPlanPolicyTests(unittest.TestCase):
    def test_constants_and_total_target_bounds(self):
        self.assertEqual((2000, 20000, 10),
                         (MIN_WALK_DISTANCE_M, MAX_TARGET_DISTANCE_M, MAX_LAPS))
        self.assertEqual([4500, 5500], distance_bounds(10000, 2))
        self.assertEqual([2000, 2200], distance_bounds(2000))
        self.assertEqual([1000, 1100], distance_bounds(2000, 2))

    def test_explicit_two_laps_use_actual_base_and_keep_geometry_unchanged(self):
        inspection = valid_lap(4900)
        plan = make_walk_plan(10000, 2, 5000)
        originals = copy.deepcopy((inspection, plan))
        result = inspect_walk_plan(inspection, plan)
        self.assertEqual('PASS_GEOMETRY_AND_DISTANCE_ONLY', result['status'])
        self.assertEqual(4900, result['base_api_distance_m'])
        self.assertEqual(9800, result['estimated_total_distance_m'])
        self.assertEqual([9000, 11000], result['total_distance_range_m'])
        self.assertEqual('UNVERIFIED', result['walking_access'])
        self.assertEqual(originals, (inspection, plan))
        self.assertNotIn('paths', result)

    def test_source_prediction_never_fills_missing_or_short_actual_distance(self):
        plan = make_walk_plan(10000, 2, 5000)
        result = inspect_walk_plan(valid_lap(4300), plan)
        self.assertEqual('FAIL', result['status'])
        self.assertEqual(8600, result['estimated_total_distance_m'])
        self.assertIn('WALK_PLAN_TARGET_DISTANCE_MISMATCH', result['failures'])
        for value in (None, 0, -1, True, '5000', math.nan, math.inf):
            with self.subTest(distance=value):
                result = inspect_walk_plan(valid_lap(value), plan)
                self.assertEqual('NOT_EVALUATED', result['status'])
                self.assertIsNone(result['estimated_total_distance_m'])

    def test_actual_total_under_2km_fails_even_inside_percent_tolerance(self):
        result = inspect_walk_plan(valid_lap(1900), make_walk_plan(2000, 1, 2050))
        self.assertEqual('FAIL', result['status'])
        self.assertIn('MIN_WALK_DISTANCE_NOT_REACHED', result['failures'])
        self.assertEqual([2000, 2200], result['total_distance_range_m'])

    def test_short_base_lap_is_allowed_when_explicit_total_meets_floor(self):
        result = inspect_walk_plan(valid_lap(1000), make_walk_plan(2000, 2, 1050))
        self.assertEqual('PASS_GEOMETRY_AND_DISTANCE_ONLY', result['status'])
        self.assertEqual(2000, result['estimated_total_distance_m'])

    def test_failed_base_is_not_promoted_by_repetition(self):
        inspection = valid_lap(4900)
        inspection.update(geometry_check='FAIL', failures=['TARGET_WATER_NOT_ENCLOSED'])
        inspection['lap_validation'].update(status='FAIL', failures=['TARGET_WATER_NOT_ENCLOSED'])
        result = inspect_walk_plan(inspection, make_walk_plan(10000, 2, 5000))
        self.assertEqual('FAIL', result['status'])
        self.assertIn('TARGET_WATER_NOT_ENCLOSED', result['failures'])

    def test_misa_base_repetition_and_crossing_reviews_survive_explicit_laps(self):
        inspection = valid_lap(2785)
        inspection.update(geometry_check='INCOMPLETE', exact_edge_retraced_distance_m=416.2,
                          unresolved=['REPETITION_AND_TOPOLOGY_REVIEW_REQUIRED'])
        inspection['lap_validation'].update(status='INCOMPLETE', unresolved=['LAP_NON_SIMPLE_GEOMETRY'])
        result = inspect_walk_plan(inspection, make_walk_plan(5600, 2, 3108))
        self.assertEqual('INCOMPLETE', result['status'])
        self.assertEqual(5570, result['estimated_total_distance_m'])
        self.assertIn('REPETITION_AND_TOPOLOGY_REVIEW_REQUIRED', result['unresolved'])
        self.assertIn('LAP_NON_SIMPLE_GEOMETRY', result['unresolved'])

    def test_missing_lap_evidence_cannot_become_a_validated_repeat(self):
        inspection = valid_lap(5000)
        del inspection['lap_validation']
        result = inspect_walk_plan(inspection, make_walk_plan(10000, 2, 5000))
        self.assertEqual('INCOMPLETE', result['status'])
        self.assertIn('BASE_LAP_GEOMETRY_CHECK_NOT_PASSED', result['unresolved'])

    def test_null_distance_preserves_one_lap_and_does_not_invent_a_goal(self):
        plan = make_walk_plan(None, 1, 2100)
        self.assertIsNone(plan['requested_total_distance_m'])
        self.assertEqual('SOURCE_PROPOSAL_ONLY', plan['status'])
        result = inspect_walk_plan(valid_lap(2050), plan)
        self.assertIsNone(result['requested_total_distance_m'])
        self.assertEqual([2000, None], result['total_distance_range_m'])
        self.assertEqual('PASS_GEOMETRY_AND_DISTANCE_ONLY', result['status'])
        result = inspect_walk_plan(valid_lap(1900), make_walk_plan(None, 1, 1950))
        self.assertEqual('FAIL', result['status'])
        with self.assertRaises(ValueError):
            make_walk_plan(None, 2, 1950)

    def test_invalid_requests_and_nonfinite_source_are_rejected(self):
        for target in (1999, 20001, 0, -1, True, '10000', math.nan, math.inf, 10**400):
            with self.subTest(target=target), self.assertRaises(ValueError):
                make_walk_plan(target, 2, 5000)
        for laps in (0, 11, 2.0, True, None, math.inf):
            with self.subTest(laps=laps), self.assertRaises(ValueError):
                make_walk_plan(10000, laps, 5000)
        for source in (None, 0, -1, True, '5000', math.nan, math.inf, 1e308, 10**400):
            with self.subTest(source=source), self.assertRaises(ValueError):
                make_walk_plan(10000, 2, source)
        with self.assertRaises(ValueError):
            distance_bounds(None)

    def test_changed_source_plan_is_rejected(self):
        for field, value in [('source_total_distance_m', 12000), ('distance_scope', 'INCLUDING_HOME'),
                             ('status', 'APPROVED')]:
            plan = make_walk_plan(10000, 2, 5000)
            plan[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                inspect_walk_plan(valid_lap(5000), plan)


if __name__ == '__main__':
    unittest.main()
