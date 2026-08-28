"""ReproEval-specific exceptions."""


class EvaluationInputError(ValueError):
    """Raised when an evaluation case or referenced file is unsafe or invalid."""
