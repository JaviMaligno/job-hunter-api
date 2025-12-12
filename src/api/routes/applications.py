"""Application automation API routes."""

import logging
from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from src.agents.form_filler import FormFillerAgent, FormFillerInput, FormFillerOutput
from src.api.dependencies import ClaudeDep
from src.automation.models import UserFormData
from src.db.models import ApplicationMode, ApplicationStatus, BlockerType

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# In-Memory Session Store (replace with DB in production)
# ============================================================================

_application_sessions: dict[str, "ApplicationSession"] = {}


class ApplicationSession(BaseModel):
    """Application session state."""

    session_id: str
    job_url: str
    status: ApplicationStatus = ApplicationStatus.PENDING
    mode: ApplicationMode = ApplicationMode.ASSISTED
    browser_session_id: str | None = None
    current_step: int = 1
    total_steps: int | None = None
    fields_filled: dict[str, str] = Field(default_factory=dict)
    blocker_type: BlockerType | None = None
    blocker_message: str | None = None
    screenshot_path: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    paused_at: datetime | None = None
    completed_at: datetime | None = None


# ============================================================================
# Request/Response Models
# ============================================================================


class StartApplicationRequest(BaseModel):
    """Request to start a job application."""

    job_url: str
    user_data: UserFormData
    cv_content: str
    cv_file_path: str | None = None
    cover_letter: str | None = None
    mode: ApplicationMode = ApplicationMode.ASSISTED
    headless: bool = False  # Default visible for assisted mode


class ApplicationStatusResponse(BaseModel):
    """Response with application status."""

    session_id: str
    status: ApplicationStatus
    job_url: str
    mode: ApplicationMode
    current_step: int
    total_steps: int | None = None
    fields_filled: int = 0
    blocker_type: BlockerType | None = None
    blocker_message: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class ResumeApplicationRequest(BaseModel):
    """Request to resume a paused application."""

    action: str = "continue"  # continue, submit, cancel


# ============================================================================
# API Endpoints
# ============================================================================


@router.post("/", response_model=ApplicationStatusResponse)
async def start_application(
    request: StartApplicationRequest,
    claude: ClaudeDep,
):
    """Start a new job application.

    This endpoint:
    1. Creates a browser session
    2. Navigates to the job URL
    3. Detects ATS type and analyzes form
    4. Starts auto-filling the application
    5. Pauses for user review before submit (in assisted mode)

    Returns session ID for tracking progress.
    """
    session_id = str(uuid4())

    # Create session record
    session = ApplicationSession(
        session_id=session_id,
        job_url=request.job_url,
        status=ApplicationStatus.IN_PROGRESS,
        mode=request.mode,
    )
    _application_sessions[session_id] = session

    try:
        # Create form filler input
        filler_input = FormFillerInput(
            application_url=request.job_url,
            user_data=request.user_data,
            cv_content=request.cv_content,
            cv_file_path=request.cv_file_path,
            cover_letter=request.cover_letter,
            mode=request.mode,
            headless=request.headless,
        )

        # Run form filler agent
        agent = FormFillerAgent(claude_api_key=claude.api_key)
        result: FormFillerOutput = await agent.run(filler_input)

        # Update session with result
        session.status = result.status
        session.browser_session_id = result.browser_session_id
        session.current_step = result.current_step
        session.total_steps = result.total_steps
        session.fields_filled = result.fields_filled
        session.blocker_type = result.blocker_detected
        session.screenshot_path = result.screenshot_path
        session.updated_at = datetime.utcnow()

        if result.status == ApplicationStatus.PAUSED:
            session.paused_at = datetime.utcnow()
        elif result.status == ApplicationStatus.SUBMITTED:
            session.completed_at = datetime.utcnow()

        if result.error:
            session.error = result.error

    except Exception as e:
        logger.error(f"Application failed: {e}")
        session.status = ApplicationStatus.FAILED
        session.error = str(e)
        session.updated_at = datetime.utcnow()

    return ApplicationStatusResponse(
        session_id=session.session_id,
        status=session.status,
        job_url=session.job_url,
        mode=session.mode,
        current_step=session.current_step,
        total_steps=session.total_steps,
        fields_filled=len(session.fields_filled),
        blocker_type=session.blocker_type,
        blocker_message=session.blocker_message,
        error=session.error,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.get("/{session_id}", response_model=ApplicationStatusResponse)
async def get_application_status(session_id: str):
    """Get status of an application session."""
    session = _application_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Application session not found")

    return ApplicationStatusResponse(
        session_id=session.session_id,
        status=session.status,
        job_url=session.job_url,
        mode=session.mode,
        current_step=session.current_step,
        total_steps=session.total_steps,
        fields_filled=len(session.fields_filled),
        blocker_type=session.blocker_type,
        blocker_message=session.blocker_message,
        error=session.error,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.get("/", response_model=list[ApplicationStatusResponse])
async def list_applications(
    status: Annotated[ApplicationStatus | None, Query(description="Filter by status")] = None,
):
    """List all application sessions."""
    sessions = list(_application_sessions.values())

    if status:
        sessions = [s for s in sessions if s.status == status]

    return [
        ApplicationStatusResponse(
            session_id=s.session_id,
            status=s.status,
            job_url=s.job_url,
            mode=s.mode,
            current_step=s.current_step,
            total_steps=s.total_steps,
            fields_filled=len(s.fields_filled),
            blocker_type=s.blocker_type,
            blocker_message=s.blocker_message,
            error=s.error,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in sorted(sessions, key=lambda x: x.created_at, reverse=True)
    ]


@router.get("/paused", response_model=list[ApplicationStatusResponse])
async def list_paused_applications():
    """List all paused application sessions."""
    sessions = [s for s in _application_sessions.values() if s.status == ApplicationStatus.PAUSED]

    return [
        ApplicationStatusResponse(
            session_id=s.session_id,
            status=s.status,
            job_url=s.job_url,
            mode=s.mode,
            current_step=s.current_step,
            total_steps=s.total_steps,
            fields_filled=len(s.fields_filled),
            blocker_type=s.blocker_type,
            blocker_message=s.blocker_message,
            error=s.error,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in sorted(sessions, key=lambda x: x.paused_at or x.created_at, reverse=True)
    ]


@router.post("/{session_id}/resume", response_model=ApplicationStatusResponse)
async def resume_application(
    session_id: str,
    request: ResumeApplicationRequest,
    claude: ClaudeDep,
):
    """Resume a paused application session.

    Actions:
    - continue: Continue filling the form
    - submit: Submit the application
    - cancel: Cancel the application
    """
    session = _application_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Application session not found")

    if session.status != ApplicationStatus.PAUSED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume session with status: {session.status}",
        )

    if request.action == "cancel":
        session.status = ApplicationStatus.CANCELLED
        session.updated_at = datetime.utcnow()
        # TODO: Close browser session
        return ApplicationStatusResponse(
            session_id=session.session_id,
            status=session.status,
            job_url=session.job_url,
            mode=session.mode,
            current_step=session.current_step,
            total_steps=session.total_steps,
            fields_filled=len(session.fields_filled),
            blocker_type=session.blocker_type,
            blocker_message=session.blocker_message,
            error=session.error,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

    # TODO: Implement resume logic with FormFillerAgent
    # For now, just update status
    session.status = ApplicationStatus.IN_PROGRESS
    session.paused_at = None
    session.updated_at = datetime.utcnow()

    return ApplicationStatusResponse(
        session_id=session.session_id,
        status=session.status,
        job_url=session.job_url,
        mode=session.mode,
        current_step=session.current_step,
        total_steps=session.total_steps,
        fields_filled=len(session.fields_filled),
        blocker_type=session.blocker_type,
        blocker_message=session.blocker_message,
        error=session.error,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.delete("/{session_id}")
async def cancel_application(session_id: str):
    """Cancel an application session."""
    session = _application_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Application session not found")

    session.status = ApplicationStatus.CANCELLED
    session.updated_at = datetime.utcnow()

    # TODO: Close browser session if active

    return {"status": "cancelled", "session_id": session_id}


@router.get("/{session_id}/screenshot")
async def get_screenshot(session_id: str):
    """Get the latest screenshot for an application session."""
    session = _application_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Application session not found")

    if not session.screenshot_path:
        raise HTTPException(status_code=404, detail="No screenshot available")

    # TODO: Return actual screenshot file
    return {
        "session_id": session_id,
        "screenshot_path": session.screenshot_path,
    }


# ============================================================================
# WebSocket Endpoint
# ============================================================================


@router.websocket("/ws/{session_id}")
async def websocket_application_updates(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time application updates.

    Clients can connect to receive updates about:
    - Form filling progress
    - Step transitions
    - Blocker detection
    - Errors and status changes
    """
    session = _application_sessions.get(session_id)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept()
    logger.info(f"WebSocket connected for application {session_id}")

    try:
        # Send initial status
        await websocket.send_json({
            "type": "status",
            "session_id": session_id,
            "status": session.status.value,
            "current_step": session.current_step,
            "fields_filled": len(session.fields_filled),
        })

        # Keep connection alive and handle client messages
        while True:
            data = await websocket.receive_text()

            # Handle client commands
            if data == "status":
                session = _application_sessions.get(session_id)
                if session:
                    await websocket.send_json({
                        "type": "status",
                        "session_id": session_id,
                        "status": session.status.value,
                        "current_step": session.current_step,
                        "fields_filled": len(session.fields_filled),
                        "blocker_type": session.blocker_type.value if session.blocker_type else None,
                    })
            else:
                await websocket.send_json({
                    "type": "ack",
                    "message": data,
                })

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for application {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for application {session_id}: {e}")
