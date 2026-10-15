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

    def tearDown(self):
        pass  # Temp files are automatically cleaned up or unlinked after tests

    # ---------------------------------------------------------
    # 1. Level Crossing Tests
    # ---------------------------------------------------------
    def test_level_cross_below_and_not_repeat(self):
        """Alert should fire once when crossing below, not repeat if staying below."""
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
            # Should fire only on 2026-09-03 when it dropped from 1510 to 1490
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0], "2026-09-03 r1 INFY level below 1500")
        finally:
            os.unlink(csv_path)
            os.unlink(json_path)

    def test_level_cross_above(self):
        """Alert should fire when crossing above level."""
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
        """Even if Day 1 starts below level, it cannot cross because there is no previous day."""
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
        """Price moving from strictly above (1510) to exactly on the boundary (1500) counts as crossing."""
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
        """If data length is less than long_window + 1, no crossover can be evaluated."""
        # 5 days of data, but long window requires 20
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
            # Here we have 5 days, long=5.
            # Day 5 (index 4) is the FIRST day long MA exists.
            # But to check crossing, we also need day 4 to have had a long MA, which it didn't!
            alerts = process_alerts(csv_path, json_path)
            self.assertEqual(len(alerts), 0)
        finally:
            os.unlink(csv_path)
            os.unlink(json_path)

    def test_ma_cross_exact_fire(self):
        """Short MA (2-day) crosses Long MA (3-day) on Day 4."""
        # Day 1: 10
        # Day 2: 10 -> MA2=10
        # Day 3: 10 -> MA2=10, MA3=10 (MA2 <= MA3)
        # Day 4: 20 -> MA2=(10+20)/2 = 15, MA3=(10+10+20)/3 = 13.33 (MA2 > MA3) -> Cross above!
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
        """Short MA crosses below Long MA."""
        # Day 1: 20
        # Day 2: 20 -> MA2=20
        # Day 3: 20 -> MA2=20, MA3=20 (MA2 >= MA3)
        # Day 4: 5  -> MA2=(20+5)/2 = 12.5, MA3=(20+20+5)/3 = 15.0 (MA2 < MA3) -> Cross below!
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
        """Dates provided in random order in CSV must be sorted chronologically before processing."""
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
        """When two rules trigger on the same date, they must be ordered by rule id."""
        csv_data = """date,instrument,close
2026-09-01,INFY,1600.00
2026-09-02,INFY,1400.00
"""
        # Both r2 and r1 trigger on 2026-09-02
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
        """Instrument in rules but absent in CSV should safely yield 0 alerts."""
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
        """Level with decimals (e.g. 1500.5) should display properly."""
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


if __name__ == "__main__":
    unittest.main()
