"""
Module Dependency Analyzer

Analyzes dependencies between workflow modules:
- Which modules depend on which
- Dependency depth (transitive dependencies)
- Impact analysis (what breaks if X changes)
- Installation requirements

Design principles:
- Non-invasive: analyzes without modifying
- Comprehensive: covers all dependency types
- Actionable: provides clear recommendations
"""

import ast
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class DependencyType(Enum):
    """Types of dependencies"""
    IMPORT = "import"           # Python import
    RUNTIME = "runtime"         # Runtime dependency
    OPTIONAL = "optional"       # Optional/soft dependency
    PEER = "peer"               # Must be same version
    DEV = "dev"                 # Development only


@dataclass
class Dependency:
    """A single dependency"""
    name: str
    dep_type: DependencyType = DependencyType.IMPORT
    version: Optional[str] = None
    optional: bool = False
    source_module: str = ""
    source_line: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.dep_type.value,
            "version": self.version,
            "optional": self.optional,
            "source_module": self.source_module,
            "source_line": self.source_line,
        }


@dataclass
class ModuleDependencies:
    """Dependencies for a single module"""
    module_id: str
    module_path: str
    direct_deps: List[Dependency] = field(default_factory=list)
    transitive_deps: Set[str] = field(default_factory=set)
    dependents: Set[str] = field(default_factory=set)  # Modules that depend on this

    @property
    def depth(self) -> int:
        """Dependency depth (max chain length)"""
        return len(self.transitive_deps)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_id": self.module_id,
            "module_path": self.module_path,
            "direct_deps": [d.to_dict() for d in self.direct_deps],
            "transitive_deps": list(self.transitive_deps),
            "dependents": list(self.dependents),
            "depth": self.depth,
        }


@dataclass
class ImpactAnalysis:
    """Impact analysis for changing a module"""
    module_id: str
    directly_affected: List[str] = field(default_factory=list)
    transitively_affected: List[str] = field(default_factory=list)
    total_impact: int = 0
    risk_level: str = "low"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_id": self.module_id,
            "directly_affected": self.directly_affected,
            "transitively_affected": self.transitively_affected,
            "total_impact": self.total_impact,
            "risk_level": self.risk_level,
        }


@dataclass
class AnalysisReport:
    """Full dependency analysis report"""
    modules: Dict[str, ModuleDependencies] = field(default_factory=dict)
    external_deps: Set[str] = field(default_factory=set)
    circular_deps: List[List[str]] = field(default_factory=list)
    orphan_modules: List[str] = field(default_factory=list)
    most_depended: List[Tuple[str, int]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_modules": len(self.modules),
            "external_deps": list(self.external_deps),
            "circular_deps": self.circular_deps,
            "orphan_modules": self.orphan_modules,
            "most_depended": [
                {"module": m, "dependent_count": c}
                for m, c in self.most_depended
            ],
            "modules": {k: v.to_dict() for k, v in self.modules.items()},
        }


class DependencyAnalyzer:
    """
    Analyzes module dependencies.

    Usage:
        analyzer = DependencyAnalyzer()
        analyzer.analyze_directory("src/core/modules")
        report = analyzer.get_report()

        # Impact analysis
        impact = analyzer.analyze_impact("browser.click")
    """

    def __init__(self):
        """Initialize analyzer"""
        self._modules: Dict[str, ModuleDependencies] = {}
        self._graph: Dict[str, Set[str]] = defaultdict(set)
        self._reverse_graph: Dict[str, Set[str]] = defaultdict(set)
        self._external_deps: Set[str] = set()

    def analyze_file(self, file_path: str) -> ModuleDependencies:
        """
        Analyze dependencies in a single file.

        Args:
            file_path: Path to Python file

        Returns:
            ModuleDependencies for the file
        """
        path = Path(file_path)
        module_id = self._path_to_module_id(str(path))

        try:
            content = path.read_text(encoding="utf-8")
            tree = ast.parse(content)
        except Exception as e:
            logger.warning(f"Could not parse {file_path}: {e}")
            return ModuleDependencies(
                module_id=module_id,
                module_path=str(path),
            )

        deps = self._extract_dependencies(tree, module_id)

        module_deps = ModuleDependencies(
            module_id=module_id,
            module_path=str(path),
            direct_deps=deps,
        )

        # Build graph
        for dep in deps:
            if self._is_internal_module(dep.name):
                self._graph[module_id].add(dep.name)
                self._reverse_graph[dep.name].add(module_id)
            else:
                self._external_deps.add(dep.name)

        self._modules[module_id] = module_deps
        return module_deps

    def analyze_directory(
        self,
        directory: str,
        recursive: bool = True,
    ) -> Dict[str, ModuleDependencies]:
        """
        Analyze all Python files in a directory.

        Args:
            directory: Directory path
            recursive: Whether to scan subdirectories

        Returns:
            Dict mapping module IDs to their dependencies
        """
        path = Path(directory)
        pattern = "**/*.py" if recursive else "*.py"

        for file_path in path.glob(pattern):
            # Skip __pycache__ and test files
            if "__pycache__" in str(file_path):
                continue
            if "__init__" in file_path.name:
                continue

            self.analyze_file(str(file_path))

        # Compute transitive dependencies
        self._compute_transitive_deps()

        # Compute dependents
        self._compute_dependents()

        return self._modules

    def analyze_impact(self, module_id: str) -> ImpactAnalysis:
        """
        Analyze impact of changing a module.

        Args:
            module_id: Module to analyze

        Returns:
            ImpactAnalysis showing affected modules
        """
        if module_id not in self._modules:
            return ImpactAnalysis(module_id=module_id)

        # Direct dependents
        directly_affected = list(self._reverse_graph.get(module_id, set()))

        # Transitive dependents (BFS)
        transitively_affected = set()
        queue = list(directly_affected)
        visited = set(directly_affected)

        while queue:
            current = queue.pop(0)
            for dependent in self._reverse_graph.get(current, set()):
                if dependent not in visited:
                    visited.add(dependent)
                    transitively_affected.add(dependent)
                    queue.append(dependent)

        total_impact = len(directly_affected) + len(transitively_affected)

        # Determine risk level
        if total_impact == 0:
            risk_level = "none"
        elif total_impact <= 2:
            risk_level = "low"
        elif total_impact <= 5:
            risk_level = "medium"
        else:
            risk_level = "high"

        return ImpactAnalysis(
            module_id=module_id,
            directly_affected=directly_affected,
            transitively_affected=list(transitively_affected),
            total_impact=total_impact,
            risk_level=risk_level,
        )

    def get_report(self) -> AnalysisReport:
        """
        Generate full analysis report.

        Returns:
            AnalysisReport with all analysis results
        """
        # Find circular dependencies
        circular = self._find_circular_deps()

        # Find orphan modules (no dependents)
        orphans = [
            m for m in self._modules
            if not self._reverse_graph.get(m)
        ]

        # Most depended modules
        dependent_counts = [
            (m, len(self._reverse_graph.get(m, set())))
            for m in self._modules
        ]
        most_depended = sorted(
            dependent_counts,
            key=lambda x: x[1],
            reverse=True,
        )[:10]

        return AnalysisReport(
            modules=dict(self._modules),
            external_deps=self._external_deps,
            circular_deps=circular,
            orphan_modules=orphans,
            most_depended=most_depended,
        )

    def get_install_requirements(self) -> List[str]:
        """
        Get list of external packages that need to be installed.

        Returns:
            List of package names
        """
        # Filter to only pip-installable packages
        stdlib = {
            "os", "sys", "re", "json", "typing", "dataclasses",
            "pathlib", "collections", "enum", "abc", "logging",
            "asyncio", "time", "datetime", "uuid", "hashlib",
            "functools", "itertools", "copy", "io", "tempfile",
            "threading", "queue", "unittest", "ast", "traceback",
        }

        return [
            dep for dep in self._external_deps
            if dep.split(".")[0] not in stdlib
        ]

    def get_dependency_tree(
        self,
        module_id: str,
        max_depth: int = 5,
    ) -> Dict[str, Any]:
        """
        Get dependency tree for a module.

        Args:
            module_id: Root module
            max_depth: Maximum tree depth

        Returns:
            Nested dict representing dependency tree
        """
        def build_tree(mod: str, depth: int, visited: Set[str]) -> Dict:
            if depth > max_depth or mod in visited:
                return {"module": mod, "deps": "..."}

            visited.add(mod)
            deps = self._graph.get(mod, set())

            return {
                "module": mod,
                "deps": [
                    build_tree(d, depth + 1, visited.copy())
                    for d in deps
                ],
            }

        return build_tree(module_id, 0, set())

    def _extract_dependencies(
        self,
        tree: ast.AST,
        source_module: str,
    ) -> List[Dependency]:
        """Extract dependencies from AST"""
        deps = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    deps.append(Dependency(
                        name=alias.name,
                        dep_type=DependencyType.IMPORT,
                        source_module=source_module,
                        source_line=node.lineno,
                    ))

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    # Check if it's an optional import (in try block)
                    optional = self._is_in_try_block(tree, node.lineno)
                    deps.append(Dependency(
                        name=node.module,
                        dep_type=DependencyType.IMPORT,
                        optional=optional,
                        source_module=source_module,
                        source_line=node.lineno,
                    ))

        return deps

    def _is_in_try_block(self, tree: ast.AST, line: int) -> bool:
        """Check if a line is inside a try block"""
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                if node.lineno < line:
                    # Check if line is within try body
                    for child in node.body:
                        if hasattr(child, 'lineno') and child.lineno == line:
                            return True
        return False

    def _path_to_module_id(self, file_path: str) -> str:
        """Convert file path to module ID"""
        path = Path(file_path)
        parts = list(path.with_suffix("").parts)

        # Find src in path
        try:
            src_idx = parts.index("src")
            parts = parts[src_idx:]
        except ValueError:
            pass

        return ".".join(parts)

    def _is_internal_module(self, module_name: str) -> bool:
        """Check if module is internal (part of this project)"""
        return module_name.startswith("src.") or module_name.startswith("flyto2.")

    def _compute_transitive_deps(self) -> None:
        """Compute transitive dependencies for all modules"""
        for module_id in self._modules:
            transitive = set()
            visited = set()
            queue = list(self._graph.get(module_id, set()))

            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                transitive.add(current)

                for dep in self._graph.get(current, set()):
                    if dep not in visited:
                        queue.append(dep)

            self._modules[module_id].transitive_deps = transitive

    def _compute_dependents(self) -> None:
        """Compute dependents for all modules"""
        for module_id in self._modules:
            self._modules[module_id].dependents = self._reverse_graph.get(
                module_id, set()
            )

    def _find_circular_deps(self) -> List[List[str]]:
        """Find circular dependencies"""
        cycles = []
        visited = set()
        rec_stack = set()
        path = []

        def dfs(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in self._graph.get(node, set()):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    # Found cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)
                    return True

            path.pop()
            rec_stack.remove(node)
            return False

        for node in list(self._graph.keys()):
            if node not in visited:
                dfs(node)

        return cycles


# =============================================================================
# Convenience functions
# =============================================================================

def analyze_module_dependencies(
    directory: str,
    output_format: str = "summary",
) -> Dict[str, Any]:
    """
    Analyze module dependencies in a directory.

    Args:
        directory: Directory to analyze
        output_format: "summary", "full", or "tree"

    Returns:
        Analysis results
    """
    analyzer = DependencyAnalyzer()
    analyzer.analyze_directory(directory)
    report = analyzer.get_report()

    if output_format == "summary":
        return {
            "total_modules": len(report.modules),
            "external_deps": list(report.external_deps)[:10],
            "circular_deps_count": len(report.circular_deps),
            "orphan_count": len(report.orphan_modules),
            "most_depended": report.most_depended[:5],
        }
    elif output_format == "full":
        return report.to_dict()
    else:
        return {"error": f"Unknown format: {output_format}"}


def get_module_impact(
    directory: str,
    module_id: str,
) -> Dict[str, Any]:
    """
    Get impact analysis for a specific module.

    Args:
        directory: Directory containing modules
        module_id: Module to analyze

    Returns:
        Impact analysis results
    """
    analyzer = DependencyAnalyzer()
    analyzer.analyze_directory(directory)
    impact = analyzer.analyze_impact(module_id)
    return impact.to_dict()
