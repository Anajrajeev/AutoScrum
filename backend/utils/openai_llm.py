"""OpenAI LLM client wrapper for AutoScrum."""

import os
from typing import List, Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv
import hashlib
import json

load_dotenv()


class OpenAILLMClient:
    """
    Wrapper for OpenAI client.

    Provides simplified interface for:
    - Chat completions
    - Streaming responses
    - Function calling
    - Token counting
    """

    def __init__(self):
        """Initialize OpenAI client."""
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4")

        if not self.api_key:
            raise ValueError(
                "Missing required OpenAI configuration. "
                "Please set OPENAI_API_KEY in .env"
            )

        # Initialize OpenAI client
        try:
            import httpx
            # Explicitly create httpx client for timeout handling
            http_client = httpx.Client(timeout=httpx.Timeout(30.0))
            self.client = OpenAI(
                api_key=self.api_key,
                http_client=http_client
            )
        except TypeError as e:
            # If http_client parameter is not accepted, try without it
            if "http_client" in str(e):
                self.client = OpenAI(
                    api_key=self.api_key
                )
            else:
                raise
        except Exception as e:
            # For other errors, try standard initialization
            self.client = OpenAI(
                api_key=self.api_key
            )

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        functions: Optional[List[Dict[str, Any]]] = None,
        function_call: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate chat completion.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            functions: Optional function definitions for function calling (legacy)
            function_call: Optional function call mode (legacy)
            tools: Optional tools definitions (new format)
            tool_choice: Optional tool choice mode ('auto', 'none', or 'required')
            
        Returns:
            Response dictionary with completion and metadata
        """
        try:
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }
            
            if max_tokens:
                kwargs["max_tokens"] = max_tokens
            
            # Use tools (new format) if provided, otherwise fall back to functions (legacy)
            if tools:
                kwargs["tools"] = tools
                if tool_choice:
                    kwargs["tool_choice"] = tool_choice
            elif functions:
                kwargs["functions"] = functions
                if function_call:
                    kwargs["function_call"] = function_call
            
            response = self.client.chat.completions.create(**kwargs)
            
            message = response.choices[0].message
            
            # Handle both new (tool_calls) and legacy (function_call) formats
            tool_calls = getattr(message, "tool_calls", None)
            function_call = getattr(message, "function_call", None)
            
            return {
                "content": message.content,
                "role": message.role,
                "function_call": function_call,  # Legacy format
                "tool_calls": tool_calls,  # New format
                "finish_reason": response.choices[0].finish_reason,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
            }
        except Exception as e:
            raise Exception(f"OpenAI API error: {str(e)}")

    async def chat_completion_async(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        functions: Optional[List[Dict[str, Any]]] = None,
        function_call: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate chat completion asynchronously.
        
        Args:
            messages: List of message dictionaries
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            functions: Optional function definitions
            function_call: Optional function call mode
            
        Returns:
            Response dictionary
        """
        # Note: For true async, use AsyncOpenAI client
        # This is a wrapper for compatibility
        return self.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            functions=functions,
            function_call=function_call
        )

    def generate_text(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Simple text generation from prompt.
        
        Args:
            prompt: User prompt
            system_message: Optional system message
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            
        Returns:
            Generated text
        """
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        
        response = self.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        return response["content"]

    def generate_json_response(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1500
    ) -> Dict[str, Any]:
        """
        Generate JSON response from prompt.
        
        Args:
            prompt: User prompt
            system_message: Optional system message
            temperature: Sampling temperature
            max_tokens: Maximum tokens for response (default 1500 to prevent excessive tokens)
            
        Returns:
            Parsed JSON dictionary
        """
        if not system_message:
            system_message = "You are a helpful assistant that responds in JSON format."
        
        prompt_with_json = f"{prompt}\n\nPlease respond with valid JSON only."
        
        response_text = self.generate_text(
            prompt=prompt_with_json,
            system_message=system_message,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        # Try to extract JSON from code blocks if present
        if "```json" in response_text:
            json_start = response_text.find("```json") + 7
            json_end = response_text.find("```", json_start)
            response_text = response_text[json_start:json_end].strip()
        elif "```" in response_text:
            json_start = response_text.find("```") + 3
            json_end = response_text.find("```", json_start)
            response_text = response_text[json_start:json_end].strip()
        
        try:
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON response: {str(e)}\nResponse: {response_text}")

    def count_tokens(self, text: str) -> int:
        """
        Estimate token count for text.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Estimated token count
        """
        # Rough estimation: 1 token ≈ 4 characters
        # For production, use tiktoken library
        return len(text) // 4

    def create_prompt_hash(self, messages: List[Dict[str, str]]) -> str:
        """
        Create hash of messages for caching.
        
        Args:
            messages: List of message dictionaries
            
        Returns:
            SHA256 hash of messages
        """
        messages_str = json.dumps(messages, sort_keys=True)
        return hashlib.sha256(messages_str.encode()).hexdigest()

    def format_messages(
        self,
        system_prompt: Optional[str],
        user_messages: List[str],
        assistant_messages: Optional[List[str]] = None
    ) -> List[Dict[str, str]]:
        """
        Format messages for chat completion.
        
        Args:
            system_prompt: System message
            user_messages: List of user messages
            assistant_messages: Optional list of assistant messages
            
        Returns:
            Formatted messages list
        """
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # Interleave user and assistant messages
        assistant_messages = assistant_messages or []
        for i, user_msg in enumerate(user_messages):
            messages.append({"role": "user", "content": user_msg})
            if i < len(assistant_messages):
                messages.append({"role": "assistant", "content": assistant_messages[i]})
        
        return messages


# Singleton instance
_llm_client: Optional[OpenAILLMClient] = None


def get_llm_client() -> OpenAILLMClient:
    """
    Get or create OpenAI LLM client singleton.

    Returns:
        OpenAILLMClient instance
    """
    global _llm_client
    if _llm_client is None:
        _llm_client = OpenAILLMClient()
    return _llm_client

