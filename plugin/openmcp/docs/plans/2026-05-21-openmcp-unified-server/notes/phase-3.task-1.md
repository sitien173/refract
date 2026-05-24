# phase-3.task-1

## Decisions made (not in spec)
- Kept signature assertion strict on parameter order by comparing `inspect.signature(run).parameters.keys()` against the required list.

## Spec deviations
- none

## Tradeoffs accepted
- Import smoke test validates module importability only; behavior validation is covered by later tests.

## Assumptions
- FastMCP tool decorator does not alter Python function signature ordering.

## Follow-ups for human
- none
