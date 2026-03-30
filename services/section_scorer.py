from typing import Dict, List


class SectionScorer:
    def score_section(self, section: Dict, target_score: Dict, competitor_scores: List[Dict]) -> float:
        score = 0.0

        if len(section.get("keywords", [])) >= 3:
            score += 20

        word_count = len(section.get("content", "").split())
        if word_count > 150:
            score += 20

        if section.get("heading"):
            score += 10

        if section.get("reason"):
            score += 20

        avg_comp_content_score = 0.0
        if competitor_scores:
            cnt = sum([c.get("content_score", 0) for c in competitor_scores])
            avg_comp_content_score = cnt / len(competitor_scores)

        target_content_score = target_score.get("content_score", 0.0)
        score += min(30, max(0, 30 * ((target_content_score / (avg_comp_content_score + 0.01)))))

        return min(score, 100.0)

    def rank_sections(self, sections: List[Dict], target_score: Dict, competitor_scores: List[Dict]) -> List[Dict]:
        out = []
        for s in sections:
            s_ = dict(s)
            s_["boost_score"] = self.score_section(s_, target_score, competitor_scores)
            out.append(s_)
        return sorted(out, key=lambda x: x.get("boost_score", 0), reverse=True)
