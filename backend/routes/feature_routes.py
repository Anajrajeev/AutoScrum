"""Feature-related API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import logging
import json

from db.database import get_db
from db import models, schemas
from orchestrator import get_orchestrator

router = APIRouter(prefix="/api/features", tags=["features"])
logger = logging.getLogger(__name__)


@router.post("/create", response_model=schemas.FeatureResponse)
async def create_feature(
    feature: schemas.FeatureCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new feature.
    
    This initiates the clarification workflow.
    """
    logger.info(f"🎬 [CREATE FEATURE] Starting feature creation: {feature.name}")
    
    # Create feature in database
    db_feature = models.Feature(
        name=feature.name,
        description=feature.description
    )
    db.add(db_feature)
    db.commit()
    db.refresh(db_feature)
    logger.info(f"✅ [CREATE FEATURE] Feature saved to DB with ID: {db_feature.id}")
    
    # Start clarification workflow
    logger.info(f"🤖 [CREATE FEATURE] Starting clarification workflow for feature {db_feature.id}")
    orchestrator = get_orchestrator()
    workflow_result = await orchestrator.run_feature_workflow(
        feature_id=db_feature.id,
        feature_name=feature.name,
        feature_description=feature.description
    )
    
    logger.info(f"📝 [CREATE FEATURE] Workflow result: status={workflow_result.get('status')}, question={workflow_result.get('question')[:50] if workflow_result.get('question') else None}...")
    
    # Convert to response and include first question
    response = schemas.FeatureResponse.model_validate(db_feature)
    
    # Add first clarification question to response
    response_data = response.model_dump()
    response_data["first_question"] = workflow_result.get("question")
    response_data["workflow_id"] = workflow_result.get("workflow_id")
    
    logger.info(f"✅ [CREATE FEATURE] Returning response with workflow_id: {response_data.get('workflow_id')}")
    
    # Create new FeatureResponse object with all fields
    return schemas.FeatureResponse(**response_data)


@router.post("/clarify", response_model=schemas.ClarificationResponse)
async def clarify_feature(
    clarification: schemas.ClarificationRequest,
    db: Session = Depends(get_db)
):
    """
    Continue feature clarification conversation.
    
    Responds with next question or completion signal.
    """
    response_length = len(clarification.user_response) if clarification.user_response else 0
    logger.info(f"[CLARIFY] Feature {clarification.feature_id}: User response received (length: {response_length})")
    
    # Get feature from database
    feature = db.query(models.Feature).filter(
        models.Feature.id == clarification.feature_id
    ).first()
    
    if not feature:
        logger.error(f"❌ [CLARIFY] Feature {clarification.feature_id} not found in database")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feature not found"
        )
    
    # Get orchestrator and continue clarification
    orchestrator = get_orchestrator()
    
    # Get the original workflow ID from Redis context
    context = orchestrator.redis_client.get_feature_context(clarification.feature_id)
    workflow_id = context.get("workflow_id") if context else None
    logger.info(f"🔍 [CLARIFY] Retrieved workflow_id from Redis: {workflow_id}")
    
    # If no workflow ID exists, create one (fallback)
    if not workflow_id:
        workflow_id = f"feature_{clarification.feature_id}"
        logger.warning(f"⚠️ [CLARIFY] No workflow_id in Redis, using fallback: {workflow_id}")
    
    result = await orchestrator.continue_clarification(
        workflow_id=workflow_id,
        feature_id=clarification.feature_id,
        user_response=clarification.user_response
    )
    
    logger.info(f"📊 [CLARIFY] Clarification result: is_complete={result.get('is_complete')}, has_question={bool(result.get('question'))}")
    
    # Update feature context if complete
    if result.get("is_complete"):
        logger.info(f"✅ [CLARIFY] Clarification COMPLETE for feature {clarification.feature_id}")
        # Get context summary from Redis
        context = orchestrator.redis_client.get_feature_context(clarification.feature_id)
        logger.info(f"📦 [CLARIFY] Retrieved context from Redis: {list(context.keys()) if context else 'None'}")
        
        # Validate that context has the required fields
        required_fields = ["goals", "user_personas", "key_features", "acceptance_criteria", "technical_constraints", "success_metrics"]
        
        if context:
            # Check if context has the complete structured fields
            if "context_summary" in context:
                summary_block = context["context_summary"]
                if isinstance(summary_block, dict) and all(f in summary_block for f in required_fields):
                    feature.context_json = summary_block
                    logger.info(f"💾 [CLARIFY] Saved nested context_summary to DB with all required fields")
                    db.commit()
                else:
                    missing = [f for f in required_fields if f not in (summary_block if isinstance(summary_block, dict) else {})]
                    logger.error(f"❌ [CLARIFY] context_summary missing required fields: {missing}")
            elif all(f in context for f in required_fields):
                # Context is already the complete summary
                feature.context_json = context
                logger.info(f"💾 [CLARIFY] Saved direct context to DB with all required fields")
                db.commit()
            else:
                missing = [f for f in required_fields if f not in context]
                logger.error(f"❌ [CLARIFY] Context missing required fields: {missing}. Keys: {list(context.keys())}")
        else:
            logger.error(f"❌ [CLARIFY] No context found in Redis for feature {clarification.feature_id}")
    
    # Get context summary if available
    context = orchestrator.redis_client.get_feature_context(clarification.feature_id)
    if context:
        # Return nested context_summary if exists, otherwise return context itself
        context_summary = context.get("context_summary") if "context_summary" in context else context
        logger.info(f"📤 [CLARIFY] Returning context_summary: {bool(context_summary)}")
    else:
        context_summary = None
        logger.warning(f"⚠️ [CLARIFY] No context to return")
    
    return schemas.ClarificationResponse(
        feature_id=clarification.feature_id,
        question=result.get("question"),
        is_complete=result.get("is_complete", False),
        context_summary=context_summary
    )


@router.post("/{feature_id}/generate-stories-preview")
async def generate_stories_preview(
    feature_id: int,
    db: Session = Depends(get_db)
):
    """
    Generate stories preview from clarified feature context.
    
    Returns stories WITHOUT saving to database or pushing to Jira.
    User must approve before final creation.
    """
    logger.info(f"📖 [STORIES PREVIEW] Starting story generation for feature {feature_id}")
    
    # Get feature
    feature = db.query(models.Feature).filter(
        models.Feature.id == feature_id
    ).first()
    
    if not feature:
        logger.error(f"❌ [STORIES PREVIEW] Feature {feature_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feature not found"
        )
    
    logger.info(f"🔍 [STORIES PREVIEW] Feature context_json exists: {bool(feature.context_json)}")
    if feature.context_json:
        logger.info(f"📦 [STORIES PREVIEW] Context keys: {list(feature.context_json.keys()) if isinstance(feature.context_json, dict) else 'Not a dict'}")
    
    if not feature.context_json:
        logger.error(f"❌ [STORIES PREVIEW] Feature {feature_id} has no context_json")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Feature context not complete. Please complete clarification first."
        )
    
    # Generate stories (preview only)
    logger.info(f"🤖 [STORIES PREVIEW] Calling Story Creator Agent for feature {feature_id}")
    orchestrator = get_orchestrator()
    result = await orchestrator.generate_stories_from_context(
        feature_id=feature_id,
        auto_push_to_jira=False
    )
    
    logger.info(f"📊 [STORIES PREVIEW] Generation result status: {result.get('status')}")
    
    if result["status"] == "failed":
        logger.error(f"❌ [STORIES PREVIEW] Story generation failed: {result.get('error')}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "Story generation failed")
        )
    
    # Fix: result["stories"] is already a list, not a dict
    stories_list = result["stories"]
    story_count = len(stories_list)
    logger.info(f"✅ [STORIES PREVIEW] Generated {story_count} stories")
    
    # Return preview without saving
    return {
        "feature_id": feature_id,
        "stories": stories_list,  # Pass the list directly
        "epic_summary": result.get("epic", {}).get("description") if result.get("epic") else None,
        "workflow_id": result.get("workflow_id"),
        "status": "preview"
    }


@router.post("/{feature_id}/prioritize-preview")
async def prioritize_stories_preview(
    feature_id: int,
    stories: List[Dict],
    db: Session = Depends(get_db)
):
    """
    Generate prioritization preview for stories.
    
    Returns story assignments WITHOUT saving to database or pushing to Jira.
    User must approve before final assignment.
    """
    logger.info(f"🎯 [PRIORITIZATION] Starting prioritization for feature {feature_id} with {len(stories)} stories")
    
    # Validate stories list
    if not stories or len(stories) == 0:
        logger.error(f"❌ [PRIORITIZATION] No stories provided for prioritization")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No stories to prioritize. Please generate stories first."
        )
    
    # Get feature
    feature = db.query(models.Feature).filter(
        models.Feature.id == feature_id
    ).first()
    
    if not feature:
        logger.error(f"❌ [PRIORITIZATION] Feature {feature_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feature not found"
        )
    
    # Run prioritization
    logger.info(f"🤖 [PRIORITIZATION] Calling Prioritization Agent")
    orchestrator = get_orchestrator()
    result = await orchestrator.run_prioritization_workflow(
        stories=stories,
        team_id=None,
        auto_assign_to_jira=False
    )
    
    logger.info(f"📊 [PRIORITIZATION] Result status: {result.get('status')}")
    
    if result["status"] == "failed":
        logger.error(f"❌ [PRIORITIZATION] Prioritization failed: {result.get('error')}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "Prioritization failed")
        )
    
    prioritization_data = result.get("prioritization", {})
    assignments = prioritization_data.get("assignments", [])
    logger.info(f"✅ [PRIORITIZATION] Created {len(assignments)} assignments")
    
    # Return preview without saving
    return {
        "feature_id": feature_id,
        "prioritization": prioritization_data,
        "workflow_id": result.get("workflow_id"),
        "status": "preview"
    }


@router.post("/{feature_id}/approve-and-create")
async def approve_and_create_stories(
    feature_id: int,
    stories: List[Dict],
    prioritization: Dict,
    push_to_jira: bool = True,
    db: Session = Depends(get_db)
):
    """
    Approve stories and prioritization, save to database, and push to Jira.
    
    This is the final step after user reviews and approves the preview.
    Stories are automatically assigned to the current active sprint.
    If no sprint exists, Sprint 1 is created automatically.
    """
    logger.info(f"✅ [APPROVE] User approved {len(stories)} stories for feature {feature_id}, push_to_jira={push_to_jira}")
    
    # Get feature
    feature = db.query(models.Feature).filter(
        models.Feature.id == feature_id
    ).first()
    
    if not feature:
        logger.error(f"❌ [APPROVE] Feature {feature_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feature not found"
        )
    
    # ==================================================================
    # AUTO-ASSIGN TO CURRENT SPRINT (or create Sprint 1 as fallback)
    # ==================================================================
    
    # Try to find an active sprint (current date between start and end)
    current_sprint = db.query(models.Sprint).filter(
        models.Sprint.start_date <= datetime.now(),
        models.Sprint.end_date >= datetime.now()
    ).first()
    
    if not current_sprint:
        # Fallback: Try to find the most recently created sprint
        current_sprint = db.query(models.Sprint).order_by(
            models.Sprint.created_at.desc()
        ).first()
        
        if current_sprint:
            logger.info(f"📅 [APPROVE] No active sprint, using most recent: {current_sprint.name}")
    
    if not current_sprint:
        # Fallback: Create "Sprint 1" if no sprints exist at all
        logger.info("📅 [APPROVE] No sprints found in database, creating Sprint 1")
        current_sprint = models.Sprint(
            name="Sprint 1",
            start_date=datetime.now(),
            end_date=datetime.now() + timedelta(days=14),  # 2-week sprint
            velocity=40  # Default velocity
        )
        db.add(current_sprint)
        db.commit()
        db.refresh(current_sprint)
        logger.info(f"✅ [APPROVE] Created Sprint 1 (ID: {current_sprint.id})")
    
    sprint_id = current_sprint.id
    logger.info(f"📌 [APPROVE] Assigning all stories to sprint: '{current_sprint.name}' (ID: {sprint_id})")
    
    try:
        logger.info(f"💾 [APPROVE] Saving {len(stories)} stories to database")
        # Save stories to database
        db_stories = []
        story_id_map = {}  # Map temp IDs to DB IDs
        
        for idx, story_dict in enumerate(stories):
            # Find assignee from prioritization - prefer email over display name
            assignee = None
            for assignment in prioritization.get("assignments", []):
                if assignment.get("story_id") == idx or assignment.get("story_title") == story_dict.get("title"):
                    # Prefer email if available, fallback to display name
                    assignee = assignment.get("assignee_email") or assignment.get("assignee")
                    logger.info(f"[APPROVE] Story {idx}: assignee_email={assignment.get('assignee_email')}, assignee={assignment.get('assignee')}, using={assignee}")
                    break
            
            # VALIDATION: Ensure assignee is always set (compulsory field)
            if not assignee:
                # Try to find any available assignee from other assignments
                for assignment in prioritization.get("assignments", []):
                    if assignment.get("assignee_email") or assignment.get("assignee"):
                        assignee = assignment.get("assignee_email") or assignment.get("assignee")
                        logger.warning(f"[APPROVE] Story {idx} had no assignee, using fallback: {assignee}")
                        break
                
                # If still no assignee, raise an error
                if not assignee:
                    error_msg = f"Story '{story_dict.get('title', 'Unknown')}' cannot be created without an assignee. All stories must have an assignee."
                    logger.error(f"[APPROVE] {error_msg}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=error_msg
                    )
            
            db_story = models.Story(
                feature_id=feature_id,
                title=story_dict["title"],
                description=story_dict["description"],
                acceptance_criteria=story_dict.get("acceptance_criteria", []),
                story_points=story_dict.get("story_points", 3),
                assignee=assignee,
                status=models.StoryStatus.TODO,
                sprint_id=sprint_id  # ✅ AUTO-ASSIGN TO SPRINT
            )
            db.add(db_story)
            db_stories.append(db_story)
            story_id_map[idx] = db_story
        
        db.commit()
        logger.info(f"✅ [APPROVE] Saved {len(db_stories)} stories to sprint '{current_sprint.name}'")
        
        # Refresh to get IDs
        for story in db_stories:
            db.refresh(story)
        
        # Push to Jira if requested
        jira_results = []
        if push_to_jira:
            logger.info(f"🚀 [APPROVE] Pushing {len(db_stories)} stories to Jira")
            orchestrator = get_orchestrator()
            jira_client = orchestrator.jira_client
            
            # Get project key from config
            project_key = jira_client.config.default_project
            if not project_key:
                logger.error("[JIRA] No JIRA_DEFAULT_PROJECT configured in environment")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Jira project not configured. Please set JIRA_DEFAULT_PROJECT environment variable."
                )
            
            logger.info(f"[JIRA] Using project key: {project_key}")
            
            for idx, story in enumerate(db_stories):
                try:
                    logger.info(f"[JIRA] Creating story {idx+1}/{len(db_stories)}: '{story.title[:50]}...'")
                    logger.info(f"[JIRA] Story details - points: {story.story_points}, assignee: '{story.assignee}'")
                    
                    # Create story in Jira using the new API
                    jira_result = await jira_client.create_story(
                        project_key=project_key,
                        summary=story.title,
                        description=story.description,
                        story_points=story.story_points,
                        assignee=story.assignee
                    )
                    
                    logger.info(f"[JIRA] Result for story {idx+1}: success={jira_result.get('success')}, key={jira_result.get('key')}")
                    
                    if jira_result.get("success"):
                        # Update story with Jira key
                        story.jira_key = jira_result.get("key")
                        jira_results.append({
                            "story_id": story.id,
                            "jira_key": jira_result.get("key"),
                            "success": True
                        })
                        logger.info(f"✅ [JIRA] Successfully created {jira_result.get('key')}")
                    else:
                        error_msg = jira_result.get("error", "Unknown error")
                        error_details = jira_result.get("details", {})
                        logger.error(f"❌ [JIRA] Failed to create story: {error_msg}")
                        logger.error(f"[JIRA] Error details: {json.dumps(error_details, indent=2)}")
                        jira_results.append({
                            "story_id": story.id,
                            "success": False,
                            "error": error_msg
                        })
                except Exception as e:
                    logger.error(f"[JIRA] Exception creating story: {str(e)}", exc_info=True)
                    jira_results.append({
                        "story_id": story.id,
                        "success": False,
                        "error": str(e)
                    })
            
            db.commit()
            
            success_count = sum(1 for r in jira_results if r.get("success"))
            logger.info(f"✅ [APPROVE] Pushed {success_count}/{len(jira_results)} stories to Jira successfully")
        
        # Convert to response schemas
        story_responses = [
            schemas.StoryResponse.model_validate(story)
            for story in db_stories
        ]
        
        logger.info(f"🎉 [APPROVE] Complete! Created {len(story_responses)} stories in '{current_sprint.name}', pushed_to_jira={push_to_jira}")
        
        return {
            "feature_id": feature_id,
            "stories": story_responses,
            "sprint_id": sprint_id,
            "sprint_name": current_sprint.name,
            "jira_results": jira_results if push_to_jira else [],
            "status": "created",
            "pushed_to_jira": push_to_jira
        }
    
    except Exception as e:
        logger.error(f"❌ [APPROVE] Failed to create stories: {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create stories: {str(e)}"
        )


@router.get("/{feature_id}", response_model=schemas.FeatureResponse)
async def get_feature(feature_id: int, db: Session = Depends(get_db)):
    """Get feature by ID."""
    feature = db.query(models.Feature).filter(
        models.Feature.id == feature_id
    ).first()
    
    if not feature:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feature not found"
        )
    
    return feature


@router.get("/", response_model=List[schemas.FeatureResponse])
async def list_features(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all features."""
    features = db.query(models.Feature).offset(skip).limit(limit).all()
    return features


@router.get("/{feature_id}/stories", response_model=List[schemas.StoryResponse])
async def get_feature_stories(
    feature_id: int,
    db: Session = Depends(get_db)
):
    """Get all stories for a feature."""
    stories = db.query(models.Story).filter(
        models.Story.feature_id == feature_id
    ).all()
    return stories


@router.delete("/{feature_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feature(feature_id: int, db: Session = Depends(get_db)):
    """Delete a feature and its stories."""
    feature = db.query(models.Feature).filter(
        models.Feature.id == feature_id
    ).first()
    
    if not feature:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feature not found"
        )
    
    db.delete(feature)
    db.commit()
    
    return None

