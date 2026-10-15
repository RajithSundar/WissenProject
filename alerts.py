#!/usr/bin/env python3
"""
Price Alert Tool
================
A command-line tool that reads daily stock prices, applies configured alert rules,
and reports which alerts fired on which days in chronological order.

Usage:
    python alerts.py <prices.csv> <rules.json>
"""

import sys
import csv
import json
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple


@dataclass
class PricePoint:
    date: str
    instrument: str
    close: float


@dataclass
class AlertEvent:
    date: str
    rule_id: str
    formatted_output: str


def parse_prices(csv_path: str) -> Dict[str, List[PricePoint]]:
    """
    Parses prices CSV.
    Returns a dict mapping instrument name -> list of PricePoints sorted chronologically by date.
    
    Handles:
    - Out of order dates
    - Whitespace trimming
    - Invalid/corrupt lines
    - Duplicate dates (keeps latest entry or raises informative warning)
    """
    instruments_data: Dict[str, Dict[str, float]] = {}

    try:
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return {}
            
            # Normalize headers
            headers = [h.strip().lower() for h in reader.fieldnames if h]
            if not all(k in headers for k in ["date", "instrument", "close"]):
                raise ValueError("CSV header must contain 'date', 'instrument', and 'close'")

            for line_no, raw_row in enumerate(reader, start=2):
                # Clean keys and values
                row = {k.strip().lower(): v.strip() for k, v in raw_row.items() if k is not None and v is not None}
                
                date_str = row.get("date", "")
                inst = row.get("instrument", "")
                close_str = row.get("close", "")

                if not date_str or not inst or not close_str:
                    # Skip empty/corrupt row
                    continue

                try:
                    close_val = float(close_str)
                except ValueError:
                    # Corrupt numeric value
                    continue

                if inst not in instruments_data:
                    instruments_data[inst] = {}

                # Store by date (deduplicating if same date occurs multiple times for same instrument)
                instruments_data[inst][date_str] = close_val

    except FileNotFoundError:
        print(f"Error: Prices file not found: {csv_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading prices file: {e}", file=sys.stderr)
        sys.exit(1)

    # Convert to sorted list of PricePoints per instrument
    result: Dict[str, List[PricePoint]] = {}
    for inst, date_map in instruments_data.items():
        sorted_dates = sorted(date_map.keys())
        result[inst] = [PricePoint(date=d, instrument=inst, close=date_map[d]) for d in sorted_dates]

    return result


def parse_rules(json_path: str) -> List[dict]:
    """
    Parses and validates rules JSON.
    """
    try:
        with open(json_path, mode="r", encoding="utf-8") as f:
            rules = json.load(f)
            if not isinstance(rules, list):
                raise ValueError("Rules file must contain a JSON list of rule objects.")
            return rules
    except FileNotFoundError:
        print(f"Error: Rules file not found: {json_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading rules file: {e}", file=sys.stderr)
        sys.exit(1)


def evaluate_level_rule(rule: dict, prices: List[PricePoint]) -> List[AlertEvent]:
    """
    Evaluates a 'level' rule:
    Fires on the first day the close crosses the level in the given direction
    (it was on the other side the previous day).
    """
    alerts: List[AlertEvent] = []
    rule_id = rule.get("id", "")
    instrument = rule.get("instrument", "")
    direction = rule.get("direction", "").lower()
    level = float(rule.get("level", 0.0))

    if len(prices) < 2:
        return alerts

    # Format level display: if integer-like (e.g. 1500.0) display as 1500
    level_display = int(level) if level.is_integer() else level

    for i in range(1, len(prices)):
        prev_close = prices[i - 1].close
        curr_close = prices[i].close
        curr_date = prices[i].date

        crossed = False
        if direction == "below":
            # Was above yesterday, crossed to at or below today
            if prev_close > level and curr_close <= level:
                crossed = True
        elif direction == "above":
            # Was below yesterday, crossed to at or above today
            if prev_close < level and curr_close >= level:
                crossed = True

        if crossed:
            msg = f"{curr_date} {rule_id} {instrument} level {direction} {level_display}"
            alerts.append(AlertEvent(date=curr_date, rule_id=rule_id, formatted_output=msg))

    return alerts


def evaluate_ma_cross_rule(rule: dict, prices: List[PricePoint]) -> List[AlertEvent]:
    """
    Evaluates an 'ma_cross' rule:
    Fires on the day the short moving average crosses the long one in the given direction.
    Moving averages need a full window of days before they are defined.
    """
    alerts: List[AlertEvent] = []
    rule_id = rule.get("id", "")
    instrument = rule.get("instrument", "")
    short_w = int(rule.get("short", 0))
    long_w = int(rule.get("long", 0))
    direction = rule.get("direction", "").lower()

    if short_w <= 0 or long_w <= 0 or short_w >= long_w:
        # Invalid window configuration
        return alerts

    n = len(prices)
    # We need at least long_w days for the first long MA to be defined,
    # and at least long_w + 1 days to determine a *crossing* from the previous day.
    if n < long_w + 1:
        return alerts

    # Precalculate closes for faster slicing
    closes = [p.close for p in prices]

    # Calculate moving averages: index i corresponds to prices[i]
    # MA is defined if i >= window - 1
    def get_ma(idx: int, window: int) -> float:
        window_closes = closes[idx - window + 1 : idx + 1]
        return sum(window_closes) / window

    # We evaluate crossing starting from day index = long_w (which is the (long_w + 1)-th day)
    # At day index long_w - 1, the first long MA is defined.
    # At day index long_w, the second long MA is defined, allowing us to check if crossing occurred.
    for i in range(long_w, n):
        curr_date = prices[i].date

        prev_short_ma = get_ma(i - 1, short_w)
        prev_long_ma = get_ma(i - 1, long_w)

        curr_short_ma = get_ma(i, short_w)
        curr_long_ma = get_ma(i, long_w)

        crossed = False
        if direction == "above":
            # Was at or below yesterday, crossed to strictly above today
            if prev_short_ma <= prev_long_ma and curr_short_ma > curr_long_ma:
                crossed = True
        elif direction == "below":
            # Was at or above yesterday, crossed to strictly below today
            if prev_short_ma >= prev_long_ma and curr_short_ma < curr_long_ma:
                crossed = True

        if crossed:
            msg = f"{curr_date} {rule_id} {instrument} ma_cross {short_w}/{long_w} {direction}"
            alerts.append(AlertEvent(date=curr_date, rule_id=rule_id, formatted_output=msg))

    return alerts


def process_alerts(prices_file: str, rules_file: str) -> List[str]:
    """
    Main processing function:
    Loads prices, applies rules, and returns list of alert output strings.
    """
    instruments_data = parse_prices(prices_file)
    rules = parse_rules(rules_file)

    all_alerts: List[AlertEvent] = []

    for rule in rules:
        instrument = rule.get("instrument")
        rule_type = rule.get("type")

        # If instrument not present in data, this rule produces no alerts
        if instrument not in instruments_data:
            continue

        prices = instruments_data[instrument]

        if rule_type == "level":
            alerts = evaluate_level_rule(rule, prices)
            all_alerts.extend(alerts)
        elif rule_type == "ma_cross":
            alerts = evaluate_ma_cross_rule(rule, prices)
            all_alerts.extend(alerts)

    # Sort alerts: ordered by date, then rule id
    all_alerts.sort(key=lambda a: (a.date, a.rule_id))

    return [a.formatted_output for a in all_alerts]


def main():
    if len(sys.argv) != 3:
        print("Usage: python alerts.py <prices.csv> <rules.json>", file=sys.stderr)
        sys.exit(1)

    prices_path = sys.argv[1]
    rules_path = sys.argv[2]

    results = process_alerts(prices_path, rules_path)
    for line in results:
        print(line)


if __name__ == "__main__":
    main()
