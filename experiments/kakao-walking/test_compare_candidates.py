"""Reject/hold before ranking; no real API calls or synthesized route geometry."""
import copy
import unittest

from compare_candidates import assess, compare, trial_summary


class CandidateComparisonTests(unittest.TestCase):
    def setUp(self):
        self.candidate = dict(requested_duration_minutes=38, source_expected_roundtrip_m=2500,
                              distance_range_m=[2000, 3000])
        self.inspection = dict(api_status="OK", geometry_check="PASS", failures=[], unresolved=[],
                               distance_m=2520, time_s=2280, geometry_distance_m=2510,
                               river_validation={"status": "PASS_GEOMETRY_ONLY"},
                               target_validation={"status": "PASS_API_TIME_ONLY"},
                               distance_validation={"status": "PASS_API_DISTANCE_ONLY"},
                               source_distance_comparison={"status": "WITHIN_TRIAL_THRESHOLD"})

    def test_invalid_but_perfect_time_candidate_cannot_win_over_validated_geometry(self):
        bad = copy.deepcopy(self.inspection)
        bad.update(geometry_check="FAIL", failures=["RIVER_UNNECESSARY_DIRECTION_REVERSAL"])
        good = copy.deepcopy(self.inspection); good["time_s"] = 2310
        result = compare([trial_summary("invalid", "SHORTEST", bad, self.candidate),
                          trial_summary("valid", "SHORTEST", good, self.candidate)], 2)
        self.assertEqual("valid", result["best_candidate_id"])
        self.assertEqual("NOT_ACCEPTED", result["recommendation_quality"])

    def test_no_winner_is_returned_when_every_response_fails_or_needs_review(self):
        bad = copy.deepcopy(self.inspection); bad["geometry_check"] = "FAIL"
        hold = copy.deepcopy(self.inspection)
        hold["unresolved"] = ["RIVER_STEP_CONNECTION_REVIEW_REQUIRED"]
        result = compare([trial_summary("failed", "SHORTEST", bad, self.candidate),
                          trial_summary("held", "SHORTEST", hold, self.candidate)], 3)
        self.assertEqual("NO_VALIDATED_CANDIDATE", result["status"])
        self.assertIsNone(result["best_candidate_id"])
        self.assertEqual(1, result["untested_candidates"])
        self.assertTrue(all(t["comparison_key"] is None for t in result["trials"]))

    def test_missing_checks_or_invalid_metrics_cannot_be_scored(self):
        for field in ["river_validation", "target_validation", "distance_validation", "source_distance_comparison"]:
            data = copy.deepcopy(self.inspection); data.pop(field)
            self.assertFalse(assess(data, self.candidate)["eligible_for_comparison"])
        for value in [0, True, float("nan"), float("inf"), None]:
            data = copy.deepcopy(self.inspection); data["time_s"] = value
            self.assertIsNone(trial_summary("missing", "SHORTEST", data, self.candidate)["comparison_key"])
        self.assertEqual("REJECTED", assess(self.inspection, self.candidate, 401)["status"])

    def test_only_measured_time_and_length_agreement_order_eligible_candidates(self):
        first = trial_summary("first", "SHORTEST", self.inspection, self.candidate)
        second_data = copy.deepcopy(self.inspection); second_data["geometry_distance_m"] = 2500
        second = trial_summary("second", "SHORTEST", second_data, self.candidate)
        self.assertEqual("second", compare([first, second], 2)["best_candidate_id"])
        self.assertEqual("UNVERIFIED", second["decision"]["walking_access"])

    def test_failed_distance_check_is_rejected_even_if_aggregate_failure_list_is_empty(self):
        data = copy.deepcopy(self.inspection); data["distance_validation"]["status"] = "FAIL"
        self.assertEqual("REJECTED", assess(data, self.candidate)["status"])


if __name__ == "__main__":
    unittest.main()
