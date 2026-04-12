# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Evolution Memory — JSON-file persistence for workflow patches and stats.

No external dependencies. Just a JSON file at ~/.flyto/evolution.json.
Tracks: runs, failures, auto-healed patches, success rates per recipe.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_EVOLUTION_PATH = os.path.expanduser("~/.flyto/evolution.json")


class EvolutionMemory:
    """Persistent memory for workflow evolution.

    Stores patches, run stats, and learned fixes in a simple JSON file.
    Thread-safe via atomic write (write to tmp then rename).
    """

    def __init__(self, path: Optional[str] = None):
        self._path = path or DEFAULT_EVOLUTION_PATH
        self._data: Dict[str, Any] = {"version": 1, "recipes": {}}
        self._load()

    def _load(self):
        """Load evolution data from disk."""
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load evolution memory: {e}")
            self._data = {"version": 1, "recipes": {}}

    def _save(self):
        """Atomically save evolution data to disk."""
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            tmp_path = self._path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self._path)
        except IOError as e:
            logger.error(f"Failed to save evolution memory: {e}")

    def _get_recipe(self, recipe_id: str) -> Dict:
        """Get or create recipe entry."""
        if recipe_id not in self._data["recipes"]:
            self._data["recipes"][recipe_id] = {
                "runs": 0,
                "successes": 0,
                "failures": 0,
                "patches": [],
                "created_at": time.time(),
                "last_run": None,
            }
        return self._data["recipes"][recipe_id]

    def record_run(self, recipe_id: str, success: bool):
        """Record a workflow run."""
        recipe = self._get_recipe(recipe_id)
        recipe["runs"] += 1
        recipe["last_run"] = time.time()
        if success:
            recipe["successes"] += 1
        else:
            recipe["failures"] += 1
        self._save()

    def add_patch(self, recipe_id: str, patch: Dict[str, Any]):
        """Record a successful auto-heal patch."""
        recipe = self._get_recipe(recipe_id)
        patch["timestamp"] = time.time()
        patch["applied_count"] = 0

        # Deduplicate: don't add if same step + same fix already exists
        for existing in recipe["patches"]:
            if (existing.get("step_id") == patch.get("step_id") and
                    existing.get("fix_type") == patch.get("fix_type") and
                    existing.get("new_value") == patch.get("new_value")):
                return

        recipe["patches"].append(patch)

        # Keep only last 50 patches per recipe
        if len(recipe["patches"]) > 50:
            recipe["patches"] = recipe["patches"][-50:]

        self._save()
        logger.info(f"Evolution: saved patch for {recipe_id}/{patch.get('step_id')}")

    def get_patches(self, recipe_id: str, step_id: Optional[str] = None) -> List[Dict]:
        """Get patches for a recipe, optionally filtered by step."""
        recipe = self._get_recipe(recipe_id)
        patches = recipe["patches"]
        if step_id:
            patches = [p for p in patches if p.get("step_id") == step_id]
        return patches

    def mark_patch_applied(self, recipe_id: str, patch_index: int):
        """Increment applied count for a patch."""
        recipe = self._get_recipe(recipe_id)
        if 0 <= patch_index < len(recipe["patches"]):
            recipe["patches"][patch_index]["applied_count"] = \
                recipe["patches"][patch_index].get("applied_count", 0) + 1
            self._save()

    def get_stats(self, recipe_id: str) -> Dict[str, Any]:
        """Get run statistics for a recipe."""
        recipe = self._get_recipe(recipe_id)
        runs = recipe["runs"]
        return {
            "runs": runs,
            "successes": recipe["successes"],
            "failures": recipe["failures"],
            "success_rate": recipe["successes"] / runs if runs > 0 else 0,
            "patches_count": len(recipe["patches"]),
            "last_run": recipe["last_run"],
        }

    def get_all_stats(self) -> Dict[str, Dict]:
        """Get stats for all recipes."""
        return {rid: self.get_stats(rid) for rid in self._data["recipes"]}
