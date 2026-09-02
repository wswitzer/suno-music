from __future__ import annotations

from collections import defaultdict

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from .models import (
    AssignmentConstraints,
    AssignmentRecord,
    CompatibilityScore,
    SourceUnit,
    StyleRecord,
)


class AssignmentError(RuntimeError):
    """Raised when the global assignment is invalid or infeasible."""


def optimize_assignments(
    lessons: list[SourceUnit],
    styles: list[StyleRecord],
    scores: list[CompatibilityScore],
    constraints: AssignmentConstraints,
    *,
    assignment_version: str = "scipy-milp-0.1.0",
) -> list[AssignmentRecord]:
    if not lessons or not styles:
        raise AssignmentError("At least one source unit and style are required")

    units = sorted(lessons, key=lambda item: (item.language, item.sequence_index, item.unit_ref))
    style_by_id = {style.style_id: style for style in styles}
    if len(style_by_id) != len(styles):
        raise AssignmentError("Duplicate style_id values are not allowed")

    required = len(units)
    minimum_capacity = len(styles) * constraints.minimum_style_usage
    maximum_capacity = len(styles) * constraints.maximum_style_usage
    if not minimum_capacity <= required <= maximum_capacity:
        raise AssignmentError(
            "Style usage constraints are infeasible: "
            f"{required} source units require capacity in "
            f"[{minimum_capacity}, {maximum_capacity}]"
        )

    score_map = {
        (score.unit_ref, score.language, score.style_id): score.total for score in scores
    }
    unknown_styles = {score.style_id for score in scores} - set(style_by_id)
    if unknown_styles:
        raise AssignmentError(f"Scores reference unknown styles: {sorted(unknown_styles)}")

    unit_count = len(units)
    style_count = len(styles)
    variable_count = unit_count * style_count

    def variable_index(unit_index: int, style_index: int) -> int:
        return unit_index * style_count + style_index

    objective = np.zeros(variable_count, dtype=float)
    for ui, unit in enumerate(units):
        for si, style in enumerate(styles):
            key = (unit.unit_ref, unit.language, style.style_id)
            if key not in score_map and constraints.missing_score_policy == "error":
                raise AssignmentError(
                    "Missing compatibility score for "
                    f"unit={unit.unit_ref}/{unit.language}, style={style.style_id}"
                )
            objective[variable_index(ui, si)] = -score_map.get(key, 0.0)

    rows: list[tuple[dict[int, float], float, float]] = []

    for ui in range(unit_count):
        rows.append(({variable_index(ui, si): 1.0 for si in range(style_count)}, 1.0, 1.0))

    for si in range(style_count):
        rows.append(
            (
                {variable_index(ui, si): 1.0 for ui in range(unit_count)},
                float(constraints.minimum_style_usage),
                float(constraints.maximum_style_usage),
            )
        )

    if constraints.minimum_exact_style_gap > 0:
        for left in range(unit_count):
            for right in range(left + 1, unit_count):
                if units[left].language != units[right].language:
                    continue
                distance = units[right].sequence_index - units[left].sequence_index
                if distance >= constraints.minimum_exact_style_gap:
                    break
                for si in range(style_count):
                    rows.append(
                        (
                            {
                                variable_index(left, si): 1.0,
                                variable_index(right, si): 1.0,
                            },
                            -np.inf,
                            1.0,
                        )
                    )

    bucket_to_style_indexes: dict[str, list[int]] = defaultdict(list)
    for si, style in enumerate(styles):
        bucket_to_style_indexes[style.primary_bucket].append(si)

    run_limit = constraints.maximum_consecutive_primary_bucket
    window_size = run_limit + 1
    for start in range(unit_count - window_size + 1):
        window = units[start : start + window_size]
        if len({unit.language for unit in window}) != 1:
            continue
        indexes = [unit.sequence_index for unit in window]
        if indexes != list(range(indexes[0], indexes[0] + window_size)):
            continue
        for style_indexes in bucket_to_style_indexes.values():
            rows.append(
                (
                    {
                        variable_index(ui, si): 1.0
                        for ui in range(start, start + window_size)
                        for si in style_indexes
                    },
                    -np.inf,
                    float(run_limit),
                )
            )

    matrix = lil_matrix((len(rows), variable_count), dtype=float)
    lower = np.empty(len(rows), dtype=float)
    upper = np.empty(len(rows), dtype=float)
    for row_index, (coefficients, low, high) in enumerate(rows):
        for column, coefficient in coefficients.items():
            matrix[row_index, column] = coefficient
        lower[row_index] = low
        upper[row_index] = high

    result = milp(
        c=objective,
        integrality=np.ones(variable_count, dtype=int),
        bounds=Bounds(np.zeros(variable_count), np.ones(variable_count)),
        constraints=LinearConstraint(matrix.tocsr(), lower, upper),
        options={"presolve": True},
    )
    if not result.success or result.x is None:
        raise AssignmentError(
            f"No feasible global assignment found: {result.message}. "
            "Relax an explicit constraint or inspect pool/bucket balance."
        )

    assignments: list[AssignmentRecord] = []
    solution = result.x.reshape((unit_count, style_count))
    for ui, unit in enumerate(units):
        selected = np.flatnonzero(solution[ui] > 0.5)
        if len(selected) != 1:
            raise AssignmentError(
                f"Solver returned {len(selected)} styles for unit {unit.unit_ref}"
            )
        style = styles[int(selected[0])]
        assignments.append(
            AssignmentRecord(
                unit_ref=unit.unit_ref,
                sequence_index=unit.sequence_index,
                lesson_number=unit.lesson_number,
                language=unit.language,
                style_id=style.style_id,
                primary_bucket=style.primary_bucket,
                fit_score=float(score_map.get((unit.unit_ref, unit.language, style.style_id), 0.0)),
                assignment_version=assignment_version,
            )
        )

    return assignments
