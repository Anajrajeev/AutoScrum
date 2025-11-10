# backend/autoscrum/transcript_agent.py
"""
Transcript analysis + action dispatcher for AutoScrum.

- Input: JSON transcript (sprint_id, start_date, end_date, project_key, team[], transcripts[])
- Actions:
  - Detect access blockers -> create ServiceNow incident
  - Detect help requests -> create Jira subtask/story and assign to available teammate
  - Detect slow/pace issues -> create coaching/triage Jira story
- Idempotency: simple SQLite DB (autoscrum_actions.db) to avoid duplicate actions
- Tool resolution: dynamically tries to import your Jira/ServiceNow impl functions
"""

import re
import os
import json
import sqlite3
import logging
import importlib
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("autoscrum.transcript_agent")
logger.setLevel(os.getenv("AUTOSCRUM_LOG_LEVEL", "INFO"))
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(ch)

# -------------------------
# Idempotency / local DB
# -------------------------
# Replace the previous SQLite DB helpers with SQLAlchemy based helpers
# Add these imports at top of file (ensure paths match your project)
from db.database import SessionLocal  # adjust path if needed
from db.models import TranscriptAction  # import the model we added

# Remove DB_PATH and sqlite3 usage entirely.

def action_exists(action_key: str) -> bool:
    """
    Check whether an action with given action_key already exists in the project's DB.
    """
    db = SessionLocal()
    try:
        exists = db.query(TranscriptAction).filter(TranscriptAction.action_key == action_key).first() is not None
        return exists
    finally:
        db.close()

def persist_action(action_key: str, person: str, story: Optional[str], diagnosis: str, confidence: float, payload: dict, response: dict):
    """
    Persist a TranscriptAction row using the project's DB session.
    """
    db = SessionLocal()
    try:
        # Use get-or-create semantics to avoid race conditions
        obj = db.query(TranscriptAction).filter(TranscriptAction.action_key == action_key).first()
        if obj:
            # update optionally
            obj.person = person or obj.person
            obj.story = story or obj.story
            obj.diagnosis = diagnosis or obj.diagnosis
            obj.confidence = float(confidence) if confidence is not None else obj.confidence
            obj.payload = payload or obj.payload
            obj.response = response or obj.response
        else:
            obj = TranscriptAction(
                action_key=action_key,
                person=person or None,
                story=story or None,
                diagnosis=diagnosis,
                confidence=float(confidence) if confidence is not None else None,
                payload=payload,
                response=response
            )
            db.add(obj)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

# -------------------------
# Regexes / keywords
# -------------------------
JIRA_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
ACCESS_KEYWORDS = ["access", "permission", "403", "401", "credentials", "vpn", "can't clone", "forbidden", "blocked", "cannot access", "no access"]
HELP_KEYWORDS = ["help", "pair", "review", "can someone", "assist", "please help", "need help", "assign"]
PACE_KEYWORDS = ["later", "not a priority", "will do later", "busy", "lack of time", "taking too long", "slow", "delay", "behind schedule", "haven't made progress", "no progress"]

# -------------------------
# Utility helpers
# -------------------------
def extract_jira_ids(text: str) -> List[str]:
    return list({m.group(1) for m in JIRA_RE.finditer(text)})

def contains_any(text: str, keywords: List[str]) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(k.lower() in t for k in keywords)

def make_action_key(person: str, story: Optional[str], diagnosis: str, excerpt: str) -> str:
    # deterministic unique key for idempotency - small and sufficient
    base = f"{person}||{story or 'NO_STORY'}||{diagnosis}||{excerpt[:200]}"
    return str(abs(hash(base)))

# -------------------------
# Dynamic tool resolver
# -------------------------
_POSSIBLE_MODULES = [
    "backend.jira_client",
    "backend.jira",
    "backend.integrations.jira",
    "backend.tools.jira",
    "backend.servicenow_client",
    "backend.servicenow",
    "backend.integrations.servicenow",
    "backend.tools.servicenow",
    "backend.services.servicenow",
    "backend.services.jira",
    # older/other variants
    "jira_client",
    "servicenow_client",
    "integrations.jira",
]

def _resolve_function(names: List[str]):
    """
    Try to import function by trying a few module name patterns.
    names: list of function names to search for, e.g. ['servicenow_create_incident_impl']
    Returns a dict name->callable (or None)
    """
    found = {}
    for name in names:
        found[name] = None
    for module_name in _POSSIBLE_MODULES:
        try:
            m = importlib.import_module(module_name)
        except Exception:
            continue
        for f in names:
            if found.get(f):
                continue
            if hasattr(m, f):
                found[f] = getattr(m, f)
    # final fallback: search top-level modules loaded
    for f in names:
        if found.get(f) is None:
            # try to find globally/present in sys.modules
            for mod in list(importlib.import_module("sys").modules.values()):
                try:
                    if hasattr(mod, f):
                        found[f] = getattr(mod, f)
                        break
                except Exception:
                    continue
    return found

# Lazy resolution cached
_TOOL_FUNCS = None
def get_tool_funcs():
    global _TOOL_FUNCS
    if _TOOL_FUNCS is not None:
        return _TOOL_FUNCS
    names = [
        "servicenow_create_incident_impl",
        "servicenow_list_incidents_impl",
        "jira_create_story_impl",
        "jira_get_team_capacity_impl",
        "jira_assign_task_impl",
        "jira_get_user_workload_impl"
    ]
    resolved = _resolve_function(names)
    _TOOL_FUNCS = resolved
    logger.info("Tool function resolution: %s", {k: bool(v) for k, v in resolved.items()})
    return _TOOL_FUNCS

# -------------------------
# Core analysis / dispatch
# -------------------------
class TranscriptAgent:
    def __init__(self, project_key: str, team: List[Dict[str, Any]], transcripts: List[Dict[str, Any]]):
        self.project_key = project_key
        self.team = {t.get("email"): t for t in team if t.get("email")}
        self.transcripts = transcripts
        self.tools = get_tool_funcs()

    def _merge_person_texts(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Build structure:
        { (person_email, story_id) : [ {date, text, flags...}, ... ] }
        Also build person->no-story entries when no jira id found.
        """
        timeline = {}
        for day in self.transcripts:
            date = day.get("date")
            for p in day.get("participants", []):
                email = p.get("email") or p.get("name")
                name = p.get("name")
                texts = p.get("spoken_text", []) or []
                for txt in texts:
                    jiras = extract_jira_ids(txt)
                    entry = {
                        "date": date,
                        "name": name,
                        "email": email,
                        "text": txt,
                        "jiras": jiras,
                        "access": contains_any(txt, ACCESS_KEYWORDS),
                        "help": contains_any(txt, HELP_KEYWORDS),
                        "pace": contains_any(txt, PACE_KEYWORDS)
                    }
                    if jiras:
                        for jid in jiras:
                            key = (email, jid)
                            timeline.setdefault(key, []).append(entry)
                    else:
                        key = (email, None)
                        timeline.setdefault(key, []).append(entry)
        return timeline

    async def _create_servicenow_incident(self, person: str, story: Optional[str], excerpt: str, confidence: float) -> Dict[str, Any]:
        func = self.tools.get("servicenow_create_incident_impl")
        payload = {
            "short_description": f"Access issue reported by {person} for {story or self.project_key}",
            "description": f"Auto-detected from scrum transcript. Excerpt: {excerpt}\nConfidence: {confidence:.2f}",
            "assignment_group": "Developer Support",
            "priority": "2",
            "caller_id": person,
            "contact_type": "email"
        }
        if not func:
            logger.warning("ServiceNow create incident function not found in environment. Returning mock.")
            return {"mock": True, "payload": payload}
        try:
            resp = await func(**payload)
            return resp
        except Exception as e:
            logger.exception("ServiceNow call failed: %s", e)
            return {"error": str(e)}

    async def _create_or_assign_jira_helper(self, person: str, story: Optional[str], excerpt: str, confidence: float) -> Dict[str, Any]:
        """
        Creates a helper/story/subtask to help 'person' on 'story'. Uses team capacity to find available teammate.
        """
        get_capacity = self.tools.get("jira_get_team_capacity_impl")
        create_story = self.tools.get("jira_create_story_impl")
        assign_task = self.tools.get("jira_assign_task_impl")

        # Extract project key from story if available (e.g., "AIOPSCF" from "AIOPSCF-13842")
        # Otherwise use the payload project_key, with fallback to default
        project_key = self.project_key
        if story:
            jira_ids = extract_jira_ids(story)
            if jira_ids:
                # Extract project key from first Jira ID (format: PROJECT-123)
                story_key = jira_ids[0]
                if "-" in story_key:
                    project_key = story_key.split("-")[0]
        
        # Ensure project_key is never None or empty
        if not project_key or not project_key.strip():
            project_key = self.project_key or "PROJ"
            logger.warning(f"Using fallback project_key: {project_key}")

        payload_base = {
            "project_key": project_key,
            "summary": f"Assist {person} on {story or 'unknown task'} (AutoScrum)",
            "description": f"Auto-suggested help: Excerpt: {excerpt}\nConfidence: {confidence:.2f}",
            "story_points": 0,
            "assignee": None
        }

        # if capacity function available, find first teammate with available_capacity > 0 (and not the requestor)
        buddy_email = None
        if get_capacity:
            try:
                cap_resp = await get_capacity(board_id=1)
                # the wrapper returns envelope {"success": True, "data": result}
                team = []
                if isinstance(cap_resp, dict):
                    # attempt to extract nested data
                    if cap_resp.get("success") and isinstance(cap_resp.get("data"), dict):
                        team = cap_resp.get("data", {}).get("team", [])
                    elif cap_resp.get("team"):
                        team = cap_resp.get("team", [])
                # fallback if response is raw
                if not team and isinstance(cap_resp, dict) and cap_resp.get("team"):
                    team = cap_resp.get("team")
                for m in team:
                    email = m.get("email") or m.get("name")
                    avail = m.get("available_capacity", 0) or 0
                    if email and avail and email != person:
                        buddy_email = email
                        break
            except Exception:
                logger.exception("Failed to get team capacity; continuing without buddy")

        # If buddy found, create a story assigned to them
        if buddy_email and create_story:
            payload = payload_base.copy()
            payload["assignee"] = buddy_email
            try:
                resp = await create_story(**payload)
                return {"action": "created_and_assigned", "assignee": buddy_email, "response": resp}
            except Exception as e:
                logger.exception("Failed to create story and assign: %s", e)
                # fallback to create unassigned story
        # Fallback: create triage story unassigned
        if create_story:
            try:
                resp = await create_story(**payload_base)
                return {"action": "created_unassigned", "response": resp}
            except Exception as e:
                logger.exception("Failed to create triage story: %s", e)
                return {"error": str(e)}
        else:
            logger.warning("Jira create story function not found; returning mock payload")
            return {"mock": True, "payload": payload_base}

    async def process(self) -> Dict[str, Any]:
        timeline = self._merge_person_texts()
        decisions = []
        for (person, story), events in timeline.items():
            # Build combined excerpt & compute flags
            excerpt = events[-1]["text"][:800]  # last update excerpt
            access = any(e["access"] for e in events)
            help_req = any(e["help"] for e in events)
            pace = any(e["pace"] for e in events)
            mentions = len(events)

            # simple confidence heuristic
            score = 0.0
            if story:
                score += 1.2
            if access:
                score += 1.0
            if help_req:
                score += 0.9
            if pace:
                score += 0.7
            score += 0.2 * (mentions - 1)
            # normalize to 0..1 (cap)
            confidence = min(score / 3.0, 1.0)

            # decide diagnosis
            diagnosis = "unknown"
            if access and confidence >= 0.3:
                diagnosis = "access"
            elif help_req and confidence >= 0.3:
                diagnosis = "needs_help"
            elif pace and confidence >= 0.7:
                diagnosis = "pace"
            else:
                diagnosis = "verify"

            # idempotency key
            action_key = make_action_key(person or "", story, diagnosis, excerpt)
            if action_exists(action_key):
                logger.info("Skipping duplicate action for key %s (person=%s, story=%s, diag=%s)", action_key, person, story, diagnosis)
                continue

            logger.info("Deciding action for %s on %s: diag=%s conf=%.2f excerpt=%s", person, story, diagnosis, confidence, excerpt[:120])

            result = None
            payload = {}
            if diagnosis == "access":
                payload = {"person": person, "story": story, "excerpt": excerpt, "confidence": confidence}
                result = await self._create_servicenow_incident(person, story, excerpt, confidence)
                persist_action(action_key, person, story, diagnosis, confidence, payload, result)
            elif diagnosis == "needs_help":
                payload = {"person": person, "story": story, "excerpt": excerpt, "confidence": confidence}
                result = await self._create_or_assign_jira_helper(person, story, excerpt, confidence)
                persist_action(action_key, person, story, diagnosis, confidence, payload, result)
            elif diagnosis == "pace":
                # create coaching/triage story
                payload = {"person": person, "story": story, "excerpt": excerpt, "confidence": confidence}
                result = await self._create_or_assign_jira_helper(person, story, excerpt, confidence)
                persist_action(action_key, person, story, diagnosis, confidence, payload, result)
            else:
                # verify -> create triage ticket
                payload = {"person": person, "story": story, "excerpt": excerpt, "confidence": confidence}
                result = await self._create_or_assign_jira_helper(person, story, excerpt, confidence)
                persist_action(action_key, person, story, diagnosis, confidence, payload, result)

            decisions.append({
                "person": person,
                "story": story,
                "diagnosis": diagnosis,
                "confidence": confidence,
                "excerpt": excerpt,
                "action_key": action_key,
                "result": result
            })
        return {"summary": {"decisions": len(decisions)}, "decisions": decisions}

# Convenience function used by route
async def analyze_transcript_json(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    payload: the exact JSON format you provided:
    {
      "sprint_id": "...", "start_date": "...", "end_date": "...",
      "project_key": "PROJ",
      "team": [...],
      "transcripts": [...]
    }
    """
    project_key = payload.get("project_key") or payload.get("project") or "PROJ"
    team = payload.get("team", [])
    transcripts = payload.get("transcripts", [])
    agent = TranscriptAgent(project_key=project_key, team=team, transcripts=transcripts)
    return await agent.process()
