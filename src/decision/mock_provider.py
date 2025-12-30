import json
import logging
from typing import Optional

logger = logging.getLogger("MockLLMProvider")

class MockLLMProvider:
    """
    Deterministic mock provider for testing and fallback.
    """
    def __init__(self, model: str = "gpt-mock"):
        self.model = model

    def generate(self, system_prompt: str, user_prompt: str = "") -> str:
        """
        Generates a deterministic JSON response based on prompt keywords.
        """
        prompt_lower = (system_prompt + " " + user_prompt).lower()
        
        # Trigger: Critical
        if "major fall" in prompt_lower or "unconscious" in prompt_lower:
            return json.dumps({
                "recommendation": "NOTIFY_CAREGIVER",
                "risk_level": "critical",
                "confidence": 0.95,
                "reasoning": "Mock critical fall detected (provider).",
                "uncertainty_flags": [],
                "notes": "Simulated critical response."
            })
            
        # Trigger: Recovering
        if "recovering" in prompt_lower:
            return json.dumps({
                "recommendation": "MONITOR",
                "risk_level": "medium",
                "confidence": 0.8,
                "reasoning": "Mock recovery detected (provider).",
                "uncertainty_flags": [],
                "notes": "Simulated monitor response."
            })
            
        # Default: Ambiguous
        return json.dumps({
            "recommendation": "REQUEST_CONFIRMATION",
            "risk_level": "low",
            "confidence": 0.6,
            "reasoning": "Mock ambiguous situation (provider).",
            "uncertainty_flags": ["ambiguous_posture"],
            "notes": "Default mock response."
        })
