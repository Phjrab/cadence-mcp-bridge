"""Original bounded step analysis, compatible with the installed Python 2.6.

An endpoint-referenced 20--80% secant rate, not maximum adjacent slope.
Criteria are preselected study diagnostics, not user design specifications.
"""
from __future__ import with_statement

import math


def finite(x):
    return type(x) in (float, int) and not math.isnan(x) and not math.isinf(x)


def transition(times, values, edge, end, input_edge=1e-9):
    # Plateaus: fixed 0.5 us windows before the edge and at the interval end.
    pre = [v for t, v in zip(times, values) if edge - 1e-6 <= t <= edge - 0.5e-6]
    post = [v for t, v in zip(times, values) if end - 1e-6 <= t <= end - 0.5e-6]
    result = {"status": "INSUFFICIENT_DATA", "direction": None, "rate_v_per_s": None,
              "start_level_v": None, "end_level_v": None, "plateau_span_v": None,
              "window_v": None, "crossings_s": None, "brackets_s": None,
              "window_sample_count": 0, "overshoot_fraction": None,
              "subwindow_rate_ratio": None, "input_edge_overlap": None}
    if len(pre) < 8 or len(post) < 8:
        return result
    a, b = sum(pre) / len(pre), sum(post) / len(post)
    swing = abs(b - a)
    result.update(start_level_v=a, end_level_v=b,
                  plateau_span_v=max(max(pre)-min(pre), max(post)-min(post)))
    if swing < 0.1:
        result["status"] = "NO_LARGE_TRANSITION"
        return result
    sign = 1 if b > a else -1
    result["direction"] = "rise" if sign > 0 else "fall"
    normalized = [(t, sign * (v - a) / swing) for t, v in zip(times, values)
                  if edge - 0.5e-6 <= t <= end - 0.5e-6]
    result["overshoot_fraction"] = max(0, max(v for t, v in normalized)-1,
                                       -min(v for t, v in normalized))
    crossings = []
    brackets = []
    for level in (0.2, 0.4, 0.6, 0.8):
        hits = []
        for left, right in zip(normalized, normalized[1:]):
            t0, v0 = left
            t1, v1 = right
            if v0 < level <= v1:
                hits.append((t0+(t1-t0)*(level-v0)/(v1-v0), [t0, t1]))
        if len(hits) != 1:
            result["status"] = "MULTIPLE_CROSSINGS" if hits else "NO_CROSSING"
            return result
        crossings.append(hits[0][0])
        brackets.append(hits[0][1])
    result["crossings_s"] = [crossings[0], crossings[-1]]
    result["brackets_s"] = [brackets[0], brackets[-1]]
    result["window_v"] = [a+sign*0.2*swing, a+sign*0.8*swing]
    result["window_sample_count"] = sum(crossings[0] <= t <= crossings[-1] for t in times)
    result["input_edge_overlap"] = crossings[0] <= edge + input_edge
    rates = [0.2*swing/(r-l) for l, r in zip(crossings, crossings[1:])]
    result["subwindow_rate_ratio"] = max(rates)/min(rates)
    rate = sign*0.6*swing/(crossings[-1]-crossings[0])
    if result["plateau_span_v"] > 0.001*swing:
        result["status"] = "UNSETTLED"
    elif result["overshoot_fraction"] > 0.02:
        result["status"] = "RINGING_OR_OVERSHOOT"
    elif result["window_sample_count"] < 8:
        result["status"] = "INSUFFICIENT_WINDOW_SAMPLES"
    elif any(r-l > (crossings[-1]-crossings[0])/8 for l, r in result["brackets_s"]):
        result["status"] = "COARSE_CROSSING_BRACKET"
    else:
        result["status"] = "DEFINED_TRANSITION"
        result["rate_v_per_s"] = rate
    return result


def parse(frame, case):
    controls = {"coarse": (1e-8, 1e-9), "medium": (5e-9, 1e-9),
                "fine": (2.5e-9, 1e-9), "fast": (2.5e-9, 5e-10)}
    if case not in controls or len(frame) > 8*1024**2:
        raise ValueError("fixed bounded step frame")
    maxstep, edge = controls[case]
    lines = frame.decode("ascii").splitlines()
    if not lines or lines[0] != "BEGIN" or lines[-1] != "END":
        raise ValueError("step framing")
    cursor, axis, vectors = 1, None, {}
    for signal in ("Vop", "Vom", "Vp", "Vm", "VDD"):
        head = lines[cursor].split("|")
        cursor += 1
        if len(head) != 3 or head[:2] != ["VECTOR", signal]:
            raise ValueError("step signal identity")
        count = int(head[2])
        if not 1001 <= count <= 16000:
            raise ValueError("bounded native step points")
        times, values = [], []
        for index in range(count):
            row = lines[cursor].split("|")
            cursor += 1
            if len(row) != 4 or row[:2] != ["POINT", str(index)]:
                raise ValueError("step point identity")
            t, v = float(row[2]), float(row[3])
            if not finite(t) or not finite(v) or abs(v) > 2:
                raise ValueError("step finite voltage bound")
            times.append(t)
            values.append(v)
        if axis is None:
            axis = times
        elif axis != times:
            raise ValueError("step shared native axis")
        vectors[signal] = values
    if cursor != len(lines)-1 or axis[0] != 0 or abs(axis[-1]-1e-5) > 1e-15:
        raise ValueError("step interval")
    if any(not 0 < r-l <= maxstep*1.00001 for l, r in zip(axis, axis[1:])):
        raise ValueError("step time resolution")
    for i, t in enumerate(axis):
        fraction = (0 if t <= 2e-6 else min(1, (t-2e-6)/edge) if t < 6e-6
                    else max(0, 1-(t-6e-6)/edge))
        p = 0.45+0.1*fraction
        if (abs(vectors["Vp"][i]-p) > 1e-7 or
                abs(vectors["Vm"][i]-(1-p)) > 1e-7 or abs(vectors["VDD"][i]-1) > 1e-9):
            raise ValueError("effective step or supply mismatch")
    differential = [p-m for p, m in zip(vectors["Vop"], vectors["Vom"])]
    return {"case": case, "maxstep_s": maxstep, "input_edge_s": edge,
            "native_point_count": len(axis), "max_observed_step_s": max(r-l for l, r in zip(axis, axis[1:])),
            "output_differential_min_v": min(differential),
            "output_differential_max_v": max(differential),
            "transitions": [transition(axis, differential, 2e-6, 6e-6, edge),
                            transition(axis, differential, 6e-6, 1e-5, edge)]}
