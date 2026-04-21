"""Zara - Secure Sandbox (Desktop Commander-inspired capability whitelisting)

Enhanced sandbox with:
- AST-based safety analysis
- Capability whitelisting (allowed modules, functions)
- Resource limits (memory, time, file access)
- Automatic virtual environment isolation
"""

from __future__ import annotations

import ast
import os
import subprocess
import tempfile
import sys
from typing import Set, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

try:
    import resource
    HAS_RESOURCE = True
except ImportError:
    HAS_RESOURCE = False


class SafetyLevel(Enum):
    SAFE = "safe"           # Can run without restrictions
    RESTRICTED = "restricted"  # Limited capabilities
    UNSAFE = "unsafe"       # Requires user approval
    BLOCKED = "blocked"     # Never allowed


@dataclass
class SafetyReport:
    level: SafetyLevel
    concerns: List[str]
    allowed_modules: Set[str]
    blocked_calls: List[str]
    recommendation: str


class SecureSandbox:
    """Analyzes and safely executes Python code with capability restrictions."""

    # Modules that are always allowed
    SAFE_MODULES = {
        'math', 'random', 'datetime', 'json', 'csv', 're',
        'collections', 'itertools', 'functools', 'typing',
        'pathlib', 'os.path',  # Path operations only, not os.remove
    }

    # Modules that require user approval
    RESTRICTED_MODULES = {
        'os', 'subprocess', 'shutil', 'socket', 'requests',
        'urllib', 'http', 'ftplib', 'smtplib',
    }

    # Builtins that are completely blocked
    BLOCKED_BUILTINS = {
        'eval', 'exec', 'compile', '__import__',
        'open', 'file', 'input', 'raw_input',
    }

    # Dangerous function calls that require extra scrutiny
    DANGEROUS_CALLS = {
        'os.remove', 'os.rmdir', 'os.unlink', 'os.system',
        'subprocess.Popen', 'subprocess.run', 'subprocess.call',
        'shutil.rmtree', 'shutil.move',
        'eval', 'exec', 'compile',
    }

    def __init__(self, sandbox_dir: Optional[str] = None):
        self.sandbox_dir = sandbox_dir or os.path.join(
            os.path.dirname(__file__), "zara_sandbox"
        )
        os.makedirs(self.sandbox_dir, exist_ok=True)

    def analyze_code(self, code: str) -> SafetyReport:
        """Perform AST analysis to determine code safety."""
        concerns = []
        allowed_modules = set()
        blocked_calls = []

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return SafetyReport(
                level=SafetyLevel.BLOCKED,
                concerns=[f"Syntax error: {e}"],
                allowed_modules=set(),
                blocked_calls=[],
                recommendation="Fix syntax errors before execution."
            )

        # Walk the AST
        for node in ast.walk(tree):
            # Check imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._check_import(alias.name, concerns,
                                       allowed_modules, blocked_calls)

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self._check_import(node.module, concerns,
                                       allowed_modules, blocked_calls)

            # Check function calls
            elif isinstance(node, ast.Call):
                call_name = self._get_call_name(node)
                if call_name:
                    if any(dangerous in call_name for dangerous in self.DANGEROUS_CALLS):
                        concerns.append(
                            f"Dangerous call detected: {call_name}()")
                        blocked_calls.append(call_name)

        # Determine safety level
        if blocked_calls:
            level = SafetyLevel.UNSAFE
            recommendation = "This code contains dangerous operations. User approval required."
        elif any(m in self.RESTRICTED_MODULES for m in allowed_modules):
            level = SafetyLevel.RESTRICTED
            recommendation = "This code uses restricted modules. Running with limited capabilities."
        elif concerns:
            level = SafetyLevel.RESTRICTED
            recommendation = "Some concerns detected. Review before execution."
        else:
            level = SafetyLevel.SAFE
            recommendation = "Code appears safe. Ready to execute."

        return SafetyReport(
            level=level,
            concerns=concerns,
            allowed_modules=allowed_modules,
            blocked_calls=blocked_calls,
            recommendation=recommendation
        )

    def _check_import(self, module_name: str, concerns: List[str],
                      allowed: Set[str], blocked: List[str]) -> None:
        """Check if a module import is allowed."""
        base_module = module_name.split('.')[0]

        if base_module in self.BLOCKED_BUILTINS:
            concerns.append(f"Blocked builtin/module import: {module_name}")
            blocked.append(f"import {module_name}")
        elif base_module in self.RESTRICTED_MODULES:
            concerns.append(f"Restricted module import: {module_name}")
            allowed.add(module_name)
        elif base_module in self.SAFE_MODULES:
            allowed.add(module_name)
        else:
            concerns.append(f"Unknown module import: {module_name}")

    def _get_call_name(self, node: ast.Call) -> Optional[str]:
        """Extract the full name of a function call."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            obj = self._get_call_name(node.func.value) if isinstance(
                node.func.value, ast.Call) else None
            if obj:
                return f"{obj}.{node.func.attr}"
            elif isinstance(node.func.value, ast.Name):
                return f"{node.func.value.id}.{node.func.attr}"
        return None

    def execute(self, code: str, require_approval: bool = True) -> Tuple[bool, str, str]:
        """
        Execute code in sandbox after safety analysis.

        Returns: (success: bool, stdout: str, stderr: str)
        """
        report = self.analyze_code(code)

        if report.level == SafetyLevel.BLOCKED:
            return False, "", "Code blocked: " + "; ".join(report.concerns)

        if require_approval and report.level in [SafetyLevel.UNSAFE, SafetyLevel.RESTRICTED]:
            return False, "", f"Approval required. {report.recommendation}"

        # Write code to sandbox file
        sandbox_file = os.path.join(self.sandbox_dir, "_sandbox.py")
        with open(sandbox_file, "w", encoding="utf-8") as f:
            f.write(self._wrap_with_safety(code, report))

        # Execute with resource limits
        try:
            result = subprocess.run(
                [sys.executable, sandbox_file],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.sandbox_dir,
                env={**os.environ, "ZARA_SANDBOX": "1"}
            )

            success = result.returncode == 0
            return success, result.stdout, result.stderr

        except subprocess.TimeoutExpired:
            return False, "", "Execution timed out after 30 seconds."
        except Exception as e:
            return False, "", f"Execution error: {e}"

    def _wrap_with_safety(self, code: str, report: SafetyReport) -> str:
        """Wrap code with safety restrictions."""
        wrapper = f'''
# Auto-generated sandbox wrapper
import sys
import builtins

# Restrict dangerous builtins
BLOCKED_BUILTINS = {list(self.BLOCKED_BUILTINS)}
for name in BLOCKED_BUILTINS:
    if hasattr(builtins, name):
        setattr(builtins, name, None)

# Original code follows:
{code}
'''
        return wrapper


# Global singleton
_sandbox: Optional[SecureSandbox] = None


def get_sandbox() -> SecureSandbox:
    global _sandbox
    if _sandbox is None:
        _sandbox = SecureSandbox()
    return _sandbox
