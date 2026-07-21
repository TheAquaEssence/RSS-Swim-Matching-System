"""Loads and caches result.json + profiles.json from a solver job directory."""

import json
from pathlib import Path
from typing import Dict, List, Optional

from core.flags import expand_flag_codes, get_highest_severity


class DataManager:
    """Loads and caches result.json + profiles.json from a solver job directory."""

    def __init__(self, job_dir: str):
        self.job_dir = Path(job_dir)
        self._result = {}
        self._profiles = {"swimmers": {}, "instructors": {}}
        self._load()

    def _load(self):
        result_path = self.job_dir / "result.json"
        if result_path.exists():
            with open(result_path, "r") as f:
                self._result = json.load(f)

        # profiles.json is always written to job_dir by solver_wrapper.py.
        # The result_files.profiles path is relative to app_root (not job_dir),
        # so we always look for it directly in job_dir.
        profiles_path = self.job_dir / "profiles.json"

        if profiles_path.exists():
            with open(profiles_path, "r") as f:
                self._profiles = json.load(f)

    def reload(self):
        """Re-read data from disk (after re-solve)."""
        self._load()

    @property
    def summary(self) -> Dict:
        return self._result.get("summary", {})

    @property
    def matches(self) -> List[Dict]:
        return self._result.get("matches", [])

    @property
    def unassigned(self) -> List[Dict]:
        return self._result.get("unassigned", [])

    def get_match(self, index: int) -> Optional[Dict]:
        if 0 <= index < len(self.matches):
            return self.matches[index]
        return None

    def get_swimmer(self, swimmer_id: int) -> Optional[Dict]:
        return self._profiles.get("swimmers", {}).get(str(swimmer_id))

    def get_instructor(self, instructor_id: int) -> Optional[Dict]:
        return self._profiles.get("instructors", {}).get(str(instructor_id))

    def all_instructors(self) -> List[Dict]:
        return list(self._profiles.get("instructors", {}).values())

    def all_swimmers(self) -> List[Dict]:
        return list(self._profiles.get("swimmers", {}).values())

    @staticmethod
    def _person_name(obj) -> str:
        """Extract a display name from a nested swimmer/instructor dict."""
        if not obj:
            return "-"
        if obj.get("first_name") or obj.get("last_name"):
            return f"{obj.get('first_name', '')} {obj.get('last_name', '')}".strip()
        return obj.get("name", "-")

    def _swimmer_label(self, match: Dict) -> str:
        """Build a swimmer display label for any match type."""
        if match.get("type") == "pair":
            s1 = match.get("swimmer_1_name") or self._person_name(match.get("swimmer_1"))
            s2 = match.get("swimmer_2_name") or self._person_name(match.get("swimmer_2"))
            return f"{s1} & {s2}"
        return match.get("swimmer_name") or self._person_name(match.get("swimmer"))

    @staticmethod
    def _normalize_confidence(value) -> Optional[float]:
        if value is None:
            return None
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return None
        if 0 < confidence <= 1:
            confidence *= 100
        return confidence

    @staticmethod
    def _expanded_match_flags(match: Dict) -> List[Dict]:
        flags = match.get("flags")
        if isinstance(flags, list) and flags:
            return [flag for flag in flags if isinstance(flag, dict)]

        flag_codes = match.get("flag_codes")
        if isinstance(flag_codes, list) and flag_codes:
            return expand_flag_codes([str(code) for code in flag_codes if code])

        return []

    def _is_flagged_match(self, match: Dict, threshold: float = 50) -> bool:
        confidence = self._normalize_confidence(match.get("confidence"))
        if confidence is not None and confidence < threshold:
            return True
        if match.get("continuity_dispute"):
            return True
        if self._expanded_match_flags(match):
            return True

        severity = str(match.get("review_severity") or "").strip().lower()
        return severity not in ("", "none")

    def _flag_reasons(self, match: Dict, threshold: float = 50) -> List[str]:
        reasons: List[str] = []
        confidence = self._normalize_confidence(match.get("confidence"))
        if confidence is not None and confidence < threshold:
            reasons.append("Low confidence")
        if match.get("continuity_dispute"):
            reasons.append("Continuity dispute")

        for flag in self._expanded_match_flags(match):
            title = str(flag.get("title") or flag.get("code") or "").strip()
            if title and title not in reasons:
                reasons.append(title)

        if not reasons:
            summary = str(match.get("flag_summary") or "").strip()
            if summary:
                reasons.append(summary)

        return reasons

    def get_flagged_matches(self, threshold: int = 50) -> List[Dict]:
        return [m for m in self.matches if self._is_flagged_match(m, threshold)]

    def get_confidence_distribution(self) -> dict:
        """Bucket confidences into 10 bins (0-10, 10-20, ..., 90-100)."""
        buckets = ["0-10", "10-20", "20-30", "30-40", "40-50",
                   "50-60", "60-70", "70-80", "80-90", "90-100"]
        counts = [0] * 10
        for m in self.matches:
            conf = self._normalize_confidence(m.get("confidence"))
            if conf is None:
                continue
            idx = min(int(conf // 10), 9)
            counts[idx] += 1
        return {"buckets": buckets, "counts": counts}

    def get_type_breakdown(self) -> dict:
        """Count matches by match_type (continuity/compatibility) and format (individual/pair)."""
        result = {"continuity": 0, "compatibility": 0, "individual": 0, "pair": 0}
        for m in self.matches:
            mt = m.get("match_type", "compatibility")
            result[mt] = result.get(mt, 0) + 1
            fmt = m.get("type", "individual")
            result[fmt] = result.get(fmt, 0) + 1
        return result

    def get_flagged_matches_with_reasons(self, threshold: float = 50) -> list:
        """Return flagged matches with index and user-facing review reasons."""
        flagged = []
        for i, m in enumerate(self.matches):
            conf = self._normalize_confidence(m.get("confidence"))
            reasons = self._flag_reasons(m, threshold)
            if not reasons:
                continue

            severity = str(m.get("review_severity") or "").strip().lower()
            if severity in ("", "none"):
                severity = get_highest_severity([
                    str(flag.get("code") or "")
                    for flag in self._expanded_match_flags(m)
                    if flag.get("code")
                ])

            flagged.append({
                "idx": i,
                "swimmer_name": self._swimmer_label(m),
                "instructor_name": m.get("instructor_name", "-"),
                "confidence": round(conf, 1) if conf is not None else 0.0,
                "flag_reason": ", ".join(reasons),
                "review_severity": severity or "none",
            })
        return flagged
