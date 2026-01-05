from typing import Dict, Any
from datetime import datetime
from shared.logging_contracts import emit_log

def preview_message(
    snapshot: Dict[str, Any],
    decision_result: Dict[str, Any],
    policy_result: Dict[str, Any]
) -> None:
    """
    DEPRECATED: Message previews are now handled by LLMDecisionArbiter.
    This function is a no-op to prevent duplicate log emission.
    """
    pass
