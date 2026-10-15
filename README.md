# Price Alert Tool

A deterministic command-line batch processing tool that reads daily stock prices, evaluates alert rules, and outputs fired alerts in chronological order.

---

## 1. How to Run

### Requirements
- **Python 3.8+** (Uses only Python Standard Library: `sys`, `csv`, `json`, `dataclasses`, `typing`).
- **Zero external dependencies** (no `pip install`, no `pandas`, no virtual environment needed).

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

I used an AI assistant as a pair-programmer following an iterative, test-driven process. The interaction followed four distinct prompt phases:

1. **Prompt 1 (Problem Understanding & Disambiguation)**:  
   * *"Explain this build brief to me from scratch. Is this a live websocket ticker or a batch historical replay tool? What are the inputs, outputs, and edge cases?"*  
   * *Outcome*: Confirmed batch execution model, non-repeating alert behavior, and zero-dependency constraint.
2. **Prompt 2 (Architecture & Ingestion)**:  
   * *"Draft a standard library Python tool that parses `prices.csv` and `rules.json`. Handle out-of-order dates, whitespace trimming, and duplicate dates per stock without Pandas."*  
   * *Outcome*: Established dataclasses (`PricePoint`, `AlertEvent`) and nested dictionary grouping by instrument.
3. **Prompt 3 (Rule Simulation Engine)**:  
   * *"Implement `evaluate_level_rule` and `evaluate_ma_cross_rule`. Ensure moving averages are only calculated when a full window is available."*  
   * *Outcome*: Initial logic was drafted, but revealed mathematical edge-case bugs (detailed below).
4. **Prompt 4 (Adversarial Testing & Boundary Verification)**:  
   * *"Generate a unit test suite (`test_alerts.py`) targeting corrupt rows, insufficient data for 20-day MAs, Day 1 boundary conditions, and same-day multi-rule sorting."*  
   * *Outcome*: Validated all edge cases with 11 automated unit tests.

---

## 3. What the Assistant Got Wrong & What Was Changed

| Issue / Naive AI Behavior | Why It Was Wrong | What I Changed & Why |
| :--- | :--- | :--- |
| **First-day Long MA False Cross** | The AI originally started checking `ma_cross` on day index `long_w - 1` (the first day a 20-day MA exists). If `short_ma > long_ma`, it fired immediately. | On the very first day a 20-day MA is defined, **there is no previous 20-day MA on day $t-1$** to prove that the short MA was on the other side yesterday. Changed the loop to start at index `long_w`, requiring both day $t-1$ and day $t$ to have defined MAs. |
| **Boundary Value Handling** | The AI's initial condition used strict inequalities: `prev > level and curr < level`. | If price drops from 1520 to **exactly 1500**, it should count as crossing "below" 1500. Updated logic to `prev > level and curr <= level` (and `prev < level and curr >= level` for "above"). |
| **Day 1 Level Evaluation** | Initial logic evaluated Day 1 against the level as if it were a state check rather than a crossing. | The brief states: *"it was on the other side the previous day"*. Because Day 1 has no previous trading day, crossing is impossible. Enforced loop range starting strictly from `index = 1`. |
| **Same-Date Sorting Tie-Breaker** | The AI initially sorted alerts only by `date`. | If rule `r2` and rule `r1` fired on the same date, output order was nondeterministic. Enforced secondary sort key: `(alert.date, alert.rule_id)`. |

---

## 4. Key Verification & Edge Cases Covered

The `test_alerts.py` suite validates:
1. **Unordered Dates**: Scrambled dates in CSV are sorted chronologically per instrument before processing.
2. **Level Crossing**: Fires only on the day of crossing, not on subsequent days if price remains beyond the level.
3. **MA Window Requirements**: Returns zero alerts if total price rows $\le$ long window.
4. **Resilience to Dirty Data**: Missing CSV values, non-existent instruments in rules, and mixed multi-stock files operate cleanly without crashing.
