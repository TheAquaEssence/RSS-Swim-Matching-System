"""
Ranking data loader for the compatibility scoring module.

Loads swimmer type ranking CSVs into efficient lookup dictionaries.
"""

import os
from typing import Dict, Tuple

import pandas as pd

from .config import NORMALIZATION


class RankingLoader:
    """
    Loads and validates ranking tables from CSV files.

    Expected files in source_dir:
    - swimmer_type_color_rankings.csv  (columns: swimmer_type_id, color_id, rank)
    - swimmer_type_style_rankings.csv  (columns: swimmer_type_id, style_id, rank)
    """

    def __init__(self, source_dir: str):
        self.source_dir = source_dir
        self.color_rankings: Dict[Tuple[int, int], int] = {}
        self.style_rankings: Dict[Tuple[int, int], int] = {}

    def load_all(self) -> Tuple[Dict[Tuple[int, int], int], Dict[Tuple[int, int], int]]:
        """
        Load both ranking files and return the dictionaries.

        Returns:
            (color_rankings, style_rankings) where each maps
            (swimmer_type_id, trait_id) -> rank
        """
        self._load_color_rankings()
        self._load_style_rankings()
        self._validate()
        return self.color_rankings, self.style_rankings

    def _load_color_rankings(self) -> None:
        path = os.path.join(self.source_dir, 'swimmer_type_color_rankings.csv')
        df = pd.read_csv(path)
        for _, row in df.iterrows():
            key = (int(row['swimmer_type_id']), int(row['color_id']))
            self.color_rankings[key] = int(row['rank'])

    def _load_style_rankings(self) -> None:
        path = os.path.join(self.source_dir, 'swimmer_type_style_rankings.csv')
        df = pd.read_csv(path)
        for _, row in df.iterrows():
            key = (int(row['swimmer_type_id']), int(row['style_id']))
            self.style_rankings[key] = int(row['rank'])

    def _validate(self) -> None:
        """Validate that all expected swimmer_type × trait combinations exist."""
        num_colors = NORMALIZATION['num_colors']
        num_styles = NORMALIZATION['num_styles']

        # Collect all swimmer type IDs present in the data
        color_types = {k[0] for k in self.color_rankings}
        style_types = {k[0] for k in self.style_rankings}
        all_types = color_types | style_types

        errors = []

        for type_id in sorted(all_types):
            # Check color rankings completeness
            color_ranks = []
            for color_id in range(1, num_colors + 1):
                key = (type_id, color_id)
                if key not in self.color_rankings:
                    errors.append(
                        f"Missing color ranking: swimmer_type {type_id}, color {color_id}"
                    )
                else:
                    color_ranks.append(self.color_rankings[key])

            # Verify ranks form a complete permutation (1..num_colors)
            if sorted(color_ranks) != list(range(1, num_colors + 1)):
                errors.append(
                    f"Swimmer type {type_id} color ranks are not a valid permutation: {color_ranks}"
                )

            # Check style rankings completeness
            style_ranks = []
            for style_id in range(1, num_styles + 1):
                key = (type_id, style_id)
                if key not in self.style_rankings:
                    errors.append(
                        f"Missing style ranking: swimmer_type {type_id}, style {style_id}"
                    )
                else:
                    style_ranks.append(self.style_rankings[key])

            # Verify ranks form a complete permutation (1..num_styles)
            if sorted(style_ranks) != list(range(1, num_styles + 1)):
                errors.append(
                    f"Swimmer type {type_id} style ranks are not a valid permutation: {style_ranks}"
                )

        if errors:
            raise ValueError(
                f"Ranking validation failed:\n" + "\n".join(errors)
            )
