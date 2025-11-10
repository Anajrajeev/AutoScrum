# backend/routes/transcript_routes.py
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Any, Dict, List
import asyncio
import logging
import sqlite3
import json
from pathlib import Path

from agents.dynamic_transcript_agent import analyze_transcript_json

logger = logging.getLogger("autoscrum.routes")
router = APIRouter()

# Pydantic model for validation (loose)
class TranscriptPayload(BaseModel):
    sprint_id: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    project_key: str
    team: list
    transcripts: list

class WeekAnalysisRequest(BaseModel):
    week_identifier: str

class WeekData(BaseModel):
    week_identifier: str
    start_date: str
    end_date: str

@router.post("/api/analyze-transcripts")
async def analyze_transcripts(payload: TranscriptPayload):
    try:
        # convert to plain dict
        data: Dict[str, Any] = payload.dict()
        # run analysis
        result = await analyze_transcript_json(data)
        return result
    except Exception as e:
        logger.exception("Error analyzing transcripts: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/transcript/weeks")
async def get_weeks():
    """Get all available weeks from the database."""
    try:
        db_path = Path(__file__).parent.parent / "autoscrum.db"
        logger.info(f"Using database path: {db_path}")
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Create table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS weekly_standups (
                week_identifier TEXT PRIMARY KEY,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                json_data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()  # Ensure table is created

        cursor.execute("""
            SELECT week_identifier, start_date, end_date
            FROM weekly_standups
            ORDER BY start_date DESC
        """)

        weeks = cursor.fetchall()
        conn.close()

        # Convert to list of dicts
        result = [
            {
                "week_identifier": row[0],
                "start_date": row[1],
                "end_date": row[2],
                "display_name": f"Week of {row[1]} to {row[2]}"
            }
            for row in weeks
        ]

        return {"weeks": result}

    except Exception as e:
        logger.exception("Error fetching weeks: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to fetch weeks: {str(e)}")

@router.post("/api/transcript/analyze")
async def analyze_week(request: WeekAnalysisRequest):
    """Run transcript analysis for a specific week."""
    try:
        db_path = Path(__file__).parent.parent / "autoscrum.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Get the week's data
        cursor.execute("""
            SELECT json_data FROM weekly_standups
            WHERE week_identifier = ?
        """, (request.week_identifier,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail=f"Week {request.week_identifier} not found")

        # Parse the JSON data
        week_data = json.loads(row[0])

        # Run the analysis
        result = await analyze_transcript_json(week_data)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error analyzing week: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to analyze week: {str(e)}")
