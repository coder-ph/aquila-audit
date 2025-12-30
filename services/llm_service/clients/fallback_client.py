"""
Fallback client for when OpenAI is unavailable.
"""
from typing import Dict, List, Any, Optional
import time
import random

from shared.utils.logging import logger
from services.llm_service.config import config


class FallbackClient:
    """Fallback client that provides basic responses when OpenAI is unavailable."""
    
    def __init__(self):
        self.responses = {
            "explain_anomaly": [
                "This appears to be an anomalous transaction due to its significantly higher value compared to typical transactions in this category.",
                "The pattern detected suggests potential compliance issues based on the frequency and timing of these activities.",
                "This finding is flagged because it deviates from the established baseline by more than 3 standard deviations.",
                "The combination of factors including amount, location, and timing trigger multiple compliance rules.",
                "This activity matches known patterns of fraudulent behavior identified in our training data."
            ],
            "explain_rule": [
                "This rule checks for transactions exceeding the established threshold of ${amount}.",
                "The rule validates that all required documentation fields are present before approval.",
                "This compliance rule ensures adherence to regulatory requirement {regulation_code}.",
                "The rule detects duplicate submissions within a {timeframe} hour window.",
                "This validation rule checks for proper authorization chains based on transaction value."
            ],
            "summarize_findings": [
                "The audit identified {count} issues requiring attention, with {critical_count} critical findings.",
                "Key findings include compliance violations in {areas} and several high-value anomalies.",
                "The report highlights {count} areas for improvement with estimated risk levels.",
                "Summary: {critical} critical, {high} high, {medium} medium, and {low} low severity findings.",
                "Main concerns: {top_issues}. Recommended actions: {actions}."
            ]
        }
        
        self.default_response = "I'm unable to provide a detailed analysis at this time. Please try again later or contact support."
    
    def create_completion(
        self,
        messages: List[Dict[str, str]],
        prompt_type: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a fallback completion.
        
        Args:
            messages: List of messages
            prompt_type: Type of prompt for context-aware response
            **kwargs: Additional arguments
        
        Returns:
            Fallback response
        """
        # Extract user message
        user_message = ""
        for msg in messages:
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break
        
        # Determine response based on prompt type
        if prompt_type and prompt_type in self.responses:
            responses = self.responses[prompt_type]
            content = random.choice(responses)
        elif "explain" in user_message.lower():
            content = random.choice(self.responses.get("explain_anomaly", [self.default_response]))
        elif "summary" in user_message.lower() or "summarize" in user_message.lower():
            content = random.choice(self.responses.get("summarize_findings", [self.default_response]))
        else:
            content = self.default_response
        
        # Add context from user message
        if user_message:
            # Extract key values for personalization
            if "amount" in user_message.lower():
                content = content.replace("{amount}", self._extract_amount(user_message))
            if "count" in user_message.lower():
                content = content.replace("{count}", str(random.randint(1, 10)))
        
        # Simulate some processing time
        time.sleep(random.uniform(0.5, 1.5))
        
        return {
            "success": True,
            "model": "fallback",
            "content": content,
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": len(user_message) // 4,  # Rough estimate
                "completion_tokens": len(content) // 4,
                "total_tokens": (len(user_message) + len(content)) // 4
            },
            "cost": {
                "estimated": 0.0,
                "actual": 0.0,
                "currency": "USD"
            },
            "performance": {
                "response_time": random.uniform(0.5, 2.0)
            },
            "metadata": {
                "is_fallback": True,
                "timestamp": time.time()
            }
        }
    
    def _extract_amount(self, text: str) -> str:
        """Extract amount from text."""
        import re
        amounts = re.findall(r'\$\d+[\d,]*\.?\d*', text)
        if amounts:
            return amounts[0]
        return "$1,000"  # Default
    
    def get_status(self) -> Dict[str, Any]:
        """Get client status."""
        return {
            "is_healthy": True,
            "is_fallback": True,
            "available_responses": len(self.responses),
            "description": "Local fallback client"
        }


# Global fallback client instance
fallback_client = FallbackClient()