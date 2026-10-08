"""Structure checks computed from saved cells only (the notebook is never run)."""
from __future__ import annotations

from .models import Cell, Checks, ExecutionOrder


def _has_content(cell: Cell) -> bool:
    return bool(cell.source.strip())


def is_empty(cells: list[Cell]) -> bool:
    """True when there is no code and no Markdown with content."""
    return not any(c.cell_type in ("code", "markdown") and _has_content(c) for c in cells)


def execution_order(cells: list[Cell]) -> ExecutionOrder:
    """Judge run order from saved execution counts.

    - out_of_order_cells: executed cells whose count is not above the previous
      executed cell's count (the point where the order breaks).
    - skipped: a non-empty code cell was never run although a later one was.
      Gaps in the numbers (re-runs) are normal and are not flagged.
    """
    code = [c for c in cells if c.cell_type == "code" and _has_content(c)]
    executed = [c for c in code if c.execution_count is not None]

    out_of_order: list[int] = []
    prev = None
    for c in executed:
        if prev is not None and c.execution_count <= prev:
            out_of_order.append(c.index)
        prev = c.execution_count

    last_executed_pos = max((i for i, c in enumerate(code) if c.execution_count is not None), default=-1)
    skipped = last_executed_pos >= 0 and any(c.execution_count is None for c in code[:last_executed_pos])

    return ExecutionOrder(
        strictly_increasing=not out_of_order,
        skipped=skipped,
        out_of_order_cells=out_of_order,
    )


def compute_checks(cells: list[Cell]) -> Checks:
    code = [c for c in cells if c.cell_type == "code" and _has_content(c)]
    return Checks(
        empty=is_empty(cells),
        execution_order=execution_order(cells),
        error_cells=[c.index for c in cells if c.has_error],
        unexecuted_code_cells=[c.index for c in code if c.execution_count is None],
    )
