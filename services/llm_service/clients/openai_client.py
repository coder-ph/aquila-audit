"""
OpenAI client with retry logic and fallback mechanisms.
"""
import openai
from typing import Dict, List, Any, Optional, Tuple
import tiktoken
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import time

from shared.utils.logging import logger
from services.llm_service.config import config
from services.llm_service.budget.cost_tracker import cost_tracker


class OpenAIClient:
    """OpenAI API client with enhanced error handling and cost tracking."""
    
    def __init__(self):
        self.api_key = config.openai_api_key
        self.organization = config.openai_organization
        self.base_url = config.openai_base_url
        self.default_model = config.default_model
        self.fallback_model = config.fallback_model
        self.max_tokens = config.max_tokens
        self.temperature = config.temperature
        self.timeout = config.timeout
        
        # Initialize OpenAI client
        self.client = openai.OpenAI(
            api_key=self.api_key,
            organization=self.organization,
            base_url=self.base_url,
            timeout=self.timeout
        )
        
        # Initialize tokenizer for cost estimation
        try:
            self.tokenizer = tiktoken.encoding_for_model(self.default_model)
        except:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
        # Model pricing (per 1K tokens)
        self.pricing = {
            "gpt-4": {"input": 0.03, "output": 0.06},
            "gpt-4-32k": {"input": 0.06, "output": 0.12},
            "gpt-3.5-turbo": {"input": 0.0015, "output": 0.002},
            "gpt-3.5-turbo-16k": {"input": 0.003, "output": 0.004},
        }
        
        self.is_healthy = False
        self.last_health_check = None
        
    def get_status(self) -> Dict[str, Any]:
        """Get client status."""
        return {
            "is_healthy": self.is_healthy,
            "last_health_check": self.last_health_check,
            "default_model": self.default_model,
            "fallback_model": self.fallback_model
        }
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((
            openai.APIConnectionError,
            openai.APITimeoutError,
            openai.RateLimitError
        ))
    )
    def check_health(self) -> bool:
        """Check if OpenAI API is accessible."""
        try:
            # Simple completion to test connectivity
            response = self.client.chat.completions.create(
                model=self.fallback_model,  # Use cheaper model for health check
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=5
            )
            
            self.is_healthy = True
            self.last_health_check = time.time()
            return True
            
        except Exception as e:
            logger.error(f"OpenAI health check failed: {str(e)}")
            self.is_healthy = False
            return False
    
    def estimate_cost(self, messages: List[Dict[str, str]], model: str = None) -> float:
        """
        Estimate cost for a completion.
        
        Args:
            messages: List of messages
            model: Model to use for estimation
        
        Returns:
            Estimated cost in USD
        """
        if model is None:
            model = self.default_model
        
        if model not in self.pricing:
            logger.warning(f"Unknown pricing for model: {model}")
            return 0.0
        
        # Count tokens
        total_tokens = 0
        for message in messages:
            content = message.get("content", "")
            total_tokens += len(self.tokenizer.encode(content))
        
        # Estimate output tokens (assume similar length to input)
        estimated_output_tokens = min(total_tokens * 1.5, self.max_tokens)
        
        # Calculate cost
        input_cost = (total_tokens / 1000) * self.pricing[model]["input"]
        output_cost = (estimated_output_tokens / 1000) * self.pricing[model]["output"]
        
        return input_cost + output_cost
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((
            openai.APIConnectionError,
            openai.APITimeoutError,
            openai.RateLimitError
        ))
    )
    def create_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = None,
        max_tokens: int = None,
        tenant_id: str = None,
        user_id: str = None
    ) -> Dict[str, Any]:
        """
        Create chat completion with cost tracking.
        
        Args:
            messages: List of messages
            model: Model to use
            temperature: Temperature for generation
            max_tokens: Maximum tokens to generate
            tenant_id: Tenant ID for cost tracking
            user_id: User ID for cost tracking
        
        Returns:
            Completion response with metadata
        """
        if model is None:
            model = self.default_model
        
        if temperature is None:
            temperature = self.temperature
        
        if max_tokens is None:
            max_tokens = self.max_tokens
        
        # Estimate cost before making request
        estimated_cost = self.estimate_cost(messages, model)
        
        # Check budget before proceeding
        if tenant_id:
            can_proceed, message = cost_tracker.can_make_request(tenant_id, estimated_cost)
            if not can_proceed:
                raise ValueError(f"Budget exceeded: {message}")
        
        try:
            # Make API call
            start_time = time.time()
            
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            end_time = time.time()
            
            # Calculate actual cost
            usage = response.usage
            actual_cost = self._calculate_actual_cost(usage, model)
            
            # Track cost
            if tenant_id:
                cost_tracker.track_cost(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    model=model,
                    input_tokens=usage.prompt_tokens,
                    output_tokens=usage.completion_tokens,
                    cost=actual_cost
                )
            
            # Build response
            result = {
                "success": True,
                "model": model,
                "content": response.choices[0].message.content,
                "finish_reason": response.choices[0].finish_reason,
                "usage": {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens
                },
                "cost": {
                    "estimated": estimated_cost,
                    "actual": actual_cost,
                    "currency": "USD"
                },
                "performance": {
                    "response_time": end_time - start_time
                },
                "metadata": {
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "timestamp": time.time()
                }
            }
            
            logger.info(
                f"OpenAI completion successful: {model}, "
                f"tokens: {usage.total_tokens}, cost: ${actual_cost:.6f}",
                tenant_id=tenant_id
            )
            
            return result
            
        except openai.RateLimitError as e:
            logger.error(f"OpenAI rate limit exceeded: {str(e)}", tenant_id=tenant_id)
            raise
            
        except openai.APIConnectionError as e:
            logger.error(f"OpenAI connection error: {str(e)}", tenant_id=tenant_id)
            raise
            
        except openai.APITimeoutError as e:
            logger.error(f"OpenAI timeout: {str(e)}", tenant_id=tenant_id)
            raise
            
        except openai.AuthenticationError as e:
            logger.error(f"OpenAI authentication error: {str(e)}")
            raise ValueError("Invalid OpenAI API key")
            
        except Exception as e:
            logger.error(f"OpenAI error: {str(e)}", tenant_id=tenant_id)
            raise
    
    def create_completion_with_fallback(
        self,
        messages: List[Dict[str, str]],
        primary_model: str = None,
        fallback_model: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create completion with automatic fallback.
        
        Args:
            messages: List of messages
            primary_model: Primary model to try
            fallback_model: Fallback model if primary fails
        
        Returns:
            Completion response
        """
        if primary_model is None:
            primary_model = self.default_model
        
        if fallback_model is None:
            fallback_model = self.fallback_model
        
        try:
            # Try primary model
            return self.create_completion(messages, model=primary_model, **kwargs)
            
        except (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError) as e:
            logger.warning(
                f"Primary model {primary_model} failed, trying fallback {fallback_model}: {str(e)}",
                tenant_id=kwargs.get('tenant_id')
            )
            
            # Try fallback model
            try:
                return self.create_completion(messages, model=fallback_model, **kwargs)
            except Exception as fallback_error:
                logger.error(
                    f"Fallback model also failed: {str(fallback_error)}",
                    tenant_id=kwargs.get('tenant_id')
                )
                raise fallback_error
    
    def _calculate_actual_cost(self, usage, model: str) -> float:
        """Calculate actual cost based on usage."""
        if model not in self.pricing:
            return 0.0
        
        input_cost = (usage.prompt_tokens / 1000) * self.pricing[model]["input"]
        output_cost = (usage.completion_tokens / 1000) * self.pricing[model]["output"]
        
        return input_cost + output_cost
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self.tokenizer.encode(text))
    
    def truncate_to_token_limit(
        self,
        text: str,
        max_tokens: int,
        model: str = None
    ) -> str:
        """
        Truncate text to token limit.
        
        Args:
            text: Text to truncate
            max_tokens: Maximum tokens
            model: Model for tokenization
        
        Returns:
            Truncated text
        """
        tokens = self.tokenizer.encode(text)
        if len(tokens) <= max_tokens:
            return text
        
        truncated_tokens = tokens[:max_tokens]
        return self.tokenizer.decode(truncated_tokens)


# Global OpenAI client instance
openai_client = OpenAIClient()