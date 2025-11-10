"""Base agent class for AutoScrum agents."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
import time
from utils.openai_llm import get_llm_client
from memory.redis_client import get_redis_client
from db.database import get_db
from db.models import AgentLog
from sqlalchemy.orm import Session


class BaseAgent(ABC):
    """
    Abstract base class for all AutoScrum agents.
    
    Provides common functionality:
    - LLM client access
    - Redis memory access
    - Database logging
    - Error handling
    - State management
    """

    def __init__(self, agent_name: str):
        """
        Initialize base agent.
        
        Args:
            agent_name: Unique name for the agent
        """
        self.agent_name = agent_name
        self.llm_client = get_llm_client()
        self.redis_client = get_redis_client()

    @abstractmethod
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute agent logic.
        
        Args:
            input_data: Input data dictionary
            
        Returns:
            Output data dictionary
        """
        pass

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run agent with logging and error handling.
        
        Args:
            input_data: Input data dictionary
            
        Returns:
            Output data dictionary
        """
        start_time = time.time()
        status = "success"
        error_message = None
        output_data = {}

        try:
            # Execute agent logic
            output_data = await self.execute(input_data)
        except Exception as e:
            status = "failure"
            error_message = str(e)
            output_data = {"error": error_message}
            raise
        finally:
            # Log execution
            execution_time = time.time() - start_time
            await self._log_execution(
                action="execute",
                input_data=input_data,
                output_data=output_data,
                execution_time=execution_time,
                status=status,
                error_message=error_message
            )

        return output_data

    async def _log_execution(
        self,
        action: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        execution_time: float,
        status: str,
        error_message: Optional[str] = None
    ) -> None:
        """
        Log agent execution to database.
        
        Args:
            action: Action performed
            input_data: Input data
            output_data: Output data
            execution_time: Execution time in seconds
            status: Status (success/failure)
            error_message: Error message if failed
        """
        try:
            db = next(get_db())
            log = AgentLog(
                agent_name=self.agent_name,
                action=action,
                input_data=input_data,
                output_data=output_data,
                execution_time=execution_time,
                status=status,
                error_message=error_message
            )
            db.add(log)
            db.commit()
        except Exception as e:
            print(f"Failed to log agent execution: {str(e)}")

    def get_state(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get agent state from Redis.
        
        Args:
            agent_id: Unique agent instance ID
            
        Returns:
            Agent state dictionary or None
        """
        return self.redis_client.get_agent_state(self.agent_name, agent_id)

    def set_state(self, agent_id: str, state: Dict[str, Any]) -> bool:
        """
        Set agent state in Redis.
        
        Args:
            agent_id: Unique agent instance ID
            state: State dictionary
            
        Returns:
            True if successful
        """
        return self.redis_client.set_agent_state(self.agent_name, agent_id, state)

    def generate_llm_response(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.7
    ) -> str:
        """
        Generate LLM response.
        
        Args:
            prompt: User prompt
            system_message: System message
            temperature: Sampling temperature
            
        Returns:
            Generated text
        """
        return self.llm_client.generate_text(
            prompt=prompt,
            system_message=system_message,
            temperature=temperature
        )

    def generate_json_response(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """
        Generate JSON response from LLM.
        
        Args:
            prompt: User prompt
            system_message: System message
            temperature: Sampling temperature
            
        Returns:
            Parsed JSON dictionary
        """
        return self.llm_client.generate_json_response(
            prompt=prompt,
            system_message=system_message,
            temperature=temperature
        )

