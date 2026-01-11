"""
Validation for human-in-loop review inputs.

Ensures that justifications and reviews are meaningful,
not just rubber-stamping.
"""

import re
from typing import Optional


class ValidationError(Exception):
    """Raised when validation fails."""

    pass


# Common garbage inputs that indicate rubber-stamping
GARBAGE_INPUTS = {
    "ok",
    "fine",
    "approved",
    "yes",
    "no",
    ".",
    "..",
    "...",
    "x",
    "xx",
    "xxx",
    "asdf",
    "123",
    "test",
    "testing",
    "aaa",
    "bbb",
    "foo",
    "bar",
    "qwerty",
    "admin",
    "godkänd",
    "ja",
    "nej",
    "ok!",
    "done",
    "klar",
    "checked",
    "reviewed",
    "confirm",
}

# Swedish error messages
ERROR_MESSAGES = {
    "too_short": "Motiveringen är för kort. Minst 10 tecken krävs.",
    "garbage": "Ange en faktisk motivering, inte bara '{input}'.",
    "repetitive": "Motiveringen verkar vara repetitiv text.",
    "no_content": "Motiveringen saknar meningsfullt innehåll.",
}


def validate_justification(
    justification: str,
    min_length: int = 10,
    language: str = "sv",
) -> tuple[bool, Optional[str]]:
    """
    Validate that a justification is meaningful.

    Checks for:
    - Minimum length
    - Garbage/placeholder inputs
    - Repetitive text
    - Actual content

    Args:
        justification: The justification text to validate
        min_length: Minimum required length
        language: Language for error messages ('sv' or 'en')

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Strip and normalize
    text = justification.strip()

    # Check minimum length
    if len(text) < min_length:
        return False, ERROR_MESSAGES["too_short"]

    # Check for garbage inputs
    normalized = text.lower().strip()
    if normalized in GARBAGE_INPUTS:
        return False, ERROR_MESSAGES["garbage"].format(input=text)

    # Check for repetitive text (same character repeated)
    if len(set(normalized.replace(" ", ""))) < 3:
        return False, ERROR_MESSAGES["repetitive"]

    # Check for actual words (at least 2 words with 3+ chars)
    words = [w for w in text.split() if len(w) >= 3]
    if len(words) < 2:
        return False, ERROR_MESSAGES["no_content"]

    # Check for keyboard patterns
    keyboard_patterns = [
        r"^[asdfghjkl]+$",
        r"^[qwertyuiop]+$",
        r"^[zxcvbnm]+$",
        r"^[0-9]+$",
    ]
    for pattern in keyboard_patterns:
        if re.match(pattern, normalized.replace(" ", ""), re.IGNORECASE):
            return False, ERROR_MESSAGES["garbage"].format(input=text)

    return True, None


def validate_review_duration(
    duration_seconds: float,
    min_seconds: float = 2.0,
) -> tuple[bool, Optional[str]]:
    """
    Validate that a review took a reasonable amount of time.

    Reviews that are too fast are likely rubber-stamps.

    Args:
        duration_seconds: How long the review took
        min_seconds: Minimum acceptable duration

    Returns:
        Tuple of (is_valid, warning_message)
    """
    if duration_seconds < min_seconds:
        return False, f"Granskning tog endast {duration_seconds:.1f}s. Minst {min_seconds}s förväntas."

    return True, None


def is_rubber_stamp(
    duration_seconds: float,
    justification: Optional[str] = None,
    min_duration: float = 2.0,
) -> bool:
    """
    Check if a review appears to be a rubber-stamp.

    A rubber-stamp is when someone approves without actually reviewing.
    Indicators:
    - Very fast review (<2 seconds)
    - Generic/garbage justification
    - Pattern of approving everything

    Args:
        duration_seconds: How long the review took
        justification: Optional justification text
        min_duration: Minimum expected duration

    Returns:
        True if appears to be a rubber-stamp
    """
    # Too fast is definitely suspicious
    if duration_seconds < min_duration:
        return True

    # If there's a justification, check if it's garbage
    if justification:
        is_valid, _ = validate_justification(justification)
        if not is_valid:
            return True

    return False
