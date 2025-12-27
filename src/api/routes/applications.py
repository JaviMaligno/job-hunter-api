"""Application automation API routes."""

import asyncio
import enum
import logging
from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from src.agents.form_filler import FormFillerAgent, FormFillerInput, FormFillerOutput
from src.browser_service.models import BrowserMode
from src.config import settings
from src.api.dependencies import ClaudeDep
from src.api.websocket_manager import get_connection_manager, WebSocketMessage
from src.automation.models import UserFormData
from src.automation.session_store import get_session_store, SessionState
from src.db.models import ApplicationMode, ApplicationStatus, BlockerType

# Gemini orchestrator imports (optional)
try:
    from src.agents.gemini_orchestrator import (
        GeminiOrchestratorAgent,
        OrchestratorInput,
        OrchestratorOutput,
        UserFormData as GeminiUserFormData,
    )
    from src.automation.intervention_manager import (
        InterventionManager,
        InterventionRequest,
        InterventionResolution,
        InterventionType,
        get_intervention_manager,
    )
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


# Register intervention callbacks for WebSocket broadcasts
def _setup_intervention_callbacks():
    """Setup WebSocket callbacks for interventions."""
    if not GEMINI_AVAILABLE:
        return

    manager = get_intervention_manager()
    ws_manager = get_connection_manager()

    async def on_intervention(intervention: InterventionRequest):
        """Broadcast new intervention via WebSocket."""
        await ws_manager.broadcast_intervention(
            intervention_id=intervention.id,
            session_id=intervention.session_id,
            user_id=intervention.user_id,
            intervention_type=intervention.intervention_type.value,
            title=intervention.title,
            description=intervention.description,
            current_url=intervention.current_url,
        )

    async def on_resolution(intervention: InterventionRequest, resolution: InterventionResolution):
        """Broadcast intervention resolution via WebSocket."""
        message = WebSocketMessage(
            type="intervention_resolved",
            payload={
                "intervention_id": intervention.id,
                "session_id": intervention.session_id,
                "action": resolution.action,
                "notes": resolution.notes,
            },
        )
        await ws_manager.send_to_session(intervention.session_id, message)

    manager.on_intervention(on_intervention)
    manager.on_resolution(on_resolution)


# Setup callbacks on module import
_setup_intervention_callbacks()

logger = logging.getLogger(__name__)

router = APIRouter()


# Test WebSocket endpoint to debug 403 issue
@router.websocket("/ws/router-test")
async def websocket_router_test(websocket: WebSocket):
    """Simple test WebSocket endpoint on the router."""
    await websocket.accept()
    logger.info("Router test WebSocket connected!")
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Router echo: {data}")
    except WebSocketDisconnect:
        logger.info("Router test WebSocket disconnected")


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
        # Get API key if available (Anthropic has api_key, AnthropicBedrock doesn't)
        api_key = getattr(claude, "api_key", None)
        agent = FormFillerAgent(claude_api_key=api_key)
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

        if result.error_message:
            session.error = result.error_message

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


# ============================================================================
# V2 Endpoints - Gemini Orchestrator
# ============================================================================


class AgentType(str, enum.Enum):
    """Available automation agents."""
    GEMINI = "gemini"  # Gemini 2.5 + Chrome MCP
    CLAUDE = "claude"  # Claude FormFillerAgent
    HYBRID = "hybrid"  # Gemini with Claude fallback


class StartApplicationV2Request(BaseModel):
    """Request to start a job application with orchestrator."""
    job_url: str
    user_data: UserFormData
    cv_content: str
    cv_file_path: str | None = None
    cover_letter: str | None = None
    mode: ApplicationMode = ApplicationMode.ASSISTED
    agent: AgentType = AgentType.GEMINI  # Which agent to use
    auto_solve_captcha: bool = True  # Auto-solve CAPTCHAs if possible
    gemini_model: str | None = None  # Optional: override Gemini model
    browser_mode: str | None = None  # Browser mode: chrome-devtools or playwright (defaults to config)
    devtools_url: str | None = None  # Chrome DevTools URL for chrome-devtools mode


class ApplicationV2Response(BaseModel):
    """Response from v2 application endpoint."""
    session_id: str
    status: str
    success: bool
    agent_used: str = "gemini"  # Which agent was used
    steps_completed: list[str] = Field(default_factory=list)
    fields_filled: int = 0
    intervention_id: str | None = None
    intervention_type: str | None = None
    intervention_title: str | None = None
    captcha_solved: bool = False
    captcha_cost: float = 0.0
    error: str | None = None
    final_url: str | None = None


class InterventionResponse(BaseModel):
    """Response with intervention details."""
    id: str
    session_id: str
    intervention_type: str
    status: str
    title: str
    description: str
    instructions: str | None = None
    current_url: str | None = None
    captcha_type: str | None = None
    created_at: datetime


class ResolveInterventionRequest(BaseModel):
    """Request to resolve an intervention."""
    action: str  # continue, submit, cancel, retry
    notes: str | None = None
    close_browser: bool = True  # Whether to close the browser session


class SessionSummary(BaseModel):
    """Summary of a session for listing."""
    session_id: str
    job_url: str
    status: str
    current_step: int
    fields_filled: int
    created_at: datetime
    paused_at: datetime | None = None
    can_resume: bool = False


class ResumeSessionRequest(BaseModel):
    """Request to resume a paused session."""
    restore_browser: bool = True  # Restore cookies/state
    auto_solve_captcha: bool = True


@router.post("/v2/start", response_model=ApplicationV2Response)
async def start_application_v2(
    request: StartApplicationV2Request,
    claude: ClaudeDep,
):
    """Start a job application using the selected orchestrator agent.

    This v2 endpoint supports:
    - Gemini: GeminiOrchestratorAgent with Chrome MCP (recommended)
    - Claude: Claude FormFillerAgent (fallback)
    - Hybrid: Gemini with Claude fallback on failure

    Features:
    - Automatic CAPTCHA solving via 2captcha
    - InterventionManager for human-in-the-loop
    - Session persistence for resume

    Returns immediately with status and optional intervention ID.
    """
    # Check if Gemini is required but not available
    if request.agent in [AgentType.GEMINI, AgentType.HYBRID] and not GEMINI_AVAILABLE:
        if request.agent == AgentType.GEMINI:
            raise HTTPException(
                status_code=501,
                detail="Gemini orchestrator not available. Use agent=claude or check dependencies."
            )
        # For hybrid, fall back to Claude
        request.agent = AgentType.CLAUDE

    session_id = str(uuid4())

    # Create session record
    session = ApplicationSession(
        session_id=session_id,
        job_url=request.job_url,
        status=ApplicationStatus.IN_PROGRESS,
        mode=request.mode,
    )
    _application_sessions[session_id] = session

    # Also persist to session store for resume capability
    session_store = get_session_store()
    persistent_session = SessionState(
        session_id=session_id,
        job_url=request.job_url,
        status=ApplicationStatus.IN_PROGRESS,
        mode=request.mode,
        user_data_json=request.user_data.model_dump_json(),
        cv_content=request.cv_content,
        cv_file_path=request.cv_file_path,
        cover_letter=request.cover_letter,
    )
    await session_store.save(persistent_session)

    try:
        result = None
        use_claude_fallback = False
        agent_used = request.agent.value

        # Run the selected agent
        if request.agent in [AgentType.GEMINI, AgentType.HYBRID]:
            # Gemini orchestrator
            gemini_user_data = GeminiUserFormData(
                first_name=request.user_data.first_name,
                last_name=request.user_data.last_name,
                email=request.user_data.email,
                phone=request.user_data.phone,
                phone_country_code=request.user_data.phone_country_code,
                linkedin_url=request.user_data.linkedin_url,
                github_url=request.user_data.github_url,
                portfolio_url=request.user_data.portfolio_url,
                address_line_1=request.user_data.address_line_1,
                city=request.user_data.city,
                country=request.user_data.country,
                postal_code=request.user_data.postal_code,
            )

            orchestrator_input = OrchestratorInput(
                job_url=request.job_url,
                user_data=gemini_user_data,
                cv_content=request.cv_content,
                cv_file_path=request.cv_file_path,
                cover_letter=request.cover_letter,
                headless=False,
                # Session info for intervention management
                session_id=session_id,
                user_id="default",
                wait_for_intervention=True,
            )

            try:
                agent = GeminiOrchestratorAgent(
                    model=request.gemini_model,
                    auto_solve_captcha=request.auto_solve_captcha
                )
                result = await agent.run(orchestrator_input)
            except Exception as gemini_error:
                logger.warning(f"Gemini agent failed: {gemini_error}")
                if request.agent == AgentType.HYBRID:
                    logger.info("Falling back to Claude agent")
                    use_claude_fallback = True
                    agent_used = "claude_fallback"
                else:
                    raise

        if request.agent == AgentType.CLAUDE or use_claude_fallback:
            # Claude FormFillerAgent
            # Parse browser mode from request, defaulting to config
            effective_browser_mode = request.browser_mode or settings.default_browser_mode
            browser_mode = BrowserMode.CHROME_DEVTOOLS if effective_browser_mode == "chrome-devtools" else BrowserMode.PLAYWRIGHT

            filler_input = FormFillerInput(
                application_url=request.job_url,
                user_data=request.user_data,
                cv_content=request.cv_content,
                cv_file_path=request.cv_file_path,
                cover_letter=request.cover_letter,
                mode=request.mode,
                headless=False,
                browser_mode=browser_mode,
                devtools_url=request.devtools_url,
            )

            api_key = getattr(claude, "api_key", None)
            claude_agent = FormFillerAgent(claude_api_key=api_key)
            claude_result: FormFillerOutput = await claude_agent.run(filler_input)

            # Convert Claude result to OrchestratorOutput format for unified handling
            from src.agents.gemini_orchestrator import OrchestratorOutput, FieldFilled, BlockerDetected

            # Create blocker if detected
            blocker = None
            if claude_result.blocker_detected:
                blocker_type_map = {
                    BlockerType.CAPTCHA: "captcha",
                    BlockerType.LOGIN_REQUIRED: "login_required",
                    BlockerType.FILE_UPLOAD: "file_upload",
                }
                blocker = BlockerDetected(
                    blocker_type=blocker_type_map.get(claude_result.blocker_detected, "other"),
                    description=claude_result.blocker_details or "Blocker detected",
                    screenshot_path=claude_result.screenshot_path,
                    captcha_subtype="recaptcha" if claude_result.blocker_detected == BlockerType.CAPTCHA else None,
                )

            result = OrchestratorOutput(
                success=claude_result.status == ApplicationStatus.SUBMITTED,
                status=(
                    "completed" if claude_result.status == ApplicationStatus.SUBMITTED
                    else "paused" if claude_result.status == ApplicationStatus.PAUSED
                    else "needs_intervention" if claude_result.status == ApplicationStatus.NEEDS_INTERVENTION
                    else "failed" if claude_result.status == ApplicationStatus.FAILED
                    else "in_progress"
                ),
                steps_completed=[f"Step {i}" for i in range(1, claude_result.current_step + 1)],
                fields_filled=[
                    FieldFilled(field_name=k, value=v, field_type="text")
                    for k, v in claude_result.fields_filled.items()
                ],
                blocker=blocker,
                final_url=claude_result.page_url or request.job_url,
                screenshot_path=claude_result.screenshot_path,
                error_message=claude_result.error_message,
            )

        # Update session
        session.status = (
            ApplicationStatus.PAUSED if result.status == "paused"
            else ApplicationStatus.SUBMITTED if result.status == "completed"
            else ApplicationStatus.NEEDS_INTERVENTION if result.status == "needs_intervention"
            else ApplicationStatus.FAILED if result.status == "failed"
            else ApplicationStatus.IN_PROGRESS
        )
        session.fields_filled = {f.field_name: f.value for f in result.fields_filled}
        session.updated_at = datetime.utcnow()

        # Save browser session ID from Claude agent
        if request.agent == AgentType.CLAUDE or use_claude_fallback:
            if claude_result and claude_result.browser_session_id:
                session.browser_session_id = claude_result.browser_session_id

        if result.blocker:
            session.blocker_type = BlockerType.CAPTCHA if result.blocker.blocker_type == "captcha" else BlockerType.NONE
            session.blocker_message = result.blocker.description

        if result.error_message:
            session.error = result.error_message

        # Update persistent session
        persistent_session.status = session.status
        persistent_session.steps_completed = result.steps_completed
        persistent_session.fields_filled = {f.field_name: f.value for f in result.fields_filled}
        persistent_session.current_url = result.final_url
        # Save browser session ID for later cleanup
        if session.browser_session_id:
            persistent_session.browser_session_id = session.browser_session_id
        if result.blocker:
            persistent_session.blocker_type = session.blocker_type
            persistent_session.blocker_message = session.blocker_message
        if session.status == ApplicationStatus.PAUSED:
            persistent_session.paused_at = datetime.utcnow()
        elif session.status in [ApplicationStatus.SUBMITTED, ApplicationStatus.FAILED]:
            persistent_session.completed_at = datetime.utcnow()
        await session_store.save(persistent_session)

        # Create intervention if needed
        intervention_id = None
        intervention_type = None
        intervention_title = None

        if result.status == "needs_intervention" and result.blocker:
            intervention_manager = get_intervention_manager()

            # Map blocker type to intervention type
            int_type = InterventionType.CAPTCHA if result.blocker.blocker_type == "captcha" else InterventionType.OTHER

            intervention = await intervention_manager.request_intervention(
                session_id=session_id,
                user_id="default",  # TODO: Get from auth
                intervention_type=int_type,
                title=f"{result.blocker.blocker_type.title()} Detected",
                description=result.blocker.description,
                instructions="Please resolve this manually using Claude Code CLI",
                current_url=result.final_url,
                captcha_type=result.blocker.captcha_subtype,
                captcha_solve_attempted=result.captcha_info.attempted if result.captcha_info else False,
                captcha_solve_error=result.captcha_info.error if result.captcha_info else None,
            )

            intervention_id = intervention.id
            intervention_type = int_type.value
            intervention_title = intervention.title

            # Save intervention ID to persistent session
            persistent_session.intervention_id = intervention_id
            await session_store.save(persistent_session)

        # CAPTCHA info
        captcha_solved = result.captcha_info.success if result.captcha_info else False
        captcha_cost = result.captcha_info.cost_usd if result.captcha_info else 0.0

        return ApplicationV2Response(
            session_id=session_id,
            status=result.status,
            success=result.success,
            agent_used=agent_used,
            steps_completed=result.steps_completed,
            fields_filled=len(result.fields_filled),
            intervention_id=intervention_id,
            intervention_type=intervention_type,
            intervention_title=intervention_title,
            captcha_solved=captcha_solved,
            captcha_cost=captcha_cost,
            error=result.error_message,
            final_url=result.final_url,
        )

    except Exception as e:
        logger.error(f"V2 Application failed: {e}")
        import traceback
        traceback.print_exc()

        session.status = ApplicationStatus.FAILED
        session.error = str(e)
        session.updated_at = datetime.utcnow()

        # Persist failed state
        persistent_session.status = ApplicationStatus.FAILED
        persistent_session.error = str(e)
        persistent_session.completed_at = datetime.utcnow()
        await session_store.save(persistent_session)

        return ApplicationV2Response(
            session_id=session_id,
            status="failed",
            success=False,
            agent_used=request.agent.value,
            error=str(e),
        )


@router.get("/v2/interventions", response_model=list[InterventionResponse])
async def get_pending_interventions():
    """Get all pending interventions requiring user action."""
    if not GEMINI_AVAILABLE:
        raise HTTPException(status_code=501, detail="Gemini orchestrator not available")

    intervention_manager = get_intervention_manager()
    pending = intervention_manager.get_pending_interventions()

    return [
        InterventionResponse(
            id=i.id,
            session_id=i.session_id,
            intervention_type=i.intervention_type.value,
            status=i.status.value,
            title=i.title,
            description=i.description,
            instructions=i.instructions,
            current_url=i.current_url,
            captcha_type=i.captcha_type,
            created_at=i.created_at,
        )
        for i in pending
    ]


@router.get("/v2/interventions/{intervention_id}", response_model=InterventionResponse)
async def get_intervention(intervention_id: str):
    """Get details of a specific intervention."""
    if not GEMINI_AVAILABLE:
        raise HTTPException(status_code=501, detail="Gemini orchestrator not available")

    intervention_manager = get_intervention_manager()
    intervention = intervention_manager.get_intervention(intervention_id)

    if not intervention:
        raise HTTPException(status_code=404, detail="Intervention not found")

    return InterventionResponse(
        id=intervention.id,
        session_id=intervention.session_id,
        intervention_type=intervention.intervention_type.value,
        status=intervention.status.value,
        title=intervention.title,
        description=intervention.description,
        instructions=intervention.instructions,
        current_url=intervention.current_url,
        captcha_type=intervention.captcha_type,
        created_at=intervention.created_at,
    )


@router.post("/v2/interventions/{intervention_id}/resolve")
async def resolve_intervention(
    intervention_id: str,
    request: ResolveInterventionRequest,
):
    """Resolve an intervention (mark as handled manually)."""
    if not GEMINI_AVAILABLE:
        raise HTTPException(status_code=501, detail="Gemini orchestrator not available")

    intervention_manager = get_intervention_manager()

    # Get intervention to find session_id for browser cleanup
    intervention = intervention_manager.get_intervention(intervention_id)
    if not intervention:
        raise HTTPException(status_code=404, detail="Intervention not found")

    success = await intervention_manager.resolve(
        intervention_id=intervention_id,
        action=request.action,
        notes=request.notes,
    )

    if not success:
        raise HTTPException(status_code=404, detail="Failed to resolve intervention")

    # Close browser session if requested and action is "continue" (Done)
    browser_closed = False
    logger.info(f"Resolve intervention: action={request.action}, close_browser={request.close_browser}")
    if request.close_browser and request.action == "continue":
        session_store = get_session_store()
        session = await session_store.load(intervention.session_id)
        logger.info(f"Session loaded: {session.session_id if session else 'None'}, browser_session_id={session.browser_session_id if session else 'N/A'}")
        if session and session.browser_session_id:
            try:
                from src.automation.client import BrowserServiceClient
                async with BrowserServiceClient() as client:
                    await client.close_session_by_id(session.browser_session_id)
                browser_closed = True
                logger.info(f"Closed browser session {session.browser_session_id} for intervention {intervention_id}")
            except Exception as e:
                logger.warning(f"Failed to close browser session: {e}")
        else:
            logger.warning(f"No browser_session_id found for session {intervention.session_id}")

    return {
        "status": "resolved",
        "intervention_id": intervention_id,
        "action": request.action,
        "browser_closed": browser_closed,
    }


@router.get("/v2/sessions", response_model=list[SessionSummary])
async def list_v2_sessions(
    resumable_only: bool = Query(False, description="Only show resumable sessions"),
):
    """List all v2 sessions, optionally filtered to resumable only."""
    session_store = get_session_store()

    if resumable_only:
        sessions = await session_store.list_resumable()
    else:
        sessions = await session_store.list_sessions()

    return [
        SessionSummary(
            session_id=s.session_id,
            job_url=s.job_url,
            status=s.status.value if isinstance(s.status, ApplicationStatus) else s.status,
            current_step=s.current_step,
            fields_filled=len(s.fields_filled),
            created_at=s.created_at,
            paused_at=s.paused_at,
            can_resume=s.status in [
                ApplicationStatus.PAUSED,
                ApplicationStatus.NEEDS_INTERVENTION,
            ],
        )
        for s in sessions
    ]


@router.get("/v2/sessions/{session_id}")
async def get_v2_session(session_id: str):
    """Get detailed state of a v2 session."""
    session_store = get_session_store()
    session = await session_store.load(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session.session_id,
        "job_url": session.job_url,
        "status": session.status.value if isinstance(session.status, ApplicationStatus) else session.status,
        "mode": session.mode.value if isinstance(session.mode, ApplicationMode) else session.mode,
        "current_step": session.current_step,
        "total_steps": session.total_steps,
        "steps_completed": session.steps_completed,
        "fields_filled": session.fields_filled,
        "fields_remaining": session.fields_remaining,
        "blocker_type": session.blocker_type,
        "blocker_message": session.blocker_message,
        "intervention_id": session.intervention_id,
        "current_url": session.current_url,
        "error": session.error,
        "retry_count": session.retry_count,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "paused_at": session.paused_at.isoformat() if session.paused_at else None,
        "can_resume": session.status in [
            ApplicationStatus.PAUSED,
            ApplicationStatus.NEEDS_INTERVENTION,
        ],
    }


@router.post("/v2/sessions/{session_id}/resume", response_model=ApplicationV2Response)
async def resume_v2_session(
    session_id: str,
    request: ResumeSessionRequest,
    claude: ClaudeDep,
    background_tasks: BackgroundTasks,
):
    """
    Resume a paused v2 session.

    Starts the automation in background and returns immediately.
    Progress updates are sent via WebSocket.
    """
    if not GEMINI_AVAILABLE:
        raise HTTPException(status_code=501, detail="Gemini orchestrator not available")

    session_store = get_session_store()
    session = await session_store.load(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status not in [ApplicationStatus.PAUSED, ApplicationStatus.NEEDS_INTERVENTION]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume session with status: {session.status}",
        )

    # Parse user data if available
    user_data = None
    if session.user_data_json:
        import json
        user_data_dict = json.loads(session.user_data_json)
        user_data = GeminiUserFormData(**user_data_dict)

    if not user_data:
        raise HTTPException(
            status_code=400,
            detail="Session missing user data - cannot resume",
        )

    # Update status
    session.status = ApplicationStatus.IN_PROGRESS
    session.retry_count += 1
    await session_store.save(session)

    # Also update in-memory session if exists
    if session_id in _application_sessions:
        _application_sessions[session_id].status = ApplicationStatus.IN_PROGRESS
        _application_sessions[session_id].updated_at = datetime.utcnow()

    # Broadcast status change via WebSocket
    ws_manager = get_connection_manager()
    await ws_manager.send_to_session(
        session_id,
        {
            "type": "status",
            "payload": {
                "session_id": session_id,
                "status": "in_progress",
                "message": "Resuming automation...",
            },
            "timestamp": datetime.utcnow().isoformat(),
        },
    )
    await ws_manager.broadcast_global({
        "type": "session_resumed",
        "payload": {"session_id": session_id, "status": "in_progress"},
        "timestamp": datetime.utcnow().isoformat(),
    })

    # Run orchestrator in background
    async def run_resume_task():
        nonlocal session
        try:
            result = None
            use_claude_fallback = False
            agent_used = "gemini"

            # First try Gemini
            try:
                # Create orchestrator input for resume
                orchestrator_input = OrchestratorInput(
                    job_url=session.current_url or session.job_url,
                    user_data=user_data,
                    cv_content=session.cv_content or "",
                    cv_file_path=session.cv_file_path,
                    cover_letter=session.cover_letter,
                    headless=False,
                    # Session info for intervention management
                    session_id=session_id,
                    user_id=session.user_id,
                    wait_for_intervention=True,
                )

                # Run orchestrator
                agent = GeminiOrchestratorAgent(
                    auto_solve_captcha=request.auto_solve_captcha
                )
                result = await agent.run(orchestrator_input)
            except Exception as gemini_error:
                logger.warning(f"Gemini agent failed during resume: {gemini_error}")
                use_claude_fallback = True

            # Fallback to Claude if Gemini failed
            if use_claude_fallback:
                logger.info("Falling back to Claude FormFillerAgent for resume")
                agent_used = "claude_fallback"

                # Convert user data for Claude agent
                claude_user_data = UserFormData(
                    first_name=user_data.first_name,
                    last_name=user_data.last_name,
                    email=user_data.email,
                    phone=user_data.phone if hasattr(user_data, 'phone') else "",
                )

                filler_input = FormFillerInput(
                    application_url=session.current_url or session.job_url,
                    user_data=claude_user_data,
                    cv_content=session.cv_content or "",
                    cv_file_path=session.cv_file_path,
                    cover_letter=session.cover_letter,
                    mode=session.mode,
                    headless=False,
                    browser_mode=BrowserMode.CHROME_DEVTOOLS,
                )

                api_key = getattr(claude, "api_key", None)
                claude_agent = FormFillerAgent(claude_api_key=api_key)
                claude_result: FormFillerOutput = await claude_agent.run(filler_input)

                # Convert Claude result to OrchestratorOutput format
                from src.agents.gemini_orchestrator import FieldFilled, BlockerDetected

                blocker = None
                if claude_result.blocker_detected:
                    blocker_type_map = {
                        BlockerType.CAPTCHA: "captcha",
                        BlockerType.LOGIN_REQUIRED: "login_required",
                        BlockerType.FILE_UPLOAD: "file_upload",
                    }
                    blocker = BlockerDetected(
                        blocker_type=blocker_type_map.get(claude_result.blocker_detected, "other"),
                        description=claude_result.blocker_details or "Blocker detected",
                        screenshot_path=claude_result.screenshot_path,
                        captcha_subtype="recaptcha" if claude_result.blocker_detected == BlockerType.CAPTCHA else None,
                    )

                result = OrchestratorOutput(
                    success=claude_result.status == ApplicationStatus.SUBMITTED,
                    status=(
                        "completed" if claude_result.status == ApplicationStatus.SUBMITTED
                        else "paused" if claude_result.status == ApplicationStatus.PAUSED
                        else "needs_intervention" if claude_result.status == ApplicationStatus.NEEDS_INTERVENTION
                        else "failed" if claude_result.status == ApplicationStatus.FAILED
                        else "in_progress"
                    ),
                    steps_completed=[f"Step {i}" for i in range(1, claude_result.current_step + 1)],
                    fields_filled=[
                        FieldFilled(field_name=k, value=v, field_type="text")
                        for k, v in claude_result.fields_filled.items()
                    ],
                    blocker=blocker,
                    final_url=claude_result.page_url or session.job_url,
                    screenshot_path=claude_result.screenshot_path,
                    error_message=claude_result.error_message,
                )

            # Update session with result
            session = await session_store.load(session_id)  # Reload fresh
            if not session:
                logger.error(f"Session {session_id} disappeared during resume")
                return

            new_status = (
                ApplicationStatus.PAUSED if result.status == "paused"
                else ApplicationStatus.SUBMITTED if result.status == "completed"
                else ApplicationStatus.NEEDS_INTERVENTION if result.status == "needs_intervention"
                else ApplicationStatus.FAILED if result.status == "failed"
                else ApplicationStatus.IN_PROGRESS
            )

            session.status = new_status
            session.steps_completed.extend(result.steps_completed)
            session.fields_filled.update({f.field_name: f.value for f in result.fields_filled})
            session.current_url = result.final_url

            if result.error_message:
                session.error = result.error_message

            if new_status == ApplicationStatus.PAUSED:
                session.paused_at = datetime.utcnow()
            elif new_status in [ApplicationStatus.SUBMITTED, ApplicationStatus.FAILED]:
                session.completed_at = datetime.utcnow()

            await session_store.save(session)

            # Handle intervention if needed
            if result.status == "needs_intervention" and result.blocker:
                intervention_manager = get_intervention_manager()
                int_type = InterventionType.CAPTCHA if result.blocker.blocker_type == "captcha" else InterventionType.OTHER

                intervention = await intervention_manager.request_intervention(
                    session_id=session_id,
                    user_id=session.user_id,
                    intervention_type=int_type,
                    title=f"{result.blocker.blocker_type.title()} Detected",
                    description=result.blocker.description,
                    instructions="Please resolve this manually in the browser window",
                    current_url=result.final_url,
                    fields_filled=session.fields_filled,
                )

                session.intervention_id = intervention.id
                await session_store.save(session)

            # Broadcast final status
            await ws_manager.send_to_session(
                session_id,
                {
                    "type": "status",
                    "payload": {
                        "session_id": session_id,
                        "status": result.status,
                        "success": result.success,
                        "fields_filled": len(result.fields_filled),
                        "message": result.error_message or f"Completed with status: {result.status}",
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
            await ws_manager.broadcast_global({
                "type": "session_completed",
                "payload": {"session_id": session_id, "status": result.status},
                "timestamp": datetime.utcnow().isoformat(),
            })

        except Exception as e:
            logger.error(f"Background resume failed for session {session_id}: {e}")
            import traceback
            traceback.print_exc()

            # Update session as failed
            session = await session_store.load(session_id)
            if session:
                session.status = ApplicationStatus.FAILED
                session.error = str(e)
                await session_store.save(session)

            # Broadcast error
            await ws_manager.send_to_session(
                session_id,
                {
                    "type": "error",
                    "payload": {
                        "session_id": session_id,
                        "status": "failed",
                        "error": str(e),
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
            await ws_manager.broadcast_global({
                "type": "session_error",
                "payload": {"session_id": session_id, "error": str(e)},
                "timestamp": datetime.utcnow().isoformat(),
            })

    # Start background task
    asyncio.create_task(run_resume_task())

    # Return immediately with "starting" status
    return ApplicationV2Response(
        session_id=session_id,
        status="in_progress",
        success=True,
        agent_used="gemini",
        steps_completed=session.steps_completed,
        fields_filled=len(session.fields_filled),
        intervention_id=None,
        intervention_type=None,
        intervention_title=None,
        captcha_solved=False,
        captcha_cost=0.0,
        error=None,
        final_url=session.current_url,
    )


@router.delete("/v2/sessions/{session_id}")
async def delete_v2_session(session_id: str):
    """Delete a v2 session."""
    session_store = get_session_store()

    if not await session_store.load(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    await session_store.delete(session_id)

    # Also remove from in-memory store
    if session_id in _application_sessions:
        del _application_sessions[session_id]

    return {"status": "deleted", "session_id": session_id}


# ============================================================================
# V2 WebSocket Endpoints
# ============================================================================


# IMPORTANT: Static routes must be defined BEFORE dynamic routes!
# /v2/ws/interventions must come before /v2/ws/{session_id}
@router.websocket("/v2/ws/interventions")
async def websocket_v2_interventions(websocket: WebSocket):
    """
    WebSocket endpoint for real-time intervention feed.

    Receives all intervention notifications globally.
    Useful for a dashboard showing all pending interventions.
    """
    ws_manager = get_connection_manager()
    await ws_manager.connect(websocket, global_feed=True)

    logger.info("V2 WebSocket connected to global intervention feed")

    try:
        # Send current pending interventions
        if GEMINI_AVAILABLE:
            intervention_manager = get_intervention_manager()
            pending = intervention_manager.get_pending_interventions()

            await websocket.send_json({
                "type": "initial_state",
                "payload": {
                    "pending_count": len(pending),
                    "interventions": [
                        {
                            "id": i.id,
                            "session_id": i.session_id,
                            "intervention_type": i.intervention_type.value,
                            "status": i.status.value,
                            "title": i.title,
                            "description": i.description,
                            "instructions": i.instructions,
                            "current_url": i.current_url,
                            "captcha_type": i.captcha_type,
                            "created_at": i.created_at.isoformat(),
                        }
                        for i in pending
                    ],
                },
                "timestamp": datetime.utcnow().isoformat(),
            })

        # Keep connection alive
        while True:
            data = await websocket.receive_text()

            if data == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.utcnow().isoformat()})

            elif data == "refresh":
                if GEMINI_AVAILABLE:
                    intervention_manager = get_intervention_manager()
                    pending = intervention_manager.get_pending_interventions()

                    await websocket.send_json({
                        "type": "refresh",
                        "payload": {
                            "pending_count": len(pending),
                            "interventions": [
                                {
                                    "id": i.id,
                                    "session_id": i.session_id,
                                    "intervention_type": i.intervention_type.value,
                                    "status": i.status.value,
                                    "title": i.title,
                                    "description": i.description,
                                    "instructions": i.instructions,
                                    "current_url": i.current_url,
                                    "captcha_type": i.captcha_type,
                                    "created_at": i.created_at.isoformat(),
                                }
                                for i in pending
                            ],
                        },
                        "timestamp": datetime.utcnow().isoformat(),
                    })

    except WebSocketDisconnect:
        logger.info("V2 WebSocket disconnected from intervention feed")
    except Exception as e:
        logger.error(f"V2 WebSocket error on intervention feed: {e}")
    finally:
        await ws_manager.disconnect(websocket)


@router.websocket("/v2/ws/{session_id}")
async def websocket_v2_session(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time v2 session updates.

    Receives:
    - Progress updates during form filling
    - Intervention notifications
    - Status changes

    Sends:
    - "status": Request current status
    - "ping": Keep-alive
    """
    session = _application_sessions.get(session_id)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return

    ws_manager = get_connection_manager()
    await ws_manager.connect(websocket, session_id=session_id)

    logger.info(f"V2 WebSocket connected for session {session_id}")

    try:
        # Send initial status
        await websocket.send_json({
            "type": "connected",
            "payload": {
                "session_id": session_id,
                "status": session.status.value,
                "current_step": session.current_step,
                "fields_filled": len(session.fields_filled),
                "blocker_type": session.blocker_type.value if session.blocker_type else None,
            },
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Handle client messages
        while True:
            data = await websocket.receive_text()

            if data == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.utcnow().isoformat()})

            elif data == "status":
                session = _application_sessions.get(session_id)
                if session:
                    await websocket.send_json({
                        "type": "status",
                        "payload": {
                            "session_id": session_id,
                            "status": session.status.value,
                            "current_step": session.current_step,
                            "total_steps": session.total_steps,
                            "fields_filled": len(session.fields_filled),
                            "blocker_type": session.blocker_type.value if session.blocker_type else None,
                            "error": session.error,
                        },
                        "timestamp": datetime.utcnow().isoformat(),
                    })

    except WebSocketDisconnect:
        logger.info(f"V2 WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"V2 WebSocket error for session {session_id}: {e}")
    finally:
        await ws_manager.disconnect(websocket, session_id=session_id)
