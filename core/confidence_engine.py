import math


def compute_confidence(mean: float, variance: float, n: int) -> float:
    """Compute a normalized confidence score for a variant.

    Uses a statistical approximation based on mean/variance and sample size.
    """
    if n < 5:
        return 0.0

    std_error = math.sqrt(variance / n) if n > 0 else 1.0
    score = mean / (std_error + 1e-9)

    # Normalize using sigmoid to keep within 0..1 range
    return 1 / (1 + math.exp(-score))
