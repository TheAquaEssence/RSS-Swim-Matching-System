"""What-If Engine for instant swap/relax/tune queries using CompatibilityScorer."""

import os
from typing import Dict, List, Optional

import pandas as pd

from core.scoring.compatibility_scorer import CompatibilityScorer
from core.scoring.ranking_loader import RankingLoader
from core.scoring.config import SCORING_WEIGHTS


class WhatIfEngine:
    """Provides instant what-if queries using the CompatibilityScorer."""

    def __init__(self, data_manager, source_dir: str = "data/source"):
        self.dm = data_manager
        loader = RankingLoader(source_dir)
        color_rankings, style_rankings = loader.load_all()
        self._default_scorer = CompatibilityScorer(color_rankings, style_rankings)
        self._color_rankings = color_rankings
        self._style_rankings = style_rankings

        # Load label lookups from source CSVs
        self._color_labels = {}
        self._style_labels = {}
        colors_path = os.path.join(source_dir, "personality_colors.csv")
        styles_path = os.path.join(source_dir, "instructor_styles.csv")
        if os.path.exists(colors_path):
            df = pd.read_csv(colors_path)
            self._color_labels = dict(zip(df["color_id"].astype(int), df["color_name"]))
        if os.path.exists(styles_path):
            df = pd.read_csv(styles_path)
            self._style_labels = dict(zip(df["style_id"].astype(int), df["style_name"]))

    def get_style_code(self, style_name: str) -> str:
        """Derive style code from style name for DIA detection."""
        if style_name and "Do-It-All" in style_name:
            return "DIA"
        return ""

    def score_swimmer_instructor(self, swimmer_profile: Dict, instructor_profile: Dict,
                                   scorer: Optional[CompatibilityScorer] = None) -> Dict:
        """Score a swimmer-instructor pair and return breakdown."""
        s = scorer or self._default_scorer
        style_code = self.get_style_code(instructor_profile.get("primary_style_name", ""))
        result = s.score(
            swimmer_type_id=swimmer_profile["swimmer_type_id"],
            primary_color_id=instructor_profile["primary_color_id"],
            secondary_color_id=instructor_profile["secondary_color_id"],
            primary_style_id=instructor_profile["primary_style_id"],
            secondary_style_id=instructor_profile["secondary_style_id"],
            primary_style_code=style_code,
        )

        cs = result.color_score
        ss = result.style_score

        return {
            "score": round(result.combined_score, 2),
            "color_score": round(cs.normalized, 4),
            "style_score": round(ss.normalized, 4),
            "is_dia": ss.is_dia,
            "detail": {
                "primary_color": {
                    "rank": cs.primary_rank,
                    "of": 4,
                    "points": cs.primary_points,
                    "weight": 2.0,
                    "weighted": cs.primary_weighted,
                    "label": self._color_labels.get(instructor_profile["primary_color_id"], "?"),
                },
                "secondary_color": {
                    "rank": cs.secondary_rank,
                    "of": 4,
                    "points": cs.secondary_points,
                    "weight": 1.0,
                    "weighted": cs.secondary_weighted,
                    "label": self._color_labels.get(instructor_profile["secondary_color_id"], "?"),
                },
                "color_raw_total": cs.raw_total,
                "color_min": 4.0,
                "color_max": 11.0,
                "primary_style": {
                    "rank": ss.primary_rank,
                    "of": 6,
                    "points": ss.primary_points,
                    "weight": 2.0 if not ss.is_dia else 0,
                    "weighted": ss.primary_weighted,
                    "label": self._style_labels.get(instructor_profile["primary_style_id"], "?"),
                },
                "secondary_style": {
                    "rank": ss.secondary_rank,
                    "of": 6,
                    "points": ss.secondary_points,
                    "weight": 1.0 if not ss.is_dia else 2.0,
                    "weighted": ss.secondary_weighted,
                    "label": self._style_labels.get(instructor_profile["secondary_style_id"], "?"),
                },
                "style_raw_total": ss.raw_total,
                "style_min": 4.0 if not ss.is_dia else 5.0,
                "style_max": 17.0 if not ss.is_dia else 15.0,
            },
        }

    def swap_explore(self, swimmer_id: int, current_instructor_id: int) -> Dict:
        """Compare current instructor with all alternatives for a swimmer."""
        swimmer = self.dm.get_swimmer(swimmer_id)
        if not swimmer:
            return {"error": "Swimmer not found"}

        current_instr = self.dm.get_instructor(current_instructor_id)
        current_scores = self.score_swimmer_instructor(swimmer, current_instr) if current_instr else {}
        current_scores["instructor_id"] = current_instructor_id
        current_scores["instructor_name"] = current_instr.get("name", "") if current_instr else ""

        alternatives = []
        for instr in self.dm.all_instructors():
            if instr["instructor_id"] == current_instructor_id:
                continue
            scores = self.score_swimmer_instructor(swimmer, instr)
            scores["instructor_id"] = instr["instructor_id"]
            scores["instructor_name"] = instr.get("name", "")
            scores["delta"] = round(scores["score"] - current_scores.get("score", 0), 2)
            alternatives.append(scores)

        alternatives.sort(key=lambda x: x["score"], reverse=True)
        return {"current": current_scores, "alternatives": alternatives}

    def tune_weights(self, weights: Dict) -> List[Dict]:
        """Re-score all matches with adjusted weights."""
        merged = {**SCORING_WEIGHTS, **weights}
        tuned_scorer = CompatibilityScorer(self._color_rankings, self._style_rankings, weights=merged)

        results = []
        for match in self.dm.matches:
            if match["type"] == "individual":
                swimmer = self.dm.get_swimmer(match["swimmer_id"])
                instr = self.dm.get_instructor(match["instructor_id"])
                if not swimmer or not instr:
                    continue
                original = self.score_swimmer_instructor(swimmer, instr)
                tuned = self.score_swimmer_instructor(swimmer, instr, tuned_scorer)
                results.append({
                    "swimmer_id": match["swimmer_id"],
                    "swimmer_name": match.get("swimmer_name", ""),
                    "instructor_id": match["instructor_id"],
                    "instructor_name": match.get("instructor_name", ""),
                    "original_score": original["score"],
                    "tuned_score": tuned["score"],
                    "delta": round(tuned["score"] - original["score"], 2),
                })
            elif match["type"] == "pair":
                # Score both swimmers in pair
                s1 = self.dm.get_swimmer(match["swimmer_1_id"])
                s2 = self.dm.get_swimmer(match["swimmer_2_id"])
                instr = self.dm.get_instructor(match["instructor_id"])
                if not s1 or not s2 or not instr:
                    continue
                orig1 = self.score_swimmer_instructor(s1, instr)
                orig2 = self.score_swimmer_instructor(s2, instr)
                tuned1 = self.score_swimmer_instructor(s1, instr, tuned_scorer)
                tuned2 = self.score_swimmer_instructor(s2, instr, tuned_scorer)
                orig_avg = round((orig1["score"] + orig2["score"]) / 2, 2)
                tuned_avg = round((tuned1["score"] + tuned2["score"]) / 2, 2)
                results.append({
                    "swimmer_id": f"{match['swimmer_1_id']}+{match['swimmer_2_id']}",
                    "swimmer_name": f"{match.get('swimmer_1_name', '')} & {match.get('swimmer_2_name', '')}",
                    "instructor_id": match["instructor_id"],
                    "instructor_name": match.get("instructor_name", ""),
                    "original_score": orig_avg,
                    "tuned_score": tuned_avg,
                    "delta": round(tuned_avg - orig_avg, 2),
                })
        return results

    def relax_constraint(self, swimmer_id: int, constraint: str) -> Dict:
        """Show which instructors become eligible when a constraint is relaxed."""
        swimmer = self.dm.get_swimmer(swimmer_id)
        if not swimmer:
            return {"error": "Swimmer not found"}

        eligible = []
        for instr in self.dm.all_instructors():
            blocked_by = self.check_constraints(swimmer, instr)
            if constraint in blocked_by:
                # This instructor is blocked by the relaxed constraint
                scores = self.score_swimmer_instructor(swimmer, instr)
                scores["instructor_id"] = instr["instructor_id"]
                scores["instructor_name"] = instr.get("name", "")
                scores["blocked_by"] = blocked_by
                eligible.append(scores)

        eligible.sort(key=lambda x: x["score"], reverse=True)
        return {"swimmer_id": swimmer_id, "relaxed": constraint, "eligible_instructors": eligible}

    def check_constraints(self, swimmer: Dict, instructor: Dict) -> List[str]:
        """Check which hard constraints block this swimmer-instructor pair."""
        blocked = []
        # HC-2: Adapted
        if swimmer.get("has_special_needs") and not instructor.get("can_teach_adapted"):
            blocked.append("adapted")
        # HC-3: Age routing
        age = swimmer.get("age", 10)
        if age < 2.5 and not instructor.get("can_teach_babies"):
            blocked.append("babies")
        if age >= 18 and not instructor.get("can_teach_adults"):
            blocked.append("adults")
        return blocked
