"""
Comprehensive content quality scorer — thin wrapper around content_rules.py.
Maintains backward-compatible interface (rule_based_score).

The actual 73-rule per-rule engine lives in quality/content_rules.py.
This module delegates to it and returns the backward-compat format.
"""
from quality.content_rules import check_all_rules


def rule_based_score(
    body_html: str,
    keyword: str,
    title: str,
    meta_title: str = "",
    meta_desc: str = "",
    page_type: str = "article",
    *,
    brand_name: str = "",
    business_type: str = "",
    target_locations: str = "",
    target_audience: str = "",
    customer_url: str = "",
):
    """
    Backward-compatible wrapper.
    Returns: {score/100, categories, issues, word_count, kw_density,
              + new per-rule fields: percentage, rules, pillars, summary}
    """
    return check_all_rules(
        body_html, keyword, title, meta_title, meta_desc, page_type=page_type,
        brand_name=brand_name, business_type=business_type,
        target_locations=target_locations, target_audience=target_audience,
        customer_url=customer_url,
    )
