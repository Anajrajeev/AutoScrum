"""Redis client for context memory and agent state management."""

import redis
import json
import os
import logging
from typing import Optional, Dict, Any, List
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class RedisClient:
    """
    Redis client wrapper for AutoScrum context management.
    
    Handles:
    - Feature clarification context
    - Agent conversation state
    - Orchestration graph metadata
    - Temporary reasoning tokens
    """

    def __init__(self):
        """Initialize Redis connection."""
        self.host = os.getenv("REDIS_HOST", "localhost")
        self.port = int(os.getenv("REDIS_PORT", "6379"))
        self.db = int(os.getenv("REDIS_DB", "0"))
        self.password = os.getenv("REDIS_PASSWORD", None)
        
        self.client = redis.Redis(
            host=self.host,
            port=self.port,
            db=self.db,
            password=self.password,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
        
        # Test connection - Redis is now mandatory
        try:
            self.client.ping()
            logger.info(f"Redis connected successfully at {self.host}:{self.port}")
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.error(f"Failed to connect to Redis at {self.host}:{self.port}: {e}")
            raise ConnectionError(
                f"Failed to connect to Redis at {self.host}:{self.port}. "
                "Please ensure Redis is running (e.g., 'sudo service redis-server start' in WSL2)."
            ) from e

    # ========================================================================
    # Feature Context Management
    # ========================================================================

    def set_feature_context(
        self,
        feature_id: int,
        context: Dict[str, Any],
        ttl: int = 3600
    ) -> bool:
        """
        Store feature clarification context.
        
        Args:
            feature_id: Unique feature identifier
            context: Context dictionary to store
            ttl: Time to live in seconds (default 1 hour)
            
        Returns:
            True if successful
        """
        key = f"feature:{feature_id}:context"
        value = json.dumps(context)
        return self.client.setex(key, ttl, value)

    def get_feature_context(self, feature_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve feature clarification context.
        
        Args:
            feature_id: Unique feature identifier
            
        Returns:
            Context dictionary or None if not found
        """
        key = f"feature:{feature_id}:context"
        value = self.client.get(key)
        return json.loads(value) if value else None

    def update_feature_context(
        self,
        feature_id: int,
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update existing feature context with new data.
        
        Args:
            feature_id: Unique feature identifier
            updates: Dictionary of updates to merge
            
        Returns:
            True if successful
        """
        context = self.get_feature_context(feature_id) or {}
        context.update(updates)
        return self.set_feature_context(feature_id, context)

    def delete_feature_context(self, feature_id: int) -> bool:
        """
        Delete feature context from Redis.
        
        Args:
            feature_id: Unique feature identifier
            
        Returns:
            True if deleted
        """
        key = f"feature:{feature_id}:context"
        return bool(self.client.delete(key))

    # ========================================================================
    # Conversation State Management
    # ========================================================================

    def set_conversation_state(
        self,
        session_id: str,
        state: Dict[str, Any],
        ttl: int = 7200
    ) -> bool:
        """
        Store agent conversation state.
        
        Args:
            session_id: Unique session identifier
            state: Conversation state dictionary
            ttl: Time to live in seconds (default 2 hours)
            
        Returns:
            True if successful
        """
        key = f"conversation:{session_id}:state"
        value = json.dumps(state)
        return self.client.setex(key, ttl, value)

    def get_conversation_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve conversation state.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            State dictionary or None if not found
        """
        key = f"conversation:{session_id}:state"
        value = self.client.get(key)
        return json.loads(value) if value else None

    def append_conversation_message(
        self,
        session_id: str,
        role: str,
        content: str
    ) -> bool:
        """
        Append a message to conversation history.
        
        Args:
            session_id: Unique session identifier
            role: Message role (user/assistant/agent)
            content: Message content
            
        Returns:
            True if successful
        """
        key = f"conversation:{session_id}:messages"
        message = json.dumps({"role": role, "content": content})
        return bool(self.client.rpush(key, message))

    def get_conversation_messages(self, session_id: str, limit: int = 50) -> List[Dict[str, str]]:
        """
        Retrieve conversation message history.
        
        Args:
            session_id: Unique session identifier
            limit: Maximum number of messages to retrieve
            
        Returns:
            List of message dictionaries
        """
        key = f"conversation:{session_id}:messages"
        messages = self.client.lrange(key, -limit, -1)
        return [json.loads(msg) for msg in messages]

    # ========================================================================
    # Orchestration Graph Management
    # ========================================================================

    def set_orchestration_graph(
        self,
        graph_id: str,
        graph_data: Dict[str, Any],
        ttl: int = 3600
    ) -> bool:
        """
        Store orchestration graph metadata.
        
        Args:
            graph_id: Unique graph identifier
            graph_data: Graph state and metadata
            ttl: Time to live in seconds
            
        Returns:
            True if successful
        """
        key = f"orchestration:{graph_id}:graph"
        value = json.dumps(graph_data)
        return self.client.setex(key, ttl, value)

    def get_orchestration_graph(self, graph_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve orchestration graph.
        
        Args:
            graph_id: Unique graph identifier
            
        Returns:
            Graph data or None if not found
        """
        key = f"orchestration:{graph_id}:graph"
        value = self.client.get(key)
        return json.loads(value) if value else None

    # ========================================================================
    # Agent State Management
    # ========================================================================

    def set_agent_state(
        self,
        agent_name: str,
        agent_id: str,
        state: Dict[str, Any],
        ttl: int = 1800
    ) -> bool:
        """
        Store individual agent state.
        
        Args:
            agent_name: Name of the agent
            agent_id: Unique agent instance ID
            state: Agent state dictionary
            ttl: Time to live in seconds
            
        Returns:
            True if successful
        """
        key = f"agent:{agent_name}:{agent_id}:state"
        value = json.dumps(state)
        return self.client.setex(key, ttl, value)

    def get_agent_state(self, agent_name: str, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve agent state.
        
        Args:
            agent_name: Name of the agent
            agent_id: Unique agent instance ID
            
        Returns:
            Agent state or None if not found
        """
        key = f"agent:{agent_name}:{agent_id}:state"
        value = self.client.get(key)
        return json.loads(value) if value else None

    # ========================================================================
    # Cache Management
    # ========================================================================

    def cache_llm_response(
        self,
        prompt_hash: str,
        response: str,
        ttl: int = 86400
    ) -> bool:
        """
        Cache LLM response for identical prompts.
        
        Args:
            prompt_hash: Hash of the prompt
            response: LLM response to cache
            ttl: Time to live in seconds (default 24 hours)
            
        Returns:
            True if successful
        """
        key = f"cache:llm:{prompt_hash}"
        return self.client.setex(key, ttl, response)

    def get_cached_llm_response(self, prompt_hash: str) -> Optional[str]:
        """
        Retrieve cached LLM response.
        
        Args:
            prompt_hash: Hash of the prompt
            
        Returns:
            Cached response or None
        """
        key = f"cache:llm:{prompt_hash}"
        return self.client.get(key)

    # ========================================================================
    # Transcript Analysis Context Management
    # ========================================================================

    def set_transcript_context(
        self,
        sprint_id: str,
        context: Dict[str, Any],
        ttl: int = 604800  # 7 days default
    ) -> bool:
        """
        Store transcript analysis context for a sprint.
        
        Args:
            sprint_id: Sprint identifier
            context: Context dictionary with transcript data and analysis
            ttl: Time to live in seconds (default 7 days)
            
        Returns:
            True if successful
        """
        key = f"transcript:{sprint_id}:context"
        value = json.dumps(context)
        return self.client.setex(key, ttl, value)

    def get_transcript_context(self, sprint_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve transcript analysis context.
        
        Args:
            sprint_id: Sprint identifier
            
        Returns:
            Context dictionary or None if not found
        """
        key = f"transcript:{sprint_id}:context"
        value = self.client.get(key)
        return json.loads(value) if value else None

    def update_transcript_context(
        self,
        sprint_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update existing transcript context with new data.
        
        Args:
            sprint_id: Sprint identifier
            updates: Dictionary of updates to merge
            
        Returns:
            True if successful
        """
        context = self.get_transcript_context(sprint_id) or {}
        context.update(updates)
        return self.set_transcript_context(sprint_id, context)

    def set_member_warning(
        self,
        sprint_id: str,
        member_email: str,
        warning_data: Dict[str, Any],
        ttl: int = 604800
    ) -> bool:
        """
        Store warning for a team member.
        
        Args:
            sprint_id: Sprint identifier
            member_email: Team member email
            warning_data: Warning details
            ttl: Time to live in seconds
            
        Returns:
            True if successful
        """
        key = f"transcript:{sprint_id}:warning:{member_email}"
        value = json.dumps(warning_data)
        return self.client.setex(key, ttl, value)

    def get_member_warnings(self, sprint_id: str) -> List[Dict[str, Any]]:
        """
        Get all warnings for a sprint.
        
        Args:
            sprint_id: Sprint identifier
            
        Returns:
            List of warning dictionaries
        """
        pattern = f"transcript:{sprint_id}:warning:*"
        keys = self.client.keys(pattern)
        warnings = []
        for key in keys:
            value = self.client.get(key)
            if value:
                warnings.append(json.loads(value))
        return warnings

    # ========================================================================
    # Utility Methods
    # ========================================================================

    def ping(self) -> bool:
        """Test Redis connection."""
        try:
            return self.client.ping()
        except redis.ConnectionError:
            return False

    def flush_all(self) -> bool:
        """
        Flush all keys from current database.
        WARNING: Use only in development!
        """
        return self.client.flushdb()

    def close(self) -> None:
        """Close Redis connection."""
        self.client.close()


# Singleton instance
_redis_client: Optional[RedisClient] = None


def get_redis_client() -> RedisClient:
    """
    Get or create Redis client singleton.
    
    Returns:
        RedisClient instance
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client

