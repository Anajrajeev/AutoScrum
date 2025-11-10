"""Story Creator Agent for generating Jira stories."""

from typing import Dict, Any, List
from .base_agent import BaseAgent


class StoryCreatorAgent(BaseAgent):
    """
    Story Creator Agent.
    
    Responsibilities:
    - Transform clarified context into Jira-compatible stories
    - Generate epics, user stories, and acceptance criteria
    - Push results to Jira via MCP
    - Log output into PostgreSQL
    
    Input: Context JSON from Dynamic Agent
    Output: Structured list of Jira story objects
    """

    def __init__(self):
        """Initialize Story Creator Agent."""
        super().__init__(agent_name="StoryCreatorAgent")
        
        self.system_prompt = """You are an expert Agile Story Writer who creates well-structured user stories.

For each feature, you should:
1. Break it down into logical user stories following the format: "As a [persona], I want [goal] so that [benefit]"
2. Create detailed acceptance criteria for each story
3. Estimate story points (1, 2, 3, 5, 8, 13)
4. Identify dependencies between stories
5. Organize stories into epics if needed

Focus on clarity, testability, and completeness."""

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute story generation logic.
        
        Args:
            input_data: {
                "feature_id": int,
                "context": Dict[str, Any],
                "generate_epic": bool (optional)
            }
            
        Returns:
            {
                "feature_id": int,
                "epic": Optional[Dict],
                "stories": List[Dict],
                "total_story_points": int
            }
        """
        import logging
        logger = logging.getLogger(__name__)
        
        feature_id = input_data["feature_id"]
        context = input_data["context"]
        generate_epic = input_data.get("generate_epic", True)
        
        # Build prompt for story generation
        prompt = self._build_story_generation_prompt(context, generate_epic)
        
        # Generate stories using LLM
        response = self.generate_json_response(
            prompt=prompt,
            system_message=self.system_prompt,
            temperature=0.6
        )
        
        logger.info(f"📋 [STORY EXEC] LLM raw response: {response}")
        
        # Extract and structure stories
        epic = response.get("epic") if generate_epic else None
        stories = response.get("stories", [])
        
        logger.info(f"📊 [STORY EXEC] Extracted {len(stories)} stories from response")
        
        # Calculate total story points
        total_story_points = sum(story.get("story_points", 0) for story in stories)
        
        # Format stories for database/Jira
        formatted_stories = []
        for idx, story in enumerate(stories):
            formatted_story = {
                "title": story.get("title", ""),
                "description": story.get("description", ""),
                "acceptance_criteria": story.get("acceptance_criteria", []),
                "story_points": story.get("story_points", 3),
                "priority": story.get("priority", "medium"),
                "dependencies": story.get("dependencies", []),
                "order": idx + 1
            }
            formatted_stories.append(formatted_story)
        
        return {
            "feature_id": feature_id,
            "epic": epic,
            "stories": formatted_stories,
            "total_story_points": total_story_points,
            "story_count": len(formatted_stories)
        }

    def _build_story_generation_prompt(
        self,
        context: Dict[str, Any],
        generate_epic: bool
    ) -> str:
        """
        Build prompt for story generation.
        
        Args:
            context: Feature context dictionary
            generate_epic: Whether to generate an epic
            
        Returns:
            Formatted prompt string
        """
        # Helper function to safely join list items
        def safe_join(items, default="Not specified"):
            if isinstance(items, list):
                return ', '.join(str(item) for item in items) if items else default
            elif isinstance(items, str):
                return items
            else:
                return default
        
        prompt = f"""You are an expert Agile story writer. Based on the feature context below, generate high-quality user stories.

Feature Context:
Name: {context.get('feature_name', 'Unknown')}
Description: {context.get('feature_description', '')}

Goals: {safe_join(context.get('goals', []))}
User Personas: {safe_join(context.get('user_personas', []))}
Key Features: {safe_join(context.get('key_features', []))}
Technical Constraints: {safe_join(context.get('technical_constraints', []))}
Success Metrics: {safe_join(context.get('success_metrics', []))}
Acceptance Criteria: {safe_join(context.get('acceptance_criteria', []))}

Instructions:
1. Generate AT LEAST 5-8 comprehensive user stories
2. Each story should follow the format: "As a [persona], I want [goal] so that [benefit]"
3. Include detailed acceptance criteria for each story
4. Estimate story points (1, 2, 3, 5, 8, or 13)
5. Assign priorities (high, medium, low)
6. The stories should cover all key features and goals mentioned above

IMPORTANT: The "stories" array MUST NOT be empty. Generate at least 5 stories."""

        if generate_epic:
            prompt += """

Please respond ONLY with valid JSON in this exact format:
{
    "epic": {
        "title": "Epic title summarizing the entire feature",
        "description": "Comprehensive description of the epic",
        "objectives": ["objective1", "objective2", "objective3"]
    },
    "stories": [
        {
            "title": "User story title (As a... I want... so that...)",
            "description": "Detailed description of what needs to be implemented",
            "acceptance_criteria": ["criteria1", "criteria2", "criteria3"],
            "story_points": 5,
            "priority": "high",
            "dependencies": []
        }
    ]
}

CRITICAL: Include at least 5-8 stories in the array."""
        else:
            prompt += """

Please respond ONLY with valid JSON:
{
    "stories": [
        {
            "title": "User story title",
            "description": "Detailed description",
            "acceptance_criteria": ["criteria1", "criteria2"],
            "story_points": 5,
            "priority": "high",
            "dependencies": []
        }
    ]
}

CRITICAL: Include at least 5-8 stories."""

        return prompt

    async def generate_from_feature_id(
        self,
        feature_id: int,
        generate_epic: bool = True
    ) -> Dict[str, Any]:
        """
        Generate stories from feature ID by fetching context from Redis.
        
        Args:
            feature_id: Feature ID
            generate_epic: Whether to generate an epic
            
        Returns:
            Story generation result
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # Get context from Redis
        context = self.redis_client.get_feature_context(feature_id)
        
        logger.info(f"📥 [STORY AGENT] Context retrieved from Redis for feature {feature_id}")
        logger.info(f"📦 [STORY AGENT] Context keys: {list(context.keys()) if context else 'None'}")
        
        if not context:
            logger.error(f"❌ [STORY AGENT] No context found for feature {feature_id}")
            raise ValueError(f"No context found for feature {feature_id}")

        # Normalize legacy contexts that might not have the is_complete flag
        if not context.get("is_complete", False):
            summary_block = context.get("context_summary")
            required_keys = [
                "goals",
                "user_personas",
                "key_features",
                "acceptance_criteria",
                "technical_constraints",
                "success_metrics"
            ]
            
            if isinstance(summary_block, dict) and summary_block:
                logger.info("ℹ️ [STORY AGENT] Normalizing context using embedded context_summary")
                merged_context = {**context, **summary_block}
                merged_context["is_complete"] = True
                context = merged_context
            elif all(key in context for key in required_keys):
                logger.info("ℹ️ [STORY AGENT] Context contains required keys; marking as complete")
                context["is_complete"] = True
            else:
                logger.error(f"❌ [STORY AGENT] Feature {feature_id} context is not complete")
                raise ValueError(f"Feature {feature_id} context is not complete")
        
        logger.info(f"✅ [STORY AGENT] Context is complete, proceeding with story generation")
        
        return await self.execute({
            "feature_id": feature_id,
            "context": context,
            "generate_epic": generate_epic
        })

    def validate_story(self, story: Dict[str, Any]) -> bool:
        """
        Validate story structure.
        
        Args:
            story: Story dictionary
            
        Returns:
            True if valid
        """
        required_fields = ["title", "description", "acceptance_criteria"]
        return all(field in story for field in required_fields)

    def estimate_complexity(self, story: Dict[str, Any]) -> int:
        """
        Estimate story complexity based on criteria count and description length.
        
        Args:
            story: Story dictionary
            
        Returns:
            Estimated story points (1, 2, 3, 5, 8, 13)
        """
        criteria_count = len(story.get("acceptance_criteria", []))
        description_length = len(story.get("description", ""))
        
        # Simple heuristic
        if criteria_count <= 2 and description_length < 200:
            return 2
        elif criteria_count <= 4 and description_length < 500:
            return 5
        elif criteria_count <= 6:
            return 8
        else:
            return 13

