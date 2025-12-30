import logging
import os
from typing import Optional

try:
    from openai import OpenAI, APIError, RateLimitError
except ImportError:
    OpenAI = None
    APIError = None
    RateLimitError = None

logger = logging.getLogger("RealOpenAIProvider")

class RealOpenAIProvider:
    """
    Encapsulates interactions with the OpenAI SDK.
    """
    def __init__(self, api_key: str, model: str = "gpt-5-mini"):
        if not OpenAI:
            logger.error("OpenAI SDK not installed. Please install 'openai'.")
            self.client = None
        else:
            self.client = OpenAI(api_key=api_key)
        
        self.model = model

    def generate(self, system_prompt: str, user_prompt: str = "") -> Optional[str]:
        """
        Generates a JSON response from the LLM.
        """
        if not self.client:
            logger.error("Client not initialized (missing SDK?).")
            return None

        try:
            # Construct messages. If user_prompt is empty, we assume system_prompt contains everything
            # or we just send it as system. Ideally, we separate instructions (System) from data (User).
            messages = [{"role": "system", "content": system_prompt}]
            if user_prompt:
                messages.append({"role": "user", "content": user_prompt})

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"}
            )
            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"OpenAI API Call Failed: {e}")
            return None
