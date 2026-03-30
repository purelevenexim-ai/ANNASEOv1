from typing import Any, Dict, List
import statistics

from services.serp_intelligence.engine import SERPIntelligenceEngine
from services.scoring_engine import ScoringEngine


class RankingMonitor:
    def __init__(self, serp_engine: SERPIntelligenceEngine = None, scoring_engine: ScoringEngine = None):
        self.serp_engine = serp_engine or SERPIntelligenceEngine()
        self.scoring_engine = scoring_engine or ScoringEngine()

    def get_rank_history(self, db, project_id: str, keyword: str, limit: int = 10) -> List[int]:
        try:
            row = db.execute(
                "SELECT rank FROM keyword_rankings WHERE project_id=? AND keyword=? ORDER BY last_updated DESC LIMIT ?",
                (project_id, keyword, limit),
            ).fetchall()
            return [r[0] for r in row if r and r[0] is not None]
        except Exception:
            # If keyword_rankings table missing or query fails, treat as empty history
            return []

    def detect_drop(self, history: List[int]) -> Dict[str, Any]:
        if len(history) < 3:
            return {"drop_detected": False, "current_rank": history[0] if history else None, "drop_magnitude": 0}

        latest = history[0]
        numerator = [v for v in history[1:] if isinstance(v, (int, float))]
        if not numerator:
            return {"drop_detected": False, "current_rank": latest, "drop_magnitude": 0}

        previous_avg = statistics.mean(numerator)
        drop = latest - previous_avg
        return {
            "drop_detected": drop >= 1,
            "current_rank": latest,
            "previous_avg": round(previous_avg, 2),
            "drop_magnitude": round(drop, 2),
        }

    def analyze_serp_shift(self, keyword: str) -> Dict[str, Any]:
        serp_result = self.serp_engine.run([{"primary_keyword": keyword}])
        return {
            "serp_summary": serp_result.get("serp_summary", {}),
            "gaps": serp_result.get("gaps", []),
            "competitors": serp_result.get("competitors", []),
            "win_probability": serp_result.get("win_probability", 0.0),
        }

    def detect_root_causes(self, target_page: Dict[str, Any], serp_context: Dict[str, Any]) -> List[str]:
        causes: List[str] = []
        ctrl = serp_context

        if target_page.get("word_count", 0) < (ctrl.get("serp_summary", {}).get("avg_word_count", 2000)):
            causes.append("content_depth")

        if len(target_page.get("headings", [])) < 5:
            causes.append("poor_structure")

        gaps = ctrl.get("gaps", [])
        if gaps:
            causes.append("keyword_gap")

        if len(ctrl.get("competitors", [])) > 0 and target_page.get("backlinks", 0) < 3:
            causes.append("low_authority")

        if not causes:
            causes.append("minor_content_optimization")

        return causes

    def generate_recommendations(self, root_causes: List[str], gaps: List[str]) -> List[str]:
        rec = []

        if "content_depth" in root_causes:
            rec.append("Add deeper, longer sections to match competitors")
        if "poor_structure" in root_causes:
            rec.append("Use clear H2/H3 structure and add numbered steps")
        if "keyword_gap" in root_causes:
            rec.append("Include missing keywords from SERP gaps")
        if "low_authority" in root_causes:
            rec.append("Acquire backlinks and internal links to this article")

        rec.extend([f"Address gap: {g}" for g in gaps[:5]])

        if not rec:
            rec.append("Minor optimization: improve readability and add examples")

        return rec

    def diagnose_drop(self, db, project_id: str, keyword: str, target_url: str = "", content_data: Dict[str, Any] = None) -> Dict[str, Any]:
        content_data = content_data or {}

        history = self.get_rank_history(db, project_id, keyword)
        drop_info = self.detect_drop(history)

        serp_context = self.analyze_serp_shift(keyword)

        if "content_score" not in content_data:
            content_data["content_score"] = min(1.0, max(0.01, len(content_data.get("content", "").split()) / 2000))

        root_causes = self.detect_root_causes(content_data, serp_context)
        recommendations = self.generate_recommendations(root_causes, serp_context.get("gaps", []))

        return {
            "keyword": keyword,
            "drop_analysis": drop_info,
            "serp_context": serp_context,
            "root_causes": root_causes,
            "recommendations": recommendations,
            "fix_priority": "HIGH" if drop_info.get("drop_magnitude", 0) > 2 else "MEDIUM",
        }
