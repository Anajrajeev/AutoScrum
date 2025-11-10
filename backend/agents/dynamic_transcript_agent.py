# backend/agents/dynamic_transcript_agent.py
"""
LLM-powered Transcript analysis + action dispatcher for AutoScrum.

- Input: JSON transcript (sprint_id, start_date, end_date, project_key, team[], transcripts[])
- LLM Analysis: Identifies lagging members, blockers, and help requests
- Actions:
  - Lagging members: Issue warnings
  - Blockers: Create ServiceNow incidents
  - Help requests: Create Jira tasks with workload-based assignment
- Context: Store analysis in Redis for LLM context
- Tool resolution: Uses MCP tools for Jira/ServiceNow integration
"""

import re
import os
import json
import logging
import importlib
from typing import List, Dict, Any, Optional
from datetime import datetime

from utils.openai_llm import get_llm_client
from memory.redis_client import get_redis_client

logger = logging.getLogger("agents.dynamic_transcript_agent")
logger.setLevel(os.getenv("AUTOSCRUM_LOG_LEVEL", "INFO"))
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(ch)

# -------------------------
# Tool resolver for MCP tools
# -------------------------
def get_tool_funcs():
    """Get MCP tool functions for Jira and ServiceNow operations."""
    try:
        from mcp_tools.tools.jira_client import (
            jira_create_story_impl,
            jira_get_team_capacity_impl,
            jira_assign_task_impl,
            jira_get_user_workload_impl
        )
        from mcp_tools.tools.servicenow_client import (
            servicenow_create_incident_impl
        )
        return {
            "jira_create_story_impl": jira_create_story_impl,
            "jira_get_team_capacity_impl": jira_get_team_capacity_impl,
            "jira_assign_task_impl": jira_assign_task_impl,
            "jira_get_user_workload_impl": jira_get_user_workload_impl,
            "servicenow_create_incident_impl": servicenow_create_incident_impl,
        }
    except ImportError as e:
        logger.error(f"Failed to import MCP tools: {e}")
        return {}

# -------------------------
# Core analysis / dispatch
# -------------------------
class DynamicTranscriptAgent:
    def __init__(self, sprint_id: str, start_date: str, end_date: str, project_key: str, team: List[Dict[str, Any]], transcripts: List[Dict[str, Any]]):
        self.sprint_id = sprint_id
        self.start_date = start_date
        self.end_date = end_date
        self.project_key = project_key
        self.team = {t.get("email"): t for t in team if t.get("email")}
        self.transcripts = transcripts
        self.tools = get_tool_funcs()
        self.redis_client = get_redis_client()
        self.llm_client = get_llm_client()

    def _store_context_in_redis(self, analysis_data: Dict[str, Any]):
        """Store analysis context in Redis for LLM memory."""
        try:
            context_key = f"transcript_analysis:{self.sprint_id}:{self.start_date}:{self.end_date}"
            self.redis_client.set_feature_context(context_key, analysis_data, ttl=86400)  # 24 hours
            logger.info(f"Stored analysis context in Redis: {context_key}")
        except Exception as e:
            logger.error(f"Failed to store context in Redis: {e}")

    def _get_context_from_redis(self) -> Optional[Dict[str, Any]]:
        """Retrieve previous analysis context from Redis."""
        try:
            context_key = f"transcript_analysis:{self.sprint_id}:{self.start_date}:{self.end_date}"
            return self.redis_client.get_feature_context(context_key)
        except Exception as e:
            logger.error(f"Failed to retrieve context from Redis: {e}")
            return None

    async def _analyze_with_llm(self, transcript_data: Dict[str, Any]) -> Dict[str, Any]:
        """Use LLM to analyze transcripts and identify issues."""

        # Get previous context for continuity
        previous_context = self._get_context_from_redis()

        prompt = f"""
        You are an expert Scrum Master AI analyzing daily scrum transcripts for the past 5 days.

        SPRINT CONTEXT:
        - Sprint ID: {self.sprint_id}
        - Start Date: {self.start_date}
        - End Date: {self.end_date}
        - Project: {self.project_key}

        TEAM MEMBERS:
        {json.dumps([{k: v.get('name', '') + ' (' + v.get('role', '') + ')'} for k, v in self.team.items()], indent=2)}

        TRANSCRIPT DATA:
        {json.dumps(transcript_data, indent=2)}

        PREVIOUS ANALYSIS CONTEXT (if any):
        {json.dumps(previous_context, indent=2) if previous_context else "No previous context"}

        TASK: Analyze the transcripts and identify:

        1. LAGGING MEMBERS: Team members who are behind schedule, not making progress, or showing signs of being stuck
        2. BLOCKERS: Technical or external obstacles preventing progress (access issues, dependencies, etc.)
        3. HELP REQUESTS: Members explicitly asking for help or showing signs they need assistance

        For each issue identified, provide:
        - Person's email
        - Issue type (lagging/blocker/help_request)
        - Specific evidence from transcripts
        - Recommended action
        - Confidence level (0-1)

        Return ONLY a valid JSON object with this structure:
        {{
          "lagging_members": [
            {{
              "person_email": "email@example.com",
              "evidence": "Specific transcript excerpts showing lack of progress",
              "recommended_action": "Warning message or intervention needed",
              "confidence": 0.8
            }}
          ],
          "blockers": [
            {{
              "person_email": "email@example.com",
              "evidence": "Specific transcript excerpts showing the blocker",
              "blocker_type": "access/dependency/technical/other",
              "recommended_action": "Create ServiceNow ticket with specific details",
              "confidence": 0.9
            }}
          ],
          "help_requests": [
            {{
              "person_email": "email@example.com",
              "evidence": "Specific transcript excerpts showing help request",
              "help_type": "technical/review/mentoring/other",
              "recommended_action": "Assign experienced team member based on workload",
              "confidence": 0.7
            }}
          ]
        }}
        """

        try:
            response = await self.llm_client.chat_completion_async(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.3
            )

            # Extract JSON from response
            content = response.get('content', '').strip()
            if content.startswith('```json'):
                content = content[7:]
            if content.endswith('```'):
                content = content[:-3]
            content = content.strip()

            analysis = json.loads(content)
            logger.info(f"LLM analysis completed: {len(analysis.get('lagging_members', []))} lagging, {len(analysis.get('blockers', []))} blockers, {len(analysis.get('help_requests', []))} help requests")
            return analysis

        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            return {"lagging_members": [], "blockers": [], "help_requests": []}

    async def _create_servicenow_ticket(self, person: str, blocker_details: Dict[str, Any]) -> Dict[str, Any]:
        """Create ServiceNow incident for blocker."""
        func = self.tools.get("servicenow_create_incident_impl")
        if not func:
            logger.warning("ServiceNow create incident function not found")
            return {"error": "ServiceNow tool not available"}

        # Get person details
        person_info = self.team.get(person, {})
        person_name = person_info.get('name', person)

        payload = {
            "short_description": f"Blocker: {person_name} - {blocker_details.get('blocker_type', 'technical')} issue",
            "description": f"""
Auto-detected blocker from scrum transcript analysis.

Person: {person_name} ({person})
Blocker Type: {blocker_details.get('blocker_type', 'unknown')}
Evidence: {blocker_details.get('evidence', 'N/A')}
Confidence: {blocker_details.get('confidence', 0):.2f}

Sprint: {self.sprint_id}
Project: {self.project_key}
            """.strip(),
            "assignment_group": "Developer Support",
            "priority": "2",
            "caller_id": person,
            "contact_type": "email"
        }

        try:
            resp = await func(**payload)
            logger.info(f"Created ServiceNow ticket for {person}: {resp}")
            return resp
        except Exception as e:
            logger.exception(f"ServiceNow ticket creation failed for {person}: {e}")
            return {"error": str(e)}

    async def _create_jira_help_task(self, person: str, help_details: Dict[str, Any]) -> Dict[str, Any]:
        """Create Jira task for help request with workload-based assignment."""
        create_story = self.tools.get("jira_create_story_impl")
        get_capacity = self.tools.get("jira_get_team_capacity_impl")

        if not create_story:
            logger.warning("Jira create story function not found")
            return {"error": "Jira tool not available"}

        # Always use SCRUM as the project key (constant)
        project_key = "SCRUM"
        logger.info(f"Using constant project key: 'SCRUM'")

        # Get person details
        person_info = self.team.get(person, {})
        person_name = person_info.get('name', person)

        # Find best assignee based on workload
        best_assignee = await self._find_best_assignee(person)

        if not best_assignee:
            logger.warning(f"No suitable assignee found for help task. Using first available team member.")
            # Fallback to any team member except requester
            for email in self.team.keys():
                if email != person:
                    best_assignee = email
                    break

        # Ensure summary and description are clearly separated
        summary_text = f"Help Request: Assist {person_name} ({help_details.get('help_type', 'technical')} support)"
        description_text = f"""Auto-detected help request from scrum transcript analysis.

Person needing help: {person_name} ({person})
Help Type: {help_details.get('help_type', 'unknown')}
Evidence: {help_details.get('evidence', 'N/A')}
Confidence: {help_details.get('confidence', 0):.2f}

Sprint: {self.sprint_id}
Project: {project_key}

Please provide assistance and update the requesting team member.""".strip()

        payload = {
            "project_key": project_key.strip(),
            "summary": summary_text,  # Title/Summary field
            "description": description_text,  # Description field
            "story_points": 2,
            "assignee": best_assignee
        }

        logger.info(f"Creating Jira help task:")
        logger.info(f"  project_key: '{project_key}'")
        logger.info(f"  summary (title): '{summary_text[:80]}...'")
        logger.info(f"  description length: {len(description_text)}")
        logger.info(f"  assignee: '{best_assignee}'")

        try:
            resp = await create_story(**payload)
            if resp.get("success"):
                logger.info(f"Created Jira help task for {person}, assigned to {best_assignee}: {resp.get('data', {}).get('key', 'N/A')}")
                return {"action": "created_help_task", "assignee": best_assignee, "response": resp}
            else:
                error_msg = resp.get("error", {}).get("message", "Unknown error") if isinstance(resp.get("error"), dict) else str(resp.get("error", "Unknown error"))
                logger.error(f"Jira help task creation failed for {person}: {error_msg}")
                return {"error": error_msg, "response": resp}
        except Exception as e:
            logger.exception(f"Jira help task creation failed for {person}: {e}")
            return {"error": str(e)}

    async def _find_best_assignee(self, requesting_person: str) -> Optional[str]:
        """Find the best team member to assign help task based on workload."""
        get_capacity = self.tools.get("jira_get_team_capacity_impl")

        if not get_capacity:
            # Fallback: return first available team member (not the requester)
            for email, info in self.team.items():
                if email != requesting_person:
                    return email
            return None

        try:
            cap_resp = await get_capacity(board_id=1)
            if cap_resp.get("success") and cap_resp.get("data", {}).get("team"):
                team_capacity = cap_resp["data"]["team"]

                # Sort by available capacity (descending)
                sorted_team = sorted(team_capacity, key=lambda x: x.get("available_capacity", 0), reverse=True)

                # Return first person with capacity > 0 (not the requester)
                for member in sorted_team:
                    email = member.get("email")
                    available_capacity = member.get("available_capacity", 0)
                    if email and email != requesting_person and available_capacity > 0:
                        return email

        except Exception as e:
            logger.exception(f"Failed to get team capacity: {e}")

        # Fallback: return any team member except requester
        for email in self.team.keys():
            if email != requesting_person:
                return email

        return None

    def _generate_warning(self, person: str, lagging_details: Dict[str, Any]) -> Dict[str, Any]:
        """Generate warning for lagging member."""
        person_info = self.team.get(person, {})
        person_name = person_info.get('name', person)

        warning = {
            "type": "warning",
            "person": person,
            "person_name": person_name,
            "message": f"Warning: {person_name} appears to be lagging behind schedule",
            "evidence": lagging_details.get('evidence', ''),
            "recommended_action": lagging_details.get('recommended_action', ''),
            "confidence": lagging_details.get('confidence', 0),
            "sprint": self.sprint_id
        }

        logger.warning(f"Generated warning for {person}: {warning['message']}")
        return warning

    async def process(self) -> Dict[str, Any]:
        """Main processing method."""
        logger.info(f"Starting transcript analysis for sprint {self.sprint_id}")

        # Prepare transcript data for LLM analysis
        transcript_data = {
            "sprint_id": self.sprint_id,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "project_key": self.project_key,
            "team": self.team,
            "transcripts": self.transcripts
        }

        # Analyze with LLM
        analysis = await self._analyze_with_llm(transcript_data)

        # Store analysis context in Redis
        self._store_context_in_redis(analysis)

        actions = []

        # Process lagging members
        for lagging in analysis.get("lagging_members", []):
            person = lagging["person_email"]
            if person in self.team:
                warning = self._generate_warning(person, lagging)
                actions.append(warning)

        # Process blockers
        for blocker in analysis.get("blockers", []):
            person = blocker["person_email"]
            if person in self.team:
                ticket_result = await self._create_servicenow_ticket(person, blocker)
                actions.append({
                    "type": "blocker_ticket",
                    "person": person,
                    "person_name": self.team[person].get('name', person),
                    "blocker_details": blocker,
                    "ticket_result": ticket_result
                })

        # Process help requests
        for help_request in analysis.get("help_requests", []):
            person = help_request["person_email"]
            if person in self.team:
                task_result = await self._create_jira_help_task(person, help_request)
                actions.append({
                    "type": "help_task",
                    "person": person,
                    "person_name": self.team[person].get('name', person),
                    "help_details": help_request,
                    "task_result": task_result
                })

        result = {
            "summary": {
                "sprint_id": self.sprint_id,
                "warnings": len([a for a in actions if a["type"] == "warning"]),
                "blocker_tickets": len([a for a in actions if a["type"] == "blocker_ticket"]),
                "help_tasks": len([a for a in actions if a["type"] == "help_task"]),
                "total_actions": len(actions)
            },
            "actions": actions,
            "llm_analysis": analysis
        }

        logger.info(f"Transcript analysis completed: {result['summary']}")
        return result

# Convenience function used by route
async def analyze_transcript_json(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    payload: the exact JSON format provided by user:
    {
      "sprint_id": "SP-2025-11-W1",
      "start_date": "2025-11-03",
      "end_date": "2025-11-07",
      "project_key": "AIOPSCF",
      "team": [...],
      "transcripts": [...]
    }
    """
    sprint_id = payload.get("sprint_id", "unknown")
    start_date = payload.get("start_date", "")
    end_date = payload.get("end_date", "")
    # Always use SCRUM as the project key (constant)
    project_key = "SCRUM"
    team = payload.get("team", [])
    transcripts = payload.get("transcripts", [])

    agent = DynamicTranscriptAgent(
        sprint_id=sprint_id,
        start_date=start_date,
        end_date=end_date,
        project_key=project_key,
        team=team,
        transcripts=transcripts
    )
    return await agent.process()
