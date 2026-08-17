from app.models import Generation, GenerationAttempt, GenerationAttemptStatus, GenerationStatus

GENERATION_TERMINAL = {
    GenerationStatus.SUCCEEDED.value,
    GenerationStatus.FAILED.value,
    GenerationStatus.TIMED_OUT.value,
    GenerationStatus.CANCELED.value,
}
ATTEMPT_TERMINAL = {
    GenerationAttemptStatus.SUCCEEDED.value,
    GenerationAttemptStatus.FAILED.value,
    GenerationAttemptStatus.TIMED_OUT.value,
    GenerationAttemptStatus.CANCELED.value,
    GenerationAttemptStatus.SUBMISSION_UNKNOWN.value,
}

GENERATION_TRANSITIONS = {
    GenerationStatus.CREATED.value: {
        GenerationStatus.QUEUED.value,
        GenerationStatus.CANCEL_REQUESTED.value,
        GenerationStatus.CANCELED.value,
        GenerationStatus.FAILED.value,
    },
    GenerationStatus.QUEUED.value: {
        GenerationStatus.RUNNING.value,
        GenerationStatus.CANCEL_REQUESTED.value,
        GenerationStatus.SUCCEEDED.value,
        GenerationStatus.FAILED.value,
        GenerationStatus.TIMED_OUT.value,
        GenerationStatus.CANCELED.value,
    },
    GenerationStatus.RUNNING.value: {
        GenerationStatus.CANCEL_REQUESTED.value,
        GenerationStatus.SUCCEEDED.value,
        GenerationStatus.FAILED.value,
        GenerationStatus.TIMED_OUT.value,
        GenerationStatus.CANCELED.value,
    },
    GenerationStatus.CANCEL_REQUESTED.value: {
        GenerationStatus.SUCCEEDED.value,
        GenerationStatus.FAILED.value,
        GenerationStatus.TIMED_OUT.value,
        GenerationStatus.CANCELED.value,
    },
    GenerationStatus.FAILED.value: {
        GenerationStatus.CREATED.value,
    },
    GenerationStatus.TIMED_OUT.value: {
        GenerationStatus.CREATED.value,
    },
}


ATTEMPT_TRANSITIONS = {
    GenerationAttemptStatus.PENDING.value: {
        GenerationAttemptStatus.SUBMITTING.value,
        GenerationAttemptStatus.CANCELED.value,
    },
    GenerationAttemptStatus.SUBMITTING.value: {
        GenerationAttemptStatus.QUEUED.value,
        GenerationAttemptStatus.CANCEL_REQUESTED.value,
        GenerationAttemptStatus.FAILED.value,
        GenerationAttemptStatus.SUBMISSION_UNKNOWN.value,
    },
    GenerationAttemptStatus.QUEUED.value: {
        GenerationAttemptStatus.RUNNING.value,
        GenerationAttemptStatus.CANCEL_REQUESTED.value,
        GenerationAttemptStatus.SUCCEEDED.value,
        GenerationAttemptStatus.FAILED.value,
        GenerationAttemptStatus.TIMED_OUT.value,
        GenerationAttemptStatus.CANCELED.value,
    },
    GenerationAttemptStatus.RUNNING.value: {
        GenerationAttemptStatus.CANCEL_REQUESTED.value,
        GenerationAttemptStatus.SUCCEEDED.value,
        GenerationAttemptStatus.FAILED.value,
        GenerationAttemptStatus.TIMED_OUT.value,
        GenerationAttemptStatus.CANCELED.value,
    },
    GenerationAttemptStatus.CANCEL_REQUESTED.value: {
        GenerationAttemptStatus.SUCCEEDED.value,
        GenerationAttemptStatus.FAILED.value,
        GenerationAttemptStatus.TIMED_OUT.value,
        GenerationAttemptStatus.CANCELED.value,
    },
}


class InvalidGenerationTransition(ValueError):
    pass


def _transition(current: str, target: str, allowed: dict[str, set[str]]) -> str:
    if current == target:
        return target
    if target not in allowed.get(current, set()):
        raise InvalidGenerationTransition(f"Invalid transition: {current} -> {target}")
    return target


def transition_generation(generation: Generation, target: str) -> None:
    generation.status = _transition(generation.status, target, GENERATION_TRANSITIONS)


def transition_attempt(attempt: GenerationAttempt, target: str) -> None:
    attempt.status = _transition(attempt.status, target, ATTEMPT_TRANSITIONS)
