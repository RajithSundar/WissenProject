# Price Alert Tool

A deterministic command-line batch processing tool that reads daily stock prices, evaluates alert rules, and outputs fired alerts in chronological order.

---

## 1. How to Run

### Requirements
- **Python 3.8+** (Uses only Python Standard Library: `sys`, `csv`, `json`, `dataclasses`, `typing`).
- **Zero external packages required** (no `pip install`, no `pandas`, no virtualenv needed).

### Single Run Command
```bash
python alerts.py prices.csv rules.json
```

### Running Tests
```bash
python -m unittest -v test_alerts.py
```

---

## 2. How the AI Assistant Was Used

I used an AI assistant as a collaborative pair-programmer following this workflow:
1. **Architecture & Scope Briefing**: Clarified that this is a batch historical simulation (not a real-time streaming engine) and identified edge cases before writing code.
2. **Implementation Prompt**: Guided the AI to write a modular Python script with standard libraries (`csv`, `json`, `dataclasses`), handling out-of-order dates and multi-instrument data structures.
3. **Edge Case & Test Generation**: Prompted the AI to write a strict unit test suite (`test_alerts.py`) targeting boundary conditions, missing data, and chronological tie-breaking.

---

## 3. What the Assistant Got Wrong & What Was Changed

| Issue / Naive AI Behavior | Why It Was Wrong | What I Changed & Why |
| :--- | :--- | :--- |
| **First-day Long MA False Cross** | The AI originally started checking `ma_cross` on day index `long_w - 1` (the first day a 20-day MA exists). If `short_ma > long_ma`, it fired immediately. | On the very first day a 20-day MA is defined, **there is no previous 20-day MA on day $t-1$** to prove that short MA was on the other side. Changed the loop to start at index `long_w` requiring both day $t-1$ and day $t$ to have defined MAs. |
| **Boundary Value Handling** | The AI's initial condition used strict inequalities: `prev > level and curr < level`. | If price drops from 1520 to **exactly 1500**, it should count as crossing "below" 1500. Updated logic to `prev > level and curr <= level` (and `prev < level and curr >= level` for "above"). |
| **Day 1 Level Evaluation** | Initial logic evaluated Day 1 against the level as if it were a state check rather than a crossing. | The brief states: *"it was on the other side the previous day"*. Because Day 1 has no previous day, crossing is impossible. Enforced loop range starting strictly from `index = 1`. |
| **Same-Date Sorting Tie-Breaker** | The AI initially sorted alerts only by `date`. | If rule `r2` and rule `r1` fired on the same date, output order was nondeterministic. Enforced secondary sort key: `(alert.date, alert.rule_id)`. |

---

## 4. Key Verification & Edge Cases Covered

Our `test_alerts.py` suite validates:
1. **Unordered Dates**: Scrambled dates in CSV are sorted chronologically per instrument before processing.
2. **Level Crossing**: Fires only on the day of crossing, not on subsequent days if price remains beyond the level.
3. **MA Window Requirements**: Returns zero alerts if total price rows $\le$ long window.
4. **Resilience to Dirty Data**: Missing CSV values, non-existent instruments in rules, and mixed multi-stock files operate cleanly without crashing.
