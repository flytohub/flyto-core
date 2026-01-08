"""
Capability Detector

AST-based detection of capabilities from:
- Import statements (httpx -> network.access)
- Function calls (open("w") -> filesystem.write)
- Attribute access patterns
"""

import ast
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from ..constants import IMPORT_CAPABILITY_MAP, CALL_CAPABILITY_MAP


@dataclass
class CapabilityAnalysis:
    """Result of capability analysis."""

    capabilities: Set[str] = field(default_factory=set)
    imports: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    env_access: List[Tuple[int, str]] = field(default_factory=list)


class CapabilityDetector(ast.NodeVisitor):
    """AST visitor that detects capabilities from code patterns."""

    def __init__(self):
        self.capabilities: Set[str] = set()
        self.imports: List[str] = []
        self.functions: List[str] = []
        self.classes: List[str] = []
        self.env_access: List[Tuple[int, str]] = []

    def visit_Import(self, node: ast.Import) -> None:
        """Detect capabilities from import statements."""
        for alias in node.names:
            module_name = alias.name.split(".")[0]
            self.imports.append(alias.name)

            if module_name in IMPORT_CAPABILITY_MAP:
                self.capabilities.add(IMPORT_CAPABILITY_MAP[module_name])

        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Detect capabilities from from...import statements."""
        if node.module:
            module_name = node.module.split(".")[0]
            self.imports.append(node.module)

            if module_name in IMPORT_CAPABILITY_MAP:
                self.capabilities.add(IMPORT_CAPABILITY_MAP[module_name])

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Detect capabilities from function calls."""
        if isinstance(node.func, ast.Attribute):
            # Check for os.getenv()
            if isinstance(node.func.value, ast.Name):
                if node.func.value.id == "os" and node.func.attr == "getenv":
                    self.env_access.append((node.lineno, f"os.{node.func.attr}"))

                # Check for subprocess calls
                if node.func.value.id == "subprocess" and node.func.attr in (
                    "run", "call", "Popen", "check_output", "check_call"
                ):
                    self.capabilities.add("shell.execute")
                    # Check if it's a git command
                    if node.args:
                        self._check_git_command(node.args[0])

            # Check for os.environ.get()
            if isinstance(node.func.value, ast.Attribute):
                if isinstance(node.func.value.value, ast.Name):
                    if (node.func.value.value.id == "os" and
                        node.func.value.attr == "environ" and
                        node.func.attr == "get"):
                        self.env_access.append((node.lineno, "os.environ.get"))

            # Check for Path().read_text() / write_text()
            if isinstance(node.func.value, ast.Call):
                if isinstance(node.func.value.func, ast.Name):
                    if node.func.value.func.id == "Path":
                        if node.func.attr in ("read_text", "read_bytes"):
                            self.capabilities.add("filesystem.read")
                        elif node.func.attr in ("write_text", "write_bytes"):
                            self.capabilities.add("filesystem.write")

            # Check call patterns from constant map
            func_name = self._get_func_name(node.func)
            if func_name:
                self._check_call_patterns(func_name, node)

        # Check for bare open() call
        if isinstance(node.func, ast.Name) and node.func.id == "open":
            self._detect_open_mode(node)

        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        """Detect os.environ['KEY'] access."""
        if isinstance(node.value, ast.Attribute):
            if isinstance(node.value.value, ast.Name):
                if node.value.value.id == "os" and node.value.attr == "environ":
                    key = ""
                    if isinstance(node.slice, ast.Constant):
                        key = str(node.slice.value)
                    self.env_access.append((node.lineno, f"os.environ[{key!r}]"))

        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Track function definitions."""
        self.functions.append(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Track async function definitions."""
        self.functions.append(node.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track class definitions."""
        self.classes.append(node.name)
        self.generic_visit(node)

    def _get_func_name(self, node: ast.expr) -> Optional[str]:
        """Extract function name from call node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name):
                return f"{node.value.id}.{node.attr}"
            elif isinstance(node.value, ast.Attribute):
                if isinstance(node.value.value, ast.Name):
                    return f"{node.value.value.id}.{node.value.attr}.{node.attr}"
        return None

    def _check_call_patterns(self, func_name: str, node: ast.Call) -> None:
        """Check if function call implies a capability."""
        # Direct matches from pattern map
        if func_name in CALL_CAPABILITY_MAP:
            cap = CALL_CAPABILITY_MAP[func_name]
            if cap != "FORBIDDEN":  # FORBIDDEN is handled by security rules
                self.capabilities.add(cap)

        # Path method patterns
        if ".read_text" in func_name or ".read_bytes" in func_name:
            self.capabilities.add("filesystem.read")
        if ".write_text" in func_name or ".write_bytes" in func_name:
            self.capabilities.add("filesystem.write")

    def _detect_open_mode(self, node: ast.Call) -> None:
        """Detect read/write mode from open() call."""
        mode = "r"  # default mode
        for i, arg in enumerate(node.args):
            if i == 1 and isinstance(arg, ast.Constant):
                mode = str(arg.value)
                break
        for kw in node.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                mode = str(kw.value.value)
                break

        if "w" in mode or "a" in mode or "x" in mode:
            self.capabilities.add("filesystem.write")
        else:
            self.capabilities.add("filesystem.read")

    def _check_git_command(self, arg: ast.expr) -> None:
        """Check if subprocess call is running git."""
        if isinstance(arg, ast.List) and arg.elts:
            first = arg.elts[0]
            if isinstance(first, ast.Constant) and first.value == "git":
                # git commands still need shell.execute permission
                pass
        elif isinstance(arg, ast.Constant):
            if isinstance(arg.value, str) and arg.value.startswith("git "):
                pass


def detect_capabilities(source_code: str) -> Set[str]:
    """
    Detect required capabilities from Python source code.

    Args:
        source_code: Python source code to analyze

    Returns:
        Set of capability strings (e.g., {"network.access", "filesystem.read"})
    """
    try:
        tree = ast.parse(source_code)
        detector = CapabilityDetector()
        detector.visit(tree)
        return detector.capabilities
    except SyntaxError:
        return set()


def detect_imports(source_code: str) -> List[str]:
    """
    Extract all import statements from source code.

    Args:
        source_code: Python source code to analyze

    Returns:
        List of imported module names
    """
    try:
        tree = ast.parse(source_code)
        detector = CapabilityDetector()
        detector.visit(tree)
        return detector.imports
    except SyntaxError:
        return []


def analyze_capabilities(source_code: str) -> CapabilityAnalysis:
    """
    Perform full capability analysis on source code.

    Args:
        source_code: Python source code to analyze

    Returns:
        CapabilityAnalysis with all findings
    """
    try:
        tree = ast.parse(source_code)
        detector = CapabilityDetector()
        detector.visit(tree)
        return CapabilityAnalysis(
            capabilities=detector.capabilities,
            imports=detector.imports,
            functions=detector.functions,
            classes=detector.classes,
            env_access=detector.env_access,
        )
    except SyntaxError:
        return CapabilityAnalysis()
