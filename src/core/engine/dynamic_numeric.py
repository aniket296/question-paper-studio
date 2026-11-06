"""Parameterized Math Variable Solver & Range Evaluator for Numerical Dynamic Questions.

Supports:
1. Seeded pseudo-random variable sampling based on min_val, max_val, precision, and step.
2. Safe expression parsing and formula evaluation (arithmetic, powers, standard math functions).
3. Instantiation of concrete question text by replacing {{var}} tokens with sampled numbers.
4. Correct answer calculation with tolerance bounds.
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from src.core.models.question_model import NumericalDynamicData, NumericVariableRange

SAFE_MATH_GLOBALS: Dict[str, Any] = {
    "__builtins__": {},
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
    "pi": math.pi,
    "e": math.e,
}


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
    def evaluate_formula(
        formula: str,
        variable_values: Dict[str, float],
    ) -> float:
        """Safely evaluate an arithmetic/math formula given variable bindings."""
        cleaned_expr = formula.strip()
        if not cleaned_expr:
            raise ValueError("Empty formula expression cannot be evaluated.")

        # Whitelist allowed characters to prevent injection: alphanumeric, underscore, math ops, parens, dot, spaces
        if not re.match(r"^[0-9a-zA-Z_\s\+\-\*\/\%\^\(\)\.\,\:]+$", cleaned_expr):
            raise ValueError(f"Formula contains forbidden characters: '{formula}'")

        # Replace ^ with ** for python exponentiation
        py_expr = cleaned_expr.replace("^", "**")

        scope: Dict[str, Any] = dict(SAFE_MATH_GLOBALS)
        scope.update(variable_values)

        try:
            val = eval(py_expr, scope)  # pylint: disable=eval-used
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
