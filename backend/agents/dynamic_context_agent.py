"""Dynamic Context Agent for feature clarification."""

import logging
from typing import Dict, Any, Optional, List
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class DynamicContextAgent(BaseAgent):
    """
    Dynamic Context Agent.
    
    Responsibilities:
    - Ask contextual clarifying questions based on user input
    - Update Redis with feature_context
    - Signal when context is sufficiently understood
    - Maintain conversation flow for feature refinement
    
    Input: Feature name and description
    Output: Structured, clarified context JSON or next clarification question
    """

    def __init__(self):
        """Initialize Dynamic Context Agent."""
        super().__init__(agent_name="DynamicContextAgent")
        
        self.system_prompt = """You are an expert Scrum Master and Product Owner who helps clarify feature requirements.

Your goal is to understand the feature deeply by asking targeted questions about:
1. User personas and target audience
2. Key goals and success metrics
3. Core functionality and edge cases
4. Dependencies and technical constraints
5. Acceptance criteria and definition of done

Ask one question at a time. Be conversational and natural.
When you have enough information, indicate completion."""

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute clarification logic.
        
        Args:
            input_data: {
                "feature_id": int,
                "feature_name": str,
                "feature_description": str,
                "user_response": Optional[str],
                "conversation_history": Optional[List[Dict]]
            }
            
        Returns:
            {
                "feature_id": int,
                "question": Optional[str],
                "is_complete": bool,
                "context_summary": Optional[Dict],
                "conversation_history": List[Dict]
            }
        """
        feature_id = input_data["feature_id"]
        feature_name = input_data.get("feature_name")
        feature_description = input_data.get("feature_description")
        user_response = input_data.get("user_response")
        conversation_history = input_data.get("conversation_history", [])
        
        # Get existing context from Redis
        context = self.redis_client.get_feature_context(feature_id) or {}

        # STRICT LIMIT: Maximum 5 questions allowed under any circumstances
        questions_asked = context.get("questions_asked", 0)
        if questions_asked >= 5:
            # Force completion after 5 questions maximum
            logger.warning(f"🚨 MAXIMUM QUESTION LIMIT REACHED: {questions_asked} questions asked for feature {feature_id}. Forcing completion.")
            return await self._force_completion(feature_id, context, conversation_history)

        # Build conversation for LLM
        if not conversation_history:
            # First interaction
            initial_prompt = f"""Feature Name: {feature_name}
Feature Description: {feature_description}

Please ask the first clarifying question to understand this feature better."""
            
            response = self.generate_json_response(
                prompt=initial_prompt,
                system_message=self.system_prompt + "\n\nRespond in JSON format: {\"question\": \"your question here\", \"is_complete\": false}"
            )
            
            conversation_history.append({
                "role": "user",
                "content": f"Feature: {feature_name}\nDescription: {feature_description}"
            })
            conversation_history.append({
                "role": "assistant",
                "content": response.get("question", "")
            })
            
            # Update context
            context["feature_name"] = feature_name
            context["feature_description"] = feature_description
            context["questions_asked"] = 1
            self.redis_client.set_feature_context(feature_id, context)
            
            return {
                "feature_id": feature_id,
                "question": response.get("question"),
                "is_complete": False,
                "context_summary": None,
                "conversation_history": conversation_history
            }
        
        else:
            # Continuing conversation
            conversation_history.append({
                "role": "user",
                "content": user_response
            })
            
            # Limit conversation history to last 6 messages (3 turns) to reduce token usage
            # This prevents hitting token limits on repeated OpenAI calls
            recent_history = conversation_history[-6:] if len(conversation_history) > 6 else conversation_history
            
            # Build prompt for next question or completion
            # Use recent history to reduce tokens, but include feature metadata for context
            prompt = f"""Feature Name: {context.get('feature_name', 'Unknown')}
Feature Description (brief): {context.get('feature_description', '')[:400]}...

Recent conversation (last 3 exchanges):
{self._format_conversation(recent_history)}

User's latest response: {user_response}

Based on this conversation so far, decide:
1. If you have enough information, set is_complete: true and provide a comprehensive context_summary
2. If you need more information, ask the next clarifying question and set is_complete: false

Respond in JSON format:
{{
    "question": "next question or null if complete",
    "is_complete": true/false,
    "context_summary": {{
        "goals": ["goal1", "goal2"],
        "user_personas": ["persona1"],
        "key_features": ["feature1", "feature2"],
        "acceptance_criteria": ["criteria1", "criteria2"],
        "technical_constraints": ["constraint1"],
        "success_metrics": ["metric1"]
    }} or null if not complete
}}"""
            
            response = self.generate_json_response(
                prompt=prompt,
                system_message=self.system_prompt,
                temperature=0.7
            )
            
            is_complete = response.get("is_complete", False)
            question = response.get("question")
            context_summary = response.get("context_summary")

            # If completion is triggered without a summary, try to synthesize one
            if is_complete and not context_summary:
                context_summary = self._generate_context_summary(conversation_history)
                if not context_summary:
                    is_complete = False
                    question = (
                        "Thanks for the detailed response! To finalize the clarification, "
                        "could you summarize the goals, key user personas, core features, "
                        "acceptance criteria, technical constraints, and success metrics?"
                    )

            # If not complete but no question provided, generate a default follow-up
            if not is_complete and not question:
                question = (
                    "Could you provide more details about the remaining aspects? "
                    "Please share information about the goals, user personas, key features, "
                    "acceptance criteria, technical constraints, and success metrics."
                )

            if not is_complete and question:
                conversation_history.append({
                    "role": "assistant",
                    "content": question
                })
            
            # Update context in Redis
            if is_complete and context_summary:
                context.update(context_summary)
                context["context_summary"] = context_summary
                context["is_complete"] = True
            else:
                context["is_complete"] = False
            
            context["questions_asked"] = context.get("questions_asked", 0) + 1
            self.redis_client.set_feature_context(feature_id, context)
            
            return {
                "feature_id": feature_id,
                "question": question if not is_complete else None,
                "is_complete": is_complete,
                "context_summary": context_summary if is_complete else None,
                "conversation_history": conversation_history
            }

    def _generate_context_summary(
        self,
        conversation_history: List[Dict[str, str]]
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a context summary from the conversation when the LLM omits it.

        Args:
            conversation_history: Full conversation so far

        Returns:
            Context summary dictionary or None if generation fails
        """
        if not conversation_history:
            return None

        # Use only recent history to reduce tokens
        recent_history = conversation_history[-8:] if len(conversation_history) > 8 else conversation_history
        conversation_text = self._format_conversation(recent_history)
        
        summary_prompt = f"""Based on this conversation, produce the structured context summary as JSON with the following keys:
{{
    "goals": ["goal1", "goal2"],
    "user_personas": ["persona1"],
    "key_features": ["feature1"],
    "acceptance_criteria": ["criteria1"],
    "technical_constraints": ["constraint1"],
    "success_metrics": ["metric1"]
}}

Conversation (recent):
{conversation_text}

Respond with valid JSON only."""

        try:
            summary_response = self.generate_json_response(
                prompt=summary_prompt,
                system_message="You are an expert Scrum Master summarizing the conversation. Respond with the requested JSON.",
                temperature=0.3
            )
        except Exception:
            return None

        if not isinstance(summary_response, dict):
            return None

        if "context_summary" in summary_response and isinstance(summary_response["context_summary"], dict):
            return summary_response["context_summary"]

        return summary_response if isinstance(summary_response, dict) else None

    async def _force_completion(self, feature_id: int, context: Dict[str, Any], conversation_history: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Force completion when maximum question limit is reached.

        This method generates a context summary from available information
        when the agent has asked the maximum allowed questions.
        """
        logger.info(f"🔄 Forcing completion for feature {feature_id} after maximum questions")

        # Generate context summary from available conversation
        context_summary = self._generate_context_summary(conversation_history)

        # If we can't generate a summary, provide a minimal one
        if not context_summary:
            context_summary = {
                "goals": ["Feature implementation and delivery"],
                "user_personas": ["End users"],
                "key_features": [context.get("feature_name", "Feature")],
                "acceptance_criteria": ["Feature meets basic requirements"],
                "technical_constraints": ["Standard web application constraints"],
                "success_metrics": ["Successful deployment and user adoption"]
            }
            logger.warning(f"⚠️ Generated minimal context summary for feature {feature_id} due to question limit")

        # Update context with completion
        context.update(context_summary)
        context["context_summary"] = context_summary
        context["is_complete"] = True
        context["forced_completion"] = True  # Mark that this was forced due to limit
        self.redis_client.set_feature_context(feature_id, context)

        return {
            "feature_id": feature_id,
            "question": None,  # No more questions
            "is_complete": True,
            "context_summary": context_summary,
            "conversation_history": conversation_history,
            "forced_completion": True,  # Indicate this was due to question limit
            "completion_reason": "Maximum question limit reached (5 questions)"
        }

    def _format_conversation(self, conversation: List[Dict[str, str]]) -> str:
        """
        Format conversation history for LLM prompt.
        
        Args:
            conversation: List of message dictionaries
            
        Returns:
            Formatted conversation string
        """
        formatted = []
        for msg in conversation:
            role = msg["role"].capitalize()
            content = msg["content"]
            formatted.append(f"{role}: {content}")
        return "\n\n".join(formatted)

    async def get_context(self, feature_id: int) -> Optional[Dict[str, Any]]:
        """
        Get current feature context.
        
        Args:
            feature_id: Feature ID
            
        Returns:
            Context dictionary or None
        """
        return self.redis_client.get_feature_context(feature_id)

    async def reset_context(self, feature_id: int) -> bool:
        """
        Reset feature context.
        
        Args:
            feature_id: Feature ID
            
        Returns:
            True if successful
        """
        return self.redis_client.delete_feature_context(feature_id)

