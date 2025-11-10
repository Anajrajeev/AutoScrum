"""Resource-Aware Prioritization Agent for task allocation."""

from typing import Dict, Any, List, Optional
from .base_agent import BaseAgent
import math


class PrioritizationAgent(BaseAgent):
    """
    Resource-Aware Prioritization Agent.
    
    Responsibilities:
    - Fetch team data (designation, skill, capacity) from Jira via MCP
    - Apply load-balancing logic based on effective capacity
    - Assign stories automatically with MAX 5 story points per person
    - Update Jira task ownership
    - Consider skills, availability, and current workload
    
    Input: Story list, team data
    Output: Updated assignments, priority queue
    """
    
    # Maximum story points any single person can be assigned
    MAX_STORY_POINTS_PER_PERSON = 5

    def __init__(self):
        """Initialize Prioritization Agent."""
        super().__init__(agent_name="PrioritizationAgent")
        
        self.system_prompt = """You are an expert Scrum Master specialized in task allocation and team optimization.

Your goal is to:
1. Match tasks to team members based on their ROLE and SKILLS (Developer, QA, DevOps, etc.)
eal-world Impact / Use Case
eal-world Impact / Use Case
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    ~~~~~~~~~~~~~~~~~~~~~~~~    ``````````````````````````````````````````````````````````````````````````````              
3. Consider individual experience level (Junior, Mid, Senior)
4. Prioritize critical path items
5. Identify potential bottlenecks

STRICT RULES:
- **MANDATORY: Every story MUST have an assignee - NO EXCEPTIONS**
- Maximum 5 story points per team member (preferred, but can be exceeded if necessary to ensure assignment)
- Match developer stories to developers
- Match testing stories to QA/testers
- Match DevOps/infrastructure stories to DevOps engineers
- Distribute evenly across team
- If all team members are at capacity, assign to the least loaded member (even if it exceeds 5pt limit)

Use data-driven decisions to optimize team velocity and prevent burnout. Never leave a story unassigned."""

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute prioritization and assignment logic.
        
        Args:
            input_data: {
                "stories": List[Dict],
                "team_members": List[Dict],
                "sprint_capacity": int (optional)
            }
            
        Returns:
            {
                "assignments": List[Dict],
                "unassigned_stories": List[Dict],
                "team_load": Dict[str, Any],
                "warnings": List[str]
            }
        """
        import logging
        logger = logging.getLogger(__name__)
        
        stories = input_data.get("stories", [])
        team_members = input_data.get("team_members", [])
        sprint_capacity = input_data.get("sprint_capacity")
        
        logger.info(f"📋 [PRIORITY EXEC] Input stories type: {type(stories)}, length: {len(stories)}")
        if stories and len(stories) > 0:
            logger.info(f"📋 [PRIORITY EXEC] First story type: {type(stories[0])}, content: {stories[0]}")
        
        # Validate stories format
        if not isinstance(stories, list):
            logger.error(f"❌ [PRIORITY EXEC] Stories is not a list: {type(stories)}")
            raise ValueError(f"Stories must be a list, got {type(stories)}")
        
        # Ensure all stories are dicts
        validated_stories = []
        for idx, story in enumerate(stories):
            if isinstance(story, dict):
                validated_stories.append(story)
            else:
                logger.warning(f"⚠️ [PRIORITY EXEC] Story {idx} is not a dict: {type(story)}, skipping")
        
        logger.info(f"✅ [PRIORITY EXEC] Validated {len(validated_stories)} stories")
        
        # Calculate effective capacity for each team member
        team_with_capacity = self._calculate_effective_capacity(team_members)
        
        # Prioritize stories
        prioritized_stories = self._prioritize_stories(validated_stories)
        
        # Assign stories to team members
        assignments = self._assign_stories(prioritized_stories, team_with_capacity)
        
        # Calculate team load distribution
        team_load = self._calculate_team_load(assignments, team_with_capacity)
        
        # Identify warnings
        warnings = self._generate_warnings(team_load, sprint_capacity, assignments)
        
        # Get unassigned stories
        assigned_story_ids = {a["story_id"] for a in assignments if a.get("assignee")}
        unassigned_stories = []
        for idx, s in enumerate(validated_stories):
            # Check both actual ID and index
            story_identifier = s.get("id", idx)
            if story_identifier not in assigned_story_ids:
                unassigned_stories.append(s)
        
        return {
            "assignments": assignments,
            "unassigned_stories": unassigned_stories,
            "team_load": team_load,
            "warnings": warnings
        }

    def _calculate_effective_capacity(
        self,
        team_members: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Calculate effective capacity for each team member.
        
        Formula: EffectiveCapacity = MaxCapacity × (1 - CurrentLoad)
        
        Args:
            team_members: List of team member dictionaries
            
        Returns:
            Team members with calculated effective capacity
        """
        for member in team_members:
            max_capacity = member.get("max_capacity", 40)  # Default 40 hours
            current_load = member.get("current_load", 0)  # Story points or hours
            current_load_ratio = min(current_load / max_capacity, 1.0) if max_capacity > 0 else 0
            
            effective_capacity = max_capacity * (1 - current_load_ratio)
            member["effective_capacity"] = max(effective_capacity, 0)
            member["load_ratio"] = current_load_ratio
        
        return team_members

    def _prioritize_stories(self, stories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Prioritize stories based on priority, dependencies, and story points.
        
        Args:
            stories: List of story dictionaries
            
        Returns:
            Sorted list of stories
        """
        import logging
        logger = logging.getLogger(__name__)
        
        priority_map = {"high": 3, "medium": 2, "low": 1}
        
        def priority_score(story):
            # Ensure story is a dict
            if not isinstance(story, dict):
                logger.warning(f"⚠️ Story in priority_score is not a dict: {type(story)}")
                return 0
            
            priority = story.get("priority", "medium")
            priority_value = priority_map.get(priority, 2)
            has_dependencies = len(story.get("dependencies", [])) > 0
            story_points = story.get("story_points", 3)
            
            # Higher priority and fewer dependencies come first
            # Smaller stories slightly preferred for quick wins
            score = (priority_value * 100) - (10 if has_dependencies else 0) - (story_points * 0.5)
            return -score  # Negative for descending order
        
        try:
            return sorted(stories, key=priority_score)
        except Exception as e:
            logger.error(f"❌ Error prioritizing stories: {str(e)}")
            return stories  # Return as-is if sorting fails

    def _assign_stories(
        self,
        stories: List[Dict[str, Any]],
        team_members: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Assign stories to team members based on skills and capacity.
        
        Args:
            stories: Prioritized list of stories
            team_members: Team members with effective capacity
            
        Returns:
            List of assignment dictionaries
        """
        import logging
        logger = logging.getLogger(__name__)
        
        assignments = []
        
        logger.info(f"📋 [ASSIGN] Starting assignment for {len(stories)} stories to {len(team_members)} team members")
        
        # Sort team members by effective capacity (descending)
        sorted_team = sorted(
            team_members,
            key=lambda m: m.get("effective_capacity", 0),
            reverse=True
        )
        
        if sorted_team:
            logger.info(f"👥 [ASSIGN] Team sorted by capacity: {[(m.get('name'), m.get('effective_capacity')) for m in sorted_team[:3]]}")
        
        for idx, story in enumerate(stories):
            # Use index as story_id for preview stories (not yet saved to DB)
            # Or use actual ID if story has one (from DB)
            story_id = story.get("id", idx)
            story_title = story.get("title", "")
            story_description = story.get("description", "")
            story_points = story.get("story_points", 3)
            
            # Extract required skills from story text
            required_skills = self._extract_required_skills(story_title, story_description)
            logger.info(f"  📋 Story {idx}: requires skills: {required_skills}")
            
            # Find best match (returns index and match data)
            best_match_idx, best_match_data = self._find_best_assignee(
                story,
                sorted_team,
                required_skills,
                story_points
            )
            
            if best_match_idx is not None:
                # Update the ACTUAL team member in the list (not a copy)
                assignee = sorted_team[best_match_idx]["name"]
                assignee_email = sorted_team[best_match_idx].get("email", "")
                confidence = best_match_data.get("match_confidence", 0)
                previous_load = sorted_team[best_match_idx].get("current_load", 0)
                
                # Update the team member's load IN PLACE
                sorted_team[best_match_idx]["effective_capacity"] -= story_points
                sorted_team[best_match_idx]["current_load"] = previous_load + story_points
                
                logger.info(f"  ✅ Story {idx}: '{story_title[:40]}...' → {assignee} (role: {sorted_team[best_match_idx].get('job_title', 'N/A')}, {confidence:.2f} confidence, {story_points} pts, total: {sorted_team[best_match_idx]['current_load']}/5)")
                
                assignee_id = sorted_team[best_match_idx].get("id")
            else:
                # FALLBACK: Always assign to least loaded team member (even if at capacity)
                # This ensures no story is left unassigned
                if sorted_team:
                    # Find the member with the least current load
                    fallback_idx = min(
                        range(len(sorted_team)),
                        key=lambda i: sorted_team[i].get("current_load", 0)
                    )
                    assignee = sorted_team[fallback_idx]["name"]
                    assignee_email = sorted_team[fallback_idx].get("email", "")
                    assignee_id = sorted_team[fallback_idx].get("id")
                    confidence = 0.3  # Low confidence for fallback assignment
                    previous_load = sorted_team[fallback_idx].get("current_load", 0)
                    
                    # Update the team member's load IN PLACE (even if it exceeds 5pt limit)
                    sorted_team[fallback_idx]["effective_capacity"] = max(0, sorted_team[fallback_idx].get("effective_capacity", 0) - story_points)
                    sorted_team[fallback_idx]["current_load"] = previous_load + story_points
                    
                    logger.warning(f"  ⚠️ Story {idx}: '{story_title[:40]}...' → {assignee} (FALLBACK - all members at/over capacity, assigned to least loaded: {previous_load} + {story_points} = {sorted_team[fallback_idx]['current_load']} pts)")
                else:
                    # No team members available - this should never happen, but handle it
                    assignee = None
                    assignee_email = None
                    assignee_id = None
                    confidence = 0
                    logger.error(f"  ❌ Story {idx}: '{story_title[:40]}...' → UNASSIGNED (no team members available)")
            
            assignments.append({
                "story_id": story_id,
                "story_title": story_title,
                "story_points": story_points,
                "priority": story.get("priority", "medium"),
                "assignee": assignee,
                "assignee_email": assignee_email,
                "assignee_id": assignee_id,
                "confidence": confidence
            })
        
        logger.info(f"✅ [ASSIGN] Completed: {sum(1 for a in assignments if a['assignee'])} assigned, {sum(1 for a in assignments if not a['assignee'])} unassigned")
        return assignments

    def _extract_required_skills(self, title: str, description: str) -> List[str]:
        """
        Extract required skills from story title and description.
        
        Args:
            title: Story title
            description: Story description
            
        Returns:
            List of required skills/roles
        """
        text = f"{title} {description}".lower()
        skills = []
        
        # Developer keywords
        if any(keyword in text for keyword in ["develop", "code", "implement", "backend", "frontend", "api", "database", "feature"]):
            skills.append("development")
            skills.append("developer")
        
        # Testing keywords
        if any(keyword in text for keyword in ["test", "qa", "quality", "verify", "validation", "automat"]):
            skills.append("testing")
            skills.append("qa")
            skills.append("tester")
        
        # DevOps keywords
        if any(keyword in text for keyword in ["deploy", "devops", "infrastructure", "ci/cd", "pipeline", "monitor", "alert"]):
            skills.append("devops")
            skills.append("infrastructure")
        
        # UI/UX keywords
        if any(keyword in text for keyword in ["ui", "ux", "design", "interface", "user experience", "dashboard"]):
            skills.append("frontend")
            skills.append("ui")
        
        # Architecture keywords
        if any(keyword in text for keyword in ["architect", "design", "scalab", "system design", "integration"]):
            skills.append("architecture")
            skills.append("senior")
        
        return list(set(skills))  # Remove duplicates
    
    def _find_best_assignee(
        self,
        story: Dict[str, Any],
        team_members: List[Dict[str, Any]],
        required_skills: List[str],
        story_points: int
    ) -> tuple[Optional[int], Optional[Dict[str, Any]]]:
        """
        Find best team member for a story based on skills, role, and capacity.
        STRICT LIMIT: No team member can exceed 5 story points total.
        
        Args:
            story: Story dictionary
            team_members: Available team members
            required_skills: Required skills for the story
            story_points: Story points
            
        Returns:
            Tuple of (member_index, match_data) or (None, None)
        """
        import logging
        logger = logging.getLogger(__name__)
        
        best_match_idx = None
        best_match_data = None
        best_score = -1
        
        for idx, member in enumerate(team_members):
            # STRICT CHECK: Total load must not exceed MAX_STORY_POINTS_PER_PERSON
            current_load = member.get("current_load", 0)
            if current_load + story_points > self.MAX_STORY_POINTS_PER_PERSON:
                logger.debug(f"Skipping {member.get('name')}: would exceed 5pt limit ({current_load} + {story_points})")
                continue
            
            # Check if member has capacity (effective capacity check)
            if member.get("effective_capacity", 0) < story_points:
                continue
            
            # Extract member skills from job title and skills list
            member_skills = set(member.get("skills", []))
            job_title = member.get("job_title", "").lower()
            
            # Add role-based skills from job title
            if "developer" in job_title or "engineer" in job_title:
                member_skills.add("developer")
                member_skills.add("development")
            if "qa" in job_title or "test" in job_title:
                member_skills.add("qa")
                member_skills.add("testing")
                member_skills.add("tester")
            if "devops" in job_title:
                member_skills.add("devops")
                member_skills.add("infrastructure")
            if "architect" in job_title:
                member_skills.add("architecture")
                member_skills.add("senior")
            
            # Calculate skill match
            required_skills_set = set(required_skills)
            skill_overlap = len(member_skills.intersection(required_skills_set))
            
            # If no required skills specified, give base score
            if not required_skills_set:
                skill_score = 0.5
            else:
                skill_score = skill_overlap / len(required_skills_set)
            
            # STRONG preference for role match
            role_bonus = 1.0
            if required_skills_set and skill_overlap > 0:
                role_bonus = 2.0  # Double the score for role match
            
            # Calculate workload balance score (prefer less loaded members)
            load_ratio = current_load / self.MAX_STORY_POINTS_PER_PERSON
            balance_score = 1 - load_ratio
            
            # Experience level bonus
            experience_level = member.get("experience_level", "mid")
            experience_bonus = {"junior": 0.8, "mid": 1.0, "senior": 1.2}.get(experience_level, 1.0)
            
            # Combined score - HEAVILY weight role match and load balance
            score = (skill_score * role_bonus * 0.6) + (balance_score * 0.3) + (experience_bonus * 0.1)
            
            logger.debug(f"  {member.get('name')}: skill={skill_score:.2f}, role_bonus={role_bonus}, balance={balance_score:.2f}, exp={experience_bonus}, total={score:.2f}")
            
            if score > best_score:
                best_score = score
                best_match_idx = idx
                best_match_data = {"match_confidence": score}
        
        return best_match_idx, best_match_data

    def _calculate_team_load(
        self,
        assignments: List[Dict[str, Any]],
        team_members: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculate team load distribution.
        
        Args:
            assignments: List of assignments
            team_members: Team members
            
        Returns:
            Team load statistics
        """
        member_loads = {}
        
        for member in team_members:
            member_id = member.get("id")
            member_name = member.get("name")
            member_loads[member_name] = {
                "current_load": member.get("current_load", 0),
                "max_capacity": member.get("max_capacity", 40),
                "load_percentage": (member.get("current_load", 0) / member.get("max_capacity", 40)) * 100,
                "assigned_stories": 0
            }
        
        # Count assigned stories
        for assignment in assignments:
            assignee = assignment.get("assignee")
            if assignee and assignee in member_loads:
                member_loads[assignee]["assigned_stories"] += 1
        
        # Calculate team-wide statistics
        total_load = sum(m["current_load"] for m in member_loads.values())
        total_capacity = sum(m["max_capacity"] for m in member_loads.values())
        avg_load_percentage = (total_load / total_capacity * 100) if total_capacity > 0 else 0
        
        return {
            "team_members": member_loads,
            "total_load": total_load,
            "total_capacity": total_capacity,
            "avg_load_percentage": avg_load_percentage,
            "team_size": len(team_members)
        }

    def _generate_warnings(
        self,
        team_load: Dict[str, Any],
        sprint_capacity: Optional[int],
        assignments: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Generate warnings for potential issues.
        
        Args:
            team_load: Team load statistics
            sprint_capacity: Sprint capacity
            assignments: Assignments
            
        Returns:
            List of warning messages
        """
        warnings = []
        
        # Check for overloaded team members
        for member_name, load_info in team_load["team_members"].items():
            if load_info["load_percentage"] > 90:
                warnings.append(f"⚠️ {member_name} is overloaded ({load_info['load_percentage']:.1f}% capacity)")
            elif load_info["load_percentage"] > 80:
                warnings.append(f"⚡ {member_name} is near capacity ({load_info['load_percentage']:.1f}%)")
        
        # Check for underutilized team members
        for member_name, load_info in team_load["team_members"].items():
            if load_info["load_percentage"] < 50 and load_info["max_capacity"] > 0:
                warnings.append(f"📊 {member_name} has available capacity ({load_info['load_percentage']:.1f}%)")
        
        # Check for unassigned stories
        unassigned_count = sum(1 for a in assignments if not a.get("assignee"))
        if unassigned_count > 0:
            warnings.append(f"❌ {unassigned_count} stories could not be assigned due to capacity constraints")
        
        # Check sprint capacity
        if sprint_capacity:
            total_story_points = sum(a["story_points"] for a in assignments)
            if total_story_points > sprint_capacity:
                warnings.append(f"🚨 Total story points ({total_story_points}) exceed sprint capacity ({sprint_capacity})")
        
        return warnings

