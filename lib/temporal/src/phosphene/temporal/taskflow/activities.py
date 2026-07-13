"""TaskFlow step dispatcher Activity.

The generic dispatcher receives a ``StepInput`` and executes based on
``kind``. In the base form, ``_execute_step`` raises
``NotImplementedError`` — subclasses or activity-class overrides provide
the actual execution strategy (e.g. spawning a subagent, calling an API).

Heartbeats are sent during execution so Temporal knows the Activity is
alive. The heartbeat note appears in the Temporal UI — this replaces
``note_progress()`` from the file-based TaskFlow.
"""

from __future__ import annotations

from temporalio import activity

from phosphene.temporal.taskflow.models import StepInput, StepOutput


@activity.defn
async def dispatch_step_activity(step: StepInput) -> StepOutput:
    """Execute a single TaskFlow step.

    Sends heartbeats at start and completion. The default execution
    strategy raises ``NotImplementedError`` — override ``_execute_step``
    or use a TaskFlowActivities subclass for real execution.

    Args:
        step: The step specification to execute.

    Returns:
        ``StepOutput`` with success/failure and output text.
    """
    activity.heartbeat(f"Starting: {step.title}")
    try:
        result = await _execute_step(step)
        activity.heartbeat(f"Complete: {step.title}")
        return StepOutput(
            index=step.index,
            succeeded=True,
            output=result,
        )
    except Exception as exc:
        return StepOutput(
            index=step.index,
            succeeded=False,
            error=str(exc),
        )


async def _execute_step(step: StepInput) -> str:
    """Default step execution — override in subclass for custom behaviour.

    Args:
        step: The step to execute.

    Raises:
        NotImplementedError: Always — this is the override point.

    Returns:
        Result string (when overridden).
    """
    raise NotImplementedError(
        f"No executor registered for kind={step.kind!r}. "
        "Override _execute_step or use a TaskFlowActivities subclass."
    )
