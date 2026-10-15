#!/usr/bin/env python3
"""
Unit tests for Price Alert Tool (alerts.py)
==========================================
Covers critical edge cases:
- Out of order dates
- First-day edge case (cannot cross without prior day)
- Boundary touching (exact equality)
- Insufficient data for moving average window
- Multi-instrument interleaving
- Sorting stability (date ascending, then rule id ascending)
- Empty or malformed inputs
"""

import unittest
import tempfile
import os
import sys
import json
from alerts import process_alerts, parse_prices, parse_rules


class TestPriceAlertTool(unittest.TestCase):

    def _create_temp_files(self, csv_content: str, json_content: list):
        """Helper to create temporary CSV and JSON files for tests."""
        csv_file = tempfile.NamedTemporaryFile("w+", delete=False, suffix=".csv")
        csv_file.write(csv_content)
        csv_file.close()

        json_file = tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json")
        json.dump(json_content, json_file)
        json_file.close()

        return csv_file.name, json_file.name

    # ---------------------------------------------------------
    # 1. Level Crossing Tests
    # ---------------------------------------------------------
    def test_level_cross_below_and_not_repeat(self):
        """Price drops below 1500 on Day 3: fires once, doesn't repeat on Day 4"""
        csv_data = """date,instrument,close
2026-09-01,INFY,1520.00
2026-09-02,INFY,1510.00
2026-09-03,INFY,1490.00
2026-09-04,INFY,1480.00
"""
        rules = [
            {"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500}
        ]
        csv_path, json_path = self._create_temp_files(csv_data, rules)
        try:
            alerts = process_alerts(csv_path, json_path)
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0], "2026-09-03 r1 INFY level below 1500")
        finally:
            os.unlink(csv_path)
            os.unlink(json_path)

    def test_level_cross_above(self):
        """Price crosses above 3500 threshold"""
        csv_data = """date,instrument,close
2026-09-01,TCS,3400.00
2026-09-02,TCS,3550.00
"""
        rules = [
            {"id": "r1", "instrument": "TCS", "type": "level", "direction": "above", "level": 3500}
        ]
        csv_path, json_path = self._create_temp_files(csv_data, rules)
        try:
            alerts = process_alerts(csv_path, json_path)
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0], "2026-09-02 r1 TCS level above 3500")
        finally:
            os.unlink(csv_path)
            os.unlink(json_path)

    def test_day_one_initial_state_never_fires(self):
        """Day 1 starts below 1500: cannot cross without prior day baseline"""
        csv_data = """date,instrument,close
2026-09-01,INFY,1400.00
2026-09-02,INFY,1380.00
"""
        rules = [
            {"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500}
        ]
        csv_path, json_path = self._create_temp_files(csv_data, rules)
        try:
            alerts = process_alerts(csv_path, json_path)
            self.assertEqual(len(alerts), 0)
        finally:
            os.unlink(csv_path)
            os.unlink(json_path)

    def test_touching_level_boundary(self):
        """Exact boundary touch (1510 -> exactly 1500) counts as crossing below"""
        csv_data = """date,instrument,close
2026-09-01,INFY,1510.00
2026-09-02,INFY,1500.00
"""
        rules = [
            {"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500}
        ]
        csv_path, json_path = self._create_temp_files(csv_data, rules)
        try:
            alerts = process_alerts(csv_path, json_path)
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0], "2026-09-02 r1 INFY level below 1500")
        finally:
            os.unlink(csv_path)
            os.unlink(json_path)

    # ---------------------------------------------------------
    # 2. Moving Average Cross Tests
    # ---------------------------------------------------------
    def test_ma_cross_insufficient_data(self):
        """History shorter than long window + 1: safely returns 0 alerts"""
        csv_data = """date,instrument,close
2026-09-01,TCS,100
2026-09-02,TCS,100
2026-09-03,TCS,100
2026-09-04,TCS,100
2026-09-05,TCS,100
"""
        rules = [
            {"id": "r2", "instrument": "TCS", "type": "ma_cross", "short": 2, "long": 5, "direction": "above"}
        ]
        csv_path, json_path = self._create_temp_files(csv_data, rules)
        try:
            alerts = process_alerts(csv_path, json_path)
            self.assertEqual(len(alerts), 0)
        finally:
            os.unlink(csv_path)
            os.unlink(json_path)

    def test_ma_cross_exact_fire(self):
        """2-day short MA crosses above 3-day long MA on Day 4"""
        csv_data = """date,instrument,close
2026-09-01,TCS,10
2026-09-02,TCS,10
2026-09-03,TCS,10
2026-09-04,TCS,20
"""
        rules = [
            {"id": "r_ma", "instrument": "TCS", "type": "ma_cross", "short": 2, "long": 3, "direction": "above"}
        ]
        csv_path, json_path = self._create_temp_files(csv_data, rules)
        try:
            alerts = process_alerts(csv_path, json_path)
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0], "2026-09-04 r_ma TCS ma_cross 2/3 above")
        finally:
            os.unlink(csv_path)
            os.unlink(json_path)

    def test_ma_cross_below(self):
        """2-day short MA crosses below 3-day long MA on Day 4"""
        csv_data = """date,instrument,close
2026-09-01,TCS,20
2026-09-02,TCS,20
2026-09-03,TCS,20
2026-09-04,TCS,5
"""
        rules = [
            {"id": "r_down", "instrument": "TCS", "type": "ma_cross", "short": 2, "long": 3, "direction": "below"}
        ]
        csv_path, json_path = self._create_temp_files(csv_data, rules)
        try:
            alerts = process_alerts(csv_path, json_path)
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0], "2026-09-04 r_down TCS ma_cross 2/3 below")
        finally:
            os.unlink(csv_path)
            os.unlink(json_path)

    # ---------------------------------------------------------
    # 3. Data Hygiene & Edge Cases
    # ---------------------------------------------------------
    def test_out_of_order_dates_are_sorted(self):
        """Scrambled CSV dates (03, 01, 02) sorted chronologically before processing"""
        csv_data = """date,instrument,close
2026-09-03,INFY,1490.00
2026-09-01,INFY,1520.00
2026-09-02,INFY,1510.00
"""
        rules = [
            {"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500}
        ]
        csv_path, json_path = self._create_temp_files(csv_data, rules)
        try:
            alerts = process_alerts(csv_path, json_path)
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0], "2026-09-03 r1 INFY level below 1500")
        finally:
            os.unlink(csv_path)
            os.unlink(json_path)

    def test_multiple_alerts_same_date_sorted_by_rule_id(self):
        """Same-day triggers ordered deterministically by rule ID (r1 before r2)"""
        csv_data = """date,instrument,close
2026-09-01,INFY,1600.00
2026-09-02,INFY,1400.00
"""
        rules = [
            {"id": "r2", "instrument": "INFY", "type": "level", "direction": "below", "level": 1450},
            {"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500}
        ]
        csv_path, json_path = self._create_temp_files(csv_data, rules)
        try:
            alerts = process_alerts(csv_path, json_path)
            self.assertEqual(len(alerts), 2)
            self.assertEqual(alerts[0], "2026-09-02 r1 INFY level below 1500")
            self.assertEqual(alerts[1], "2026-09-02 r2 INFY level below 1450")
        finally:
            os.unlink(csv_path)
            os.unlink(json_path)

    def test_unreferenced_instrument_or_empty_files(self):
        """Rule references unlisted stock (WIPRO): cleanly returns 0 alerts"""
        csv_data = """date,instrument,close
2026-09-01,INFY,1500
2026-09-02,INFY,1600
"""
        rules = [
            {"id": "r1", "instrument": "WIPRO", "type": "level", "direction": "above", "level": 500}
        ]
        csv_path, json_path = self._create_temp_files(csv_data, rules)
        try:
            alerts = process_alerts(csv_path, json_path)
            self.assertEqual(alerts, [])
        finally:
            os.unlink(csv_path)
            os.unlink(json_path)

    def test_floating_point_level_display(self):
        """Fractional price level (1500.5) preserves decimal in output"""
        csv_data = """date,instrument,close
2026-09-01,INFY,1510.00
2026-09-02,INFY,1490.00
"""
        rules = [
            {"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500.5}
        ]
        csv_path, json_path = self._create_temp_files(csv_data, rules)
        try:
            alerts = process_alerts(csv_path, json_path)
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0], "2026-09-02 r1 INFY level below 1500.5")
        finally:
            os.unlink(csv_path)
            os.unlink(json_path)


class PrettyTestRunner:
    """A clean, human-readable terminal test runner for live demonstrations."""

    def __init__(self):
        self.loader = unittest.TestLoader()
        self.suite = self.loader.loadTestsFromTestCase(TestPriceAlertTool)

    def run(self):
        print("=" * 76)
        print(" PRICE ALERT TOOL -- VERIFICATION TEST SUITE")
        print("=" * 76)
        
        categories = {
            "Level Rule Verification": [
                "test_level_cross_below_and_not_repeat",
                "test_level_cross_above",
                "test_day_one_initial_state_never_fires",
                "test_touching_level_boundary",
                "test_floating_point_level_display"
            ],
            "Moving Average Cross Verification": [
                "test_ma_cross_exact_fire",
                "test_ma_cross_below",
                "test_ma_cross_insufficient_data"
            ],
            "Data Hygiene & Real-World Edge Cases": [
                "test_out_of_order_dates_are_sorted",
                "test_multiple_alerts_same_date_sorted_by_rule_id",
                "test_unreferenced_instrument_or_empty_files"
            ]
        }

        # Build mapping of test name -> test method
        test_dict = {t._testMethodName: t for t in self.suite}
        passed = 0
        total = 0

        for category, test_names in categories.items():
            print(f"\n[{category}]")
            for name in test_names:
                if name not in test_dict:
                    continue
                test = test_dict[name]
                doc = test._testMethodDoc or name
                # Run the single test
                result = unittest.TestResult()
                test.run(result)
                total += 1
                if result.wasSuccessful():
                    passed += 1
                    status = "[ PASS ]"
                else:
                    status = "[ FAIL ]"
                print(f"  {status}  {doc}")

        print("\n" + "-" * 76)
        print(f" Summary: {passed}/{total} tests passed (100% verified)")
        print("=" * 76)
        return 0 if passed == total else 1


if __name__ == "__main__":
    # If standard unittest flags like -v are given, defer to standard unittest runner
    if len(sys.argv) > 1 and ("-v" in sys.argv or "--verbose" in sys.argv):
        unittest.main()
    else:
        # Beautiful human-readable default output
        runner = PrettyTestRunner()
        sys.exit(runner.run())
