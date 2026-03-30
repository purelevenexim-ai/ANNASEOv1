"""
Strategy Processor — Process Step 1 keywords through business/competitor context.

Purpose: Take user's input keywords (pillars + supporting) and apply business logic:
1. Validate against project business type
2. Score based on business intent (ecommerce/blog/supplier)
3. Enrich with customer/competitor context
4. Create strategy_context object for downstream use
"""

import logging
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

log = logging.getLogger("annaseo.strategy_processor")


@dataclass
class StrategyContext:
    """Unified strategy context passed through workflow."""
    project_id: str
    session_id: str
    business_intent: str
    customer_url: Optional[str] = None
    competitor_urls: Optional[List[str]] = None
    user_keywords: Optional[List[Dict[str, Any]]] = None
    business_signals: Optional[Dict] = None
    competitor_signals: Optional[Dict] = None
    strategy_meta: Optional[Dict] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "project_id": self.project_id,
            "session_id": self.session_id,
            "business_intent": self.business_intent,
            "customer_url": self.customer_url,
            "competitor_urls": self.competitor_urls,
            "user_keywords": self.user_keywords,
            "business_signals": self.business_signals,
            "competitor_signals": self.competitor_signals,
            "strategy_meta": self.strategy_meta,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "StrategyContext":
        """Create from dict."""
        return StrategyContext(**data)


class StrategyProcessor:
    """Process Step 1 input keywords through business context."""

    def __init__(self):
        self.log = logging.getLogger("annaseo.strategy_processor")

    def process(
        self,
        project_id: str,
        session_id: str,
        business_intent: str,
        customer_url: Optional[str] = None,
        competitor_urls: Optional[List[str]] = None,
        user_keywords: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        Process Step 1 keywords through business strategy.

        Returns:
            {
                "success": bool,
                "strategy_context": StrategyContext,
                "error": str (if not success),
                "scores": list of keywords with scores
            }
        """
        try:
            self.log.info(
                f"[Strategy] Processing {len(user_keywords or [])} keywords "
                f"for project={project_id}, intent={business_intent}"
            )

            # Extract business signals from customer URL (placeholder - can be enhanced)
            business_signals = self._extract_business_signals(
                customer_url, business_intent
            )

            # Extract competitor signals from competitor URLs (placeholder)
            competitor_signals = self._extract_competitor_signals(
                competitor_urls or []
            )

            # Score user keywords based on business context
            scored_keywords = self._score_keywords(
                user_keywords or [],
                business_intent,
                business_signals,
                competitor_signals,
            )

            # Create strategy context
            ctx = StrategyContext(
                project_id=project_id,
                session_id=session_id,
                business_intent=business_intent,
                customer_url=customer_url,
                competitor_urls=competitor_urls,
                user_keywords=user_keywords,
                business_signals=business_signals,
                competitor_signals=competitor_signals,
                strategy_meta={
                    "processed_at": str(__import__("datetime").datetime.utcnow()),
                    "keyword_count": len(user_keywords or []),
                    "scored_count": len(scored_keywords),
                },
            )

            self.log.info(
                f"[Strategy] Processed {len(scored_keywords)} keywords "
                f"with business intent={business_intent}"
            )

            return {
                "success": True,
                "strategy_context": ctx,
                "scored_keywords": scored_keywords,
                "message": f"Processed {len(scored_keywords)} keywords with {business_intent} intent",
            }

        except Exception as e:
            self.log.error(f"[Strategy] Processing failed: {e}", exc_info=True)
            return {
                "success": False,
                "strategy_context": None,
                "error": str(e),
                "scored_keywords": [],
            }

    def _extract_business_signals(
        self, customer_url: Optional[str], business_intent: str
    ) -> Dict:
        """
        Extract business signals from customer URL.

        Signals extracted:
        - Intent profile (ecommerce/blog/supplier)
        - Priority keywords for this business type
        - Expected page types
        - Content focus areas
        - Allowed vs blocked topics
        """
        intent_signals = {
            "ecommerce": {
                "page_types": ["product", "category", "comparison"],
                "focus_intent": ["transactional", "commercial"],
                "priority_signals": ["price", "buy", "review", "best", "cheap", "sale"],
                "allowed_topics": ["products", "pricing", "reviews", "comparisons"],
                "blocked_topics": ["unrelated news", "politics", "gossip"],
                "content_depth": "medium",
                "freshness_importance": "high",
            },
            "blog": {
                "page_types": ["article", "guide", "resource", "tutorial"],
                "focus_intent": ["informational"],
                "priority_signals": ["how", "what", "guide", "tutorial", "tips", "learn"],
                "allowed_topics": ["education", "tips", "guides", "tutorials"],
                "blocked_topics": ["product sales pitches"],
                "content_depth": "high",
                "freshness_importance": "medium",
            },
            "supplier": {
                "page_types": ["product", "spec", "bulk", "wholesale"],
                "focus_intent": ["transactional", "commercial"],
                "priority_signals": ["bulk", "wholesale", "manufacturer", "supplier", "industrial"],
                "allowed_topics": ["products", "bulk sales", "specifications"],
                "blocked_topics": ["consumer reviews", "retail"],
                "content_depth": "medium",
                "freshness_importance": "low",
            },
        }

        signals = intent_signals.get(business_intent, intent_signals["blog"])
        signals["url_analyzed"] = bool(customer_url)
        signals["business_intent"] = business_intent

        return signals

    def _extract_competitor_signals(
        self, competitor_urls: List[str]
    ) -> Dict:
        """
        Extract competitor signals from competitor URLs.

        Analyzes:
        - Number of competitors analyzed
        - Top ranking keywords by competitors
        - Content gaps vs competitors
        - Competitor content strategies
        - Opportunity keywords
        """
        competitor_analysis = {
            "total_competitors": len(competitor_urls),
            "analyzed": len(competitor_urls) > 0,
            "analysis_stage": "discovered",
            "urls_provided": competitor_urls,
        }

        # Placeholder for competitor data - would be populated by actual crawl
        competitor_analysis.update({
            "gap_keywords": [],  # Keywords competitors rank for but you don't
            "top_keywords": [],  # Most common keywords across competitors
            "content_gaps": [],  # Topics competitors cover but you don't
            "easy_wins": [],  # Keywords with low competition
            "strength_areas": [],  # Where you're stronger than competitors
        })

        return competitor_analysis

    def _score_keywords(
        self,
        keywords: List[Dict],
        business_intent: str,
        business_signals: Dict,
        competitor_signals: Dict,
    ) -> List[Dict]:
        """
        Score user keywords based on business context.

        Simple scoring:
        - Base score: 50
        - +20 if matches business intent signals
        - +15 if appears in competitors
        - +10 if shows transactional intent
        """
        scored = []

        for kw in keywords:
            kw_text = (
                kw.get("keyword", "").lower()
                if isinstance(kw, dict)
                else str(kw).lower()
            )
            score = 50

            # Score based on business intent match
            priority_signals = business_signals.get("priority_signals", [])
            if any(sig.lower() in kw_text for sig in priority_signals):
                score += 20

            # Score based on intent
            if business_intent == "ecommerce" and any(
                word in kw_text for word in ["buy", "price", "cheap", "sale"]
            ):
                score += 10
            elif business_intent == "blog" and any(
                word in kw_text for word in ["how", "why", "what", "guide"]
            ):
                score += 10

            scored_kw = dict(kw) if isinstance(kw, dict) else {"keyword": str(kw)}
            scored_kw["strategy_score"] = score
            scored_kw["source"] = "user_input"
            scored.append(scored_kw)

        # Sort by score descending
        scored.sort(key=lambda x: x.get("strategy_score", 0), reverse=True)
        return scored


def process_strategy(
    project_id: str,
    session_id: str,
    business_intent: str,
    customer_url: Optional[str] = None,
    competitor_urls: Optional[List[str]] = None,
    user_keywords: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """Convenience function to process strategy."""
    processor = StrategyProcessor()
    return processor.process(
        project_id=project_id,
        session_id=session_id,
        business_intent=business_intent,
        customer_url=customer_url,
        competitor_urls=competitor_urls,
        user_keywords=user_keywords,
    )
