from core.confidence_engine import compute_confidence
from core.thompson_sampling import pick_variant_thompson
from core.global_memory_engine import compute_global_score, compute_context_score
from core.meta_learning import compute_meta_score

MIN_SAMPLE = 10


def score_variant(variant: dict) -> float:
    # The variant structure is expected to include:
    # - mean_roi
    # - variance
    # - sample_size
    # - weight
    if variant.get("sample_size", 0) < MIN_SAMPLE:
        return 0.0

    confidence = compute_confidence(
        variant.get("mean_roi", 0.0),
        variant.get("variance", 0.0),
        variant.get("sample_size", 0),
    )

    return confidence * variant.get("weight", 0.0)


def pick_best_variant(variants: list, db=None, context=None, meta_features=None):
    if not variants:
        return None, 0.0

    candidate = pick_variant_thompson(variants)
    scored = []

    for v in variants:
        local_score = score_variant(v)
        if db is not None:
            global_score = compute_global_score(db, v, context)
            context_score = compute_context_score(db, context) if context else 0.5
            meta_score = compute_meta_score(db, meta_features or {})
            final_score = 0.4 * local_score + 0.35 * global_score + 0.25 * (0.5 + meta_score / 2)
        else:
            final_score = local_score

        scored.append((v, final_score))

    scored.sort(key=lambda item: item[1], reverse=True)
    best_confidence_variant, best_confidence_score = scored[0]

    if candidate and db is not None:
        candidate_score = next((s for v, s in scored if v is candidate), None)
        candidate_score = candidate_score if candidate_score is not None else score_variant(candidate)
        if candidate_score >= best_confidence_score * 0.9:
            return candidate, candidate_score

    return (best_confidence_variant, best_confidence_score) if best_confidence_score > 0 else (None, 0.0)

