"""Parameterized Math Variable Solver & Range Evaluator for Numerical Dynamic Questions.

Supports:
1. Seeded pseudo-random variable sampling based on min_val, max_val, precision, and step.
2. Safe expression parsing and formula evaluation (arithmetic, powers, standard math functions).
3. Instantiation of concrete question text by replacing {{var}} tokens with sampled numbers.
4. Correct answer calculation with tolerance bounds.
"""

from __future__ import annotations

import ast
import math
import operator
import random
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from src.core.models.question_model import NumericalDynamicData, NumericVariableRange

SAFE_MATH_FUNCTIONS: Dict[str, Callable[..., float]] = {
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "sinh": math.sinh,
    "cosh": math.cosh,
    "tanh": math.tanh,
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "exp": math.exp,
    "pow": math.pow,
    "abs": abs,
    "round": round,
}

SAFE_MATH_CONSTANTS: Dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
}

SAFE_MATH_GLOBALS: Dict[str, Any] = {
    "__builtins__": {},
    **SAFE_MATH_FUNCTIONS,
    **SAFE_MATH_CONSTANTS,
}

MAX_FORMULA_LENGTH = 512
MAX_EXPONENT_ABS = 1000.0
MAX_BASE_FOR_LARGE_EXP = 1e6


@dataclass
class DynamicInstantiationResult:
    """Result of instantiating parameterized variables and computing answer."""

    variables: Dict[str, float]
    formatted_variables: Dict[str, str]
    computed_answer: Optional[float]
    formatted_answer: str
    tolerance: float
    unit: str
    instantiated_text: str


class DynamicNumericEngine:
    """Solves and instantiates dynamic numerical questions."""

    @staticmethod
    def sample_variable_value(
        var_range: NumericVariableRange,
        rng: Optional[random.Random] = None,
    ) -> float:
        """Sample a value within [min_val, max_val] adhering to precision and step."""
        r = rng if rng is not None else random.Random()
        min_v = var_range.min_val
        max_v = var_range.max_val
        step = var_range.step
        prec = var_range.precision

        if step is not None and step > 0:
            num_steps = int(math.floor((max_v - min_v) / step))
            if num_steps <= 0:
                raw_val = min_v
            else:
                chosen_step = r.randint(0, num_steps)
                raw_val = min_v + (chosen_step * step)
        else:
            raw_val = r.uniform(min_v, max_v)

        val = round(raw_val, prec)
        if prec == 0:
            return float(int(val))
        return val

    @staticmethod
    def _eval_ast_node(node: ast.AST, env: Dict[str, float]) -> float:
        """Recursively evaluate a strictly whitelisted arithmetic AST node."""
        if isinstance(node, ast.Expression):
            return DynamicNumericEngine._eval_ast_node(node.body, env)

        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                return float(node.value)
            raise ValueError(f"Unsupported constant literal in formula: {node.value!r}")

        if isinstance(node, ast.Name):
            if node.id in env:
                return float(env[node.id])
            if node.id in SAFE_MATH_CONSTANTS:
                return float(SAFE_MATH_CONSTANTS[node.id])
            raise ValueError(f"Unknown variable or constant '{node.id}' in formula.")

        if isinstance(node, ast.UnaryOp):
            operand = DynamicNumericEngine._eval_ast_node(node.operand, env)
            if isinstance(node.op, ast.UAdd):
                return +operand
            if isinstance(node.op, ast.USub):
                return -operand
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")

        if isinstance(node, ast.BinOp):
            left = DynamicNumericEngine._eval_ast_node(node.left, env)
            right = DynamicNumericEngine._eval_ast_node(node.right, env)
            if isinstance(node.op, ast.Add):
                return float(left + right)
            if isinstance(node.op, ast.Sub):
                return float(left - right)
            if isinstance(node.op, ast.Mult):
                return float(left * right)
            if isinstance(node.op, ast.Div):
                return float(left / right)
            if isinstance(node.op, ast.FloorDiv):
                return float(left // right)
            if isinstance(node.op, ast.Mod):
                return float(left % right)
            if isinstance(node.op, ast.Pow):
                if abs(right) > MAX_EXPONENT_ABS or (abs(left) > MAX_BASE_FOR_LARGE_EXP and abs(right) > 20):
                    raise ValueError(
                        f"Exponentiation magnitude exceeds safety bounds (base={left}, exp={right})."
                    )
                return float(math.pow(left, right) if left >= 0 or right.is_integer() else (left ** right))
            raise ValueError(f"Unsupported binary operator: {type(node.op).__name__}")

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in SAFE_MATH_FUNCTIONS:
                func_label = ast.unparse(node.func) if hasattr(ast, "unparse") else str(node.func)
                raise ValueError(f"Disallowed function call '{func_label}' in formula.")
            if node.keywords:
                raise ValueError("Keyword arguments are not permitted in formula function calls.")
            args = [DynamicNumericEngine._eval_ast_node(arg, env) for arg in node.args]
            fn = SAFE_MATH_FUNCTIONS[node.func.id]
            if node.func.id == "pow" and len(args) == 2:
                if abs(args[1]) > MAX_EXPONENT_ABS:
                    raise ValueError(f"Exponent {args[1]} exceeds maximum allowed bound ({MAX_EXPONENT_ABS}).")
            if node.func.id == "round" and len(args) == 2:
                return float(round(args[0], int(args[1])))
            return float(fn(*args))

        raise ValueError(f"Disallowed syntax construct '{type(node).__name__}' in mathematical formula.")

    @staticmethod
    def evaluate_formula(
        formula: str,
        variable_values: Dict[str, float],
    ) -> float:
        """Safely evaluate an arithmetic/math formula given variable bindings using a strict AST walker."""
        cleaned_expr = formula.strip()
        if not cleaned_expr:
            raise ValueError("Empty formula expression cannot be evaluated.")
        if len(cleaned_expr) > MAX_FORMULA_LENGTH:
            raise ValueError(f"Formula length ({len(cleaned_expr)}) exceeds limit ({MAX_FORMULA_LENGTH}).")

        # Whitelist allowed characters: alphanumeric, underscore, math ops, parens, dot, comma, spaces
        if not re.match(r"^[0-9a-zA-Z_\s\+\-\*\/\%\^\(\)\.\,]+$", cleaned_expr):
            raise ValueError(f"Formula contains forbidden characters: '{formula}'")

        # Replace ^ with ** for python exponentiation
        py_expr = cleaned_expr.replace("^", "**")

        try:
            tree = ast.parse(py_expr, mode="eval")
            val = DynamicNumericEngine._eval_ast_node(tree, variable_values)
            if math.isnan(val) or math.isinf(val):
                raise ValueError("Formula evaluated to NaN or Infinity.")
            return float(val)
        except Exception as exc:
            raise ValueError(f"Failed to evaluate formula '{formula}': {exc}") from exc

    @staticmethod
    def instantiate_question(
        prompt_template: str,
        numeric_data: NumericalDynamicData,
        seed: Optional[int] = None,
    ) -> DynamicInstantiationResult:
        """Sample variables using `seed`, evaluate formula, and format the question prompt."""
        rng = random.Random(seed) if seed is not None else random.Random()

        sampled_vals: Dict[str, float] = {}
        formatted_vals: Dict[str, str] = {}

        for var_name, var_range in numeric_data.variables.items():
            val = DynamicNumericEngine.sample_variable_value(var_range, rng=rng)
            sampled_vals[var_name] = val
            prec = var_range.precision
            if prec == 0:
                formatted_vals[var_name] = str(int(val))
            else:
                formatted_vals[var_name] = f"{val:.{prec}f}"

        # Calculate formula answer if formula provided
        ans: Optional[float] = None
        ans_formatted = ""
        if numeric_data.formula_expr.strip():
            ans = DynamicNumericEngine.evaluate_formula(
                numeric_data.formula_expr,
                sampled_vals,
            )
            # Pick reasonable precision for answer representation
            ans_formatted = f"{ans:.4g}"

        # Substitute into prompt text
        text = prompt_template
        for var_name, f_val in formatted_vals.items():
            text = text.replace(f"{{{{{var_name}}}}}", f_val)
            text = text.replace(f"{{{var_name}}}", f_val)

        return DynamicInstantiationResult(
            variables=sampled_vals,
            formatted_variables=formatted_vals,
            computed_answer=ans,
            formatted_answer=ans_formatted,
            tolerance=numeric_data.answer_tolerance,
            unit=numeric_data.unit,
            instantiated_text=text,
        )
