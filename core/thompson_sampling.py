import random


def sample_beta(successes: float, failures: float) -> float:
    # Beta distribution with uniform prior (1,1)
    # Avoid zero values by adding smoothing.
    alpha = max(1.0, successes + 1.0)
    beta = max(1.0, failures + 1.0)
    return random.betavariate(alpha, beta)


def pick_variant_thompson(variants: list):
    best = None
    best_score = -1.0

    for v in variants or []:
        sample_size = v.get("sample_size", 0)
        successes = v.get("success_count", None)
        failures = v.get("failures", None)

        if successes is None:
            successes = v.get("successes", 0)
            if successes is None:
                successes = max(0, int(v.get("success_rate", 0.0) * sample_size))

        if failures is None:
            failures = v.get("failures", 0)
            if failures is None:
                failures = max(0, sample_size - int(successes))

        s = sample_beta(successes, failures)

        if s > best_score:
            best_score = s
            best = v

    return best
