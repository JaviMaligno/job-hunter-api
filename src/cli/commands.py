"""CLI commands using Typer."""

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from src.agents.cv_adapter import (
    CoverLetterAgent,
    CoverLetterInput,
    CVAdapterAgent,
    CVAdapterInput,
)

app = typer.Typer(
    name="job-hunter",
    help="AI-powered job hunting automation CLI",
    add_completion=False,
)

console = Console()


def read_file(path: Path) -> str:
    """Read file content with encoding handling."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def read_cv(path: Path) -> str:
    """Read CV from file (supports txt, md, pdf, docx)."""
    suffix = path.suffix.lower()

    if suffix in [".txt", ".md"]:
        return read_file(path)

    elif suffix == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text
        except ImportError:
            raise typer.BadParameter("pypdf not installed. Run: pip install pypdf")

    elif suffix == ".docx":
        try:
            from docx import Document

            doc = Document(str(path))
            return "\n".join([para.text for para in doc.paragraphs])
        except ImportError:
            raise typer.BadParameter("python-docx not installed. Run: pip install python-docx")

    else:
        raise typer.BadParameter(f"Unsupported file format: {suffix}")


@app.command()
def adapt_cv(
    cv_path: Annotated[Path, typer.Option("--cv", "-c", help="Path to CV file")],
    job_description: Annotated[
        str, typer.Option("--job", "-j", help="Job description text or file path")
    ],
    job_title: Annotated[str, typer.Option("--title", "-t", help="Job title")],
    company: Annotated[str, typer.Option("--company", help="Company name")],
    language: Annotated[str, typer.Option("--lang", "-l", help="Output language")] = "en",
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output file path")] = None,
    api_key: Annotated[
        str | None, typer.Option("--api-key", envvar="ANTHROPIC_API_KEY", help="Claude API key")
    ] = None,
):
    """
    Adapt a CV for a specific job posting.

    Example:
        job-hunter adapt-cv --cv ./my_cv.pdf --job "Software Engineer at..." --title "SE" --company "Acme"
    """
    if not cv_path.exists():
        console.print(f"[red]Error:[/red] CV file not found: {cv_path}")
        raise typer.Exit(1)

    # Read CV
    console.print("[dim]Reading CV...[/dim]")
    cv_content = read_cv(cv_path)

    # Read job description from file if it's a path
    jd_path = Path(job_description)
    if jd_path.exists():
        job_desc = read_file(jd_path)
    else:
        job_desc = job_description

    console.print(
        Panel(
            f"[bold]Adapting CV for:[/bold] {job_title} at {company}\n"
            f"[dim]CV:[/dim] {cv_path}\n"
            f"[dim]Language:[/dim] {language}",
            title="Job Hunter",
        )
    )

    async def run_adaptation():
        agent = CVAdapterAgent(claude_api_key=api_key)
        input_data = CVAdapterInput(
            base_cv=cv_content,
            job_description=job_desc,
            job_title=job_title,
            company=company,
            language=language,
        )
        return await agent.run(input_data)

    console.print("[dim]Adapting CV with Claude...[/dim]")
    result = asyncio.run(run_adaptation())

    # Display results
    console.print("\n")
    console.print(Panel(f"[bold green]Match Score: {result.match_score}/100[/bold green]"))

    console.print("\n[bold]Skills Matched:[/bold]")
    for skill in result.skills_matched:
        console.print(f"  [green]+[/green] {skill}")

    if result.skills_missing:
        console.print("\n[bold]Skills Gap:[/bold]")
        for skill in result.skills_missing:
            console.print(f"  [yellow]-[/yellow] {skill}")

    console.print("\n[bold]Changes Made:[/bold]")
    for change in result.changes_made:
        console.print(f"  * {change}")

    console.print("\n[bold]Interview Key Points:[/bold]")
    for point in result.key_highlights:
        console.print(f"  > {point}")

    # Save adapted CV
    if output:
        output.write_text(result.adapted_cv, encoding="utf-8")
        console.print(f"\n[green]Adapted CV saved to:[/green] {output}")
    else:
        console.print("\n[bold]Adapted CV:[/bold]")
        console.print(Markdown(result.adapted_cv))


@app.command()
def cover_letter(
    cv_path: Annotated[Path, typer.Option("--cv", "-c", help="Path to CV file")],
    job_description: Annotated[
        str, typer.Option("--job", "-j", help="Job description text or file path")
    ],
    job_title: Annotated[str, typer.Option("--title", "-t", help="Job title")],
    company: Annotated[str, typer.Option("--company", help="Company name")],
    language: Annotated[str, typer.Option("--lang", "-l", help="Output language")] = "en",
    tone: Annotated[
        str, typer.Option("--tone", help="Tone: professional, enthusiastic, casual")
    ] = "professional",
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output file path")] = None,
    api_key: Annotated[
        str | None, typer.Option("--api-key", envvar="ANTHROPIC_API_KEY", help="Claude API key")
    ] = None,
):
    """
    Generate a cover letter for a job application.

    Example:
        job-hunter cover-letter --cv ./my_cv.pdf --job "..." --title "SE" --company "Acme"
    """
    if not cv_path.exists():
        console.print(f"[red]Error:[/red] CV file not found: {cv_path}")
        raise typer.Exit(1)

    cv_content = read_cv(cv_path)

    # Read job description from file if it's a path
    jd_path = Path(job_description)
    if jd_path.exists():
        job_desc = read_file(jd_path)
    else:
        job_desc = job_description

    console.print(
        Panel(
            f"[bold]Generating cover letter for:[/bold] {job_title} at {company}",
            title="Job Hunter",
        )
    )

    async def run_generation():
        agent = CoverLetterAgent(claude_api_key=api_key)
        input_data = CoverLetterInput(
            cv_content=cv_content,
            job_description=job_desc,
            job_title=job_title,
            company=company,
            language=language,
            tone=tone,
        )
        return await agent.run(input_data)

    console.print("[dim]Generating cover letter with Claude...[/dim]")
    result = asyncio.run(run_generation())

    # Display results
    console.print("\n[bold]Cover Letter:[/bold]")
    console.print(Markdown(result.cover_letter))

    console.print("\n[bold]Key Points Addressed:[/bold]")
    for point in result.key_points:
        console.print(f"  * {point}")

    console.print("\n[bold]Interview Talking Points:[/bold]")
    for point in result.talking_points:
        console.print(f"  > {point}")

    # Save cover letter
    if output:
        output.write_text(result.cover_letter, encoding="utf-8")
        console.print(f"\n[green]Cover letter saved to:[/green] {output}")


@app.command()
def gmail_login():
    """
    Authenticate with Gmail using OAuth.

    Opens a browser window for Google login.
    Token is saved locally for future use.
    """
    from src.integrations.email.gmail import authenticate_gmail, is_authenticated

    if is_authenticated():
        console.print("[green]Already authenticated with Gmail[/green]")
        console.print("Use 'gmail-logout' to disconnect and re-authenticate")
        return

    console.print(
        Panel(
            "[bold]Gmail Authentication[/bold]\n\n"
            "A browser window will open for Google login.\n"
            "Grant access to read your emails.",
            title="Job Hunter",
        )
    )

    try:
        console.print("[dim]Waiting for authentication...[/dim]")
        authenticate_gmail()

        console.print("\n[green]Successfully authenticated with Gmail![/green]")
        console.print("You can now use 'gmail-fetch' to get job alert emails.")

    except Exception as e:
        console.print(f"\n[red]Authentication failed:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def gmail_status():
    """Check Gmail authentication status."""
    from src.integrations.email.gmail import is_authenticated

    if is_authenticated():
        console.print("[green]Gmail: Authenticated[/green]")
    else:
        console.print("[yellow]Gmail: Not authenticated[/yellow]")
        console.print("Run 'gmail-login' to connect your Gmail account")


@app.command()
def gmail_logout():
    """Disconnect Gmail account."""
    from src.integrations.email.gmail import logout_gmail

    if logout_gmail():
        console.print("[green]Gmail disconnected successfully[/green]")
    else:
        console.print("[yellow]No Gmail connection found[/yellow]")


@app.command()
def gmail_fetch(
    max_emails: Annotated[int, typer.Option("--max", "-m", help="Maximum emails to fetch")] = 20,
    unread_only: Annotated[
        bool, typer.Option("--unread", "-u", help="Only fetch unread emails")
    ] = False,
):
    """
    Fetch job alert emails from Gmail.

    Searches for emails from LinkedIn, Indeed, InfoJobs, etc.
    """
    from src.integrations.email.gmail import GmailClient, is_authenticated

    if not is_authenticated():
        console.print("[red]Not authenticated with Gmail[/red]")
        console.print("Run 'gmail-login' first")
        raise typer.Exit(1)

    console.print(Panel("[bold]Fetching job alert emails...[/bold]", title="Job Hunter"))

    try:
        client = GmailClient()
        console.print("[dim]Connecting to Gmail...[/dim]")

        if unread_only:
            emails = client.get_all_unread_emails(max_results=max_emails)
        else:
            emails = client.get_job_alert_emails(max_results=max_emails)

        if not emails:
            console.print("\n[yellow]No job alert emails found[/yellow]")
            return

        console.print(f"\n[green]Found {len(emails)} emails[/green]\n")

        for i, email in enumerate(emails, 1):
            # Truncate subject if too long
            subject = (
                email["subject"][:60] + "..." if len(email["subject"]) > 60 else email["subject"]
            )
            sender = email["sender"][:40] + "..." if len(email["sender"]) > 40 else email["sender"]

            console.print(f"[bold]{i}.[/bold] {subject}")
            console.print(f"   [dim]From:[/dim] {sender}")
            console.print(f"   [dim]Date:[/dim] {email['received_at'][:10]}")
            console.print()

    except Exception as e:
        console.print(f"\n[red]Error fetching emails:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def version():
    """Show version information."""
    console.print("[bold]Job Hunter API[/bold] v0.1.0")
    console.print("AI-powered job hunting automation")


@app.command()
def info():
    """Show configuration information."""
    from src.config import settings
    from src.integrations.email.gmail import is_authenticated

    console.print(Panel("[bold]Configuration[/bold]", title="Job Hunter"))
    console.print(f"  Environment: {settings.app_env.value}")
    console.print(f"  Debug: {settings.debug}")
    console.print(f"  Database: {settings.database_url[:50]}...")
    console.print(
        f"  Langfuse: {'[green]Configured[/green]' if settings.langfuse_secret_key else '[yellow]Not configured[/yellow]'}"
    )

    # Claude API / Bedrock
    if settings.bedrock_enabled:
        console.print(f"  [green]AWS Bedrock: Enabled[/green] ({settings.bedrock_region})")
        console.print(f"  Model: {settings.bedrock_model_id}")
    elif settings.anthropic_api_key:
        console.print("  [green]Claude API: Configured[/green]")
    else:
        console.print("  [yellow]Claude: Not configured (enable Bedrock or set API key)[/yellow]")

    console.print(
        f"  Gmail: {'[green]Connected[/green]' if is_authenticated() else '[yellow]Not connected (run gmail-login)[/yellow]'}"
    )
    console.print(
        f"  Google OAuth: {'[green]Configured[/green]' if settings.google_client_id else '[yellow]Not configured[/yellow]'}"
    )


# ============================================================================
# Phase 2: Browser Automation Commands
# ============================================================================


@app.command()
def apply(
    job_url: Annotated[str, typer.Argument(help="URL of the job to apply to")],
    cv_path: Annotated[Path, typer.Option("--cv", "-c", help="Path to CV file")],
    mode: Annotated[
        str, typer.Option("--mode", "-m", help="Mode: assisted, semi-auto, auto")
    ] = "assisted",
    cover_letter_path: Annotated[
        Path | None, typer.Option("--cover", help="Path to cover letter file")
    ] = None,
    headless: Annotated[bool, typer.Option("--headless", help="Run browser headless")] = False,
    api_key: Annotated[
        str | None, typer.Option("--api-key", envvar="ANTHROPIC_API_KEY", help="Claude API key")
    ] = None,
):
    """
    Apply to a job posting with browser automation.

    Modes:
    - assisted: Auto-fill form, pause before submit for review (default)
    - semi-auto: Auto-fill form, pause only on blockers
    - auto: Fully automatic (use with caution)

    Example:
        job-hunter apply "https://company.breezy.hr/p/job123" --cv ./cv.pdf --mode assisted
    """
    from src.agents.form_filler import FormFillerAgent, FormFillerInput, UserFormData
    from src.automation.client import BrowserServiceClient
    from src.db.models import ApplicationMode

    if not cv_path.exists():
        console.print(f"[red]Error:[/red] CV file not found: {cv_path}")
        raise typer.Exit(1)

    # Read CV
    console.print("[dim]Reading CV...[/dim]")
    cv_content = read_cv(cv_path)

    # Read cover letter if provided
    cover_letter = None
    if cover_letter_path and cover_letter_path.exists():
        cover_letter = read_file(cover_letter_path)

    # Map mode string to enum
    mode_map = {
        "assisted": ApplicationMode.ASSISTED,
        "semi-auto": ApplicationMode.SEMI_AUTO,
        "auto": ApplicationMode.AUTO,
    }
    app_mode = mode_map.get(mode.lower(), ApplicationMode.ASSISTED)

    console.print(
        Panel(
            f"[bold]Applying to job[/bold]\n\n"
            f"URL: {job_url}\n"
            f"CV: {cv_path}\n"
            f"Mode: {app_mode.value}\n"
            f"Headless: {headless}",
            title="Job Hunter - Apply",
        )
    )

    # Check if browser service is available
    async def check_service():
        return await BrowserServiceClient.is_service_available()

    service_available = asyncio.run(check_service())

    if not service_available:
        console.print("\n[yellow]Browser Service not running[/yellow]")
        console.print(
            "Start it with: [bold]uvicorn src.browser_service.main:app --port 8001[/bold]"
        )
        console.print("\nOr run in headless mode without the service (coming soon)")
        raise typer.Exit(1)

    # Create user data (TODO: load from database/config)
    # For now, using placeholder data
    user_data = UserFormData(
        first_name="John",
        last_name="Doe",
        email="john.doe@example.com",
        phone="7123456789",
        phone_country_code="+44",
        city="London",
        country="United Kingdom",
    )

    console.print(
        "[yellow]Note: Using placeholder user data. Configure your profile for real applications.[/yellow]"
    )

    async def run_apply():
        agent = FormFillerAgent(claude_api_key=api_key)
        input_data = FormFillerInput(
            application_url=job_url,
            user_data=user_data,
            cv_content=cv_content,
            cv_file_path=str(cv_path) if cv_path else None,
            cover_letter=cover_letter,
            mode=app_mode,
            headless=headless,
        )
        return await agent.run(input_data)

    console.print("\n[dim]Starting browser automation...[/dim]")

    try:
        result = asyncio.run(run_apply())

        # Display results
        status_color = {
            "pending": "yellow",
            "in_progress": "blue",
            "submitted": "green",
            "failed": "red",
            "needs_intervention": "yellow",
        }
        color = status_color.get(result.status.value, "white")

        console.print(f"\n[bold]Status:[/bold] [{color}]{result.status.value}[/{color}]")

        if result.detected_ats:
            console.print(f"[dim]ATS Detected:[/dim] {result.detected_ats}")

        if result.fields_filled:
            console.print(f"\n[bold]Fields Filled:[/bold] {len(result.fields_filled)}")
            for _selector, value in list(result.fields_filled.items())[:5]:
                display_value = value[:30] + "..." if len(value) > 30 else value
                console.print(f"  [green]+[/green] {display_value}")

        if result.questions_answered:
            console.print(f"\n[bold]Questions Answered:[/bold] {len(result.questions_answered)}")
            for q in result.questions_answered[:3]:
                console.print(f"  [blue]Q:[/blue] {q.question_text[:50]}...")
                if q.answer:
                    console.print(f"  [green]A:[/green] {q.answer[:50]}...")

        if result.blocker_detected:
            console.print(f"\n[yellow]Blocker:[/yellow] {result.blocker_detected.value}")
            if result.blocker_details:
                console.print(f"  {result.blocker_details}")

        if result.requires_user_action:
            console.print("\n[bold yellow]Action Required:[/bold yellow]")
            console.print(f"  {result.user_action_message}")
            console.print(f"\n  Session ID: {result.browser_session_id}")
            console.print(
                f"  Use 'apply-resume {result.browser_session_id}' after completing the action"
            )

        if result.screenshot_path:
            console.print(f"\n[dim]Screenshot:[/dim] {result.screenshot_path}")

        if result.error_message:
            console.print(f"\n[red]Error:[/red] {result.error_message}")

    except Exception as e:
        console.print(f"\n[red]Error during application:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def apply_status(
    session_id: Annotated[str | None, typer.Argument(help="Session ID to check")] = None,
):
    """
    Check status of application sessions.

    Without arguments, shows all paused sessions.
    With session_id, shows details for that session.

    Example:
        job-hunter apply-status
        job-hunter apply-status abc123-def456
    """
    from src.automation.blockers.handler import BlockerHandler

    handler = BlockerHandler()
    paused = handler.list_paused_sessions()

    if session_id:
        # Show specific session
        session = handler.get_paused_session(session_id)
        if session:
            console.print(
                Panel(
                    f"[bold]Session:[/bold] {session.session_id}\n"
                    f"[bold]Blocker:[/bold] {session.blocker_type.value}\n"
                    f"[bold]Message:[/bold] {session.blocker_message}\n"
                    f"[bold]Paused At:[/bold] {session.paused_at}\n"
                    f"[bold]URL:[/bold] {session.page_url or 'N/A'}",
                    title="Session Details",
                )
            )
            if session.screenshot_path:
                console.print(f"\n[dim]Screenshot:[/dim] {session.screenshot_path}")
        else:
            console.print(f"[yellow]Session not found:[/yellow] {session_id}")
    else:
        # Show all paused sessions
        if not paused:
            console.print("[green]No paused sessions[/green]")
            return

        console.print(f"[bold]Paused Sessions:[/bold] {len(paused)}\n")
        for session in paused:
            console.print(f"  [yellow]*[/yellow] {session.session_id[:8]}...")
            console.print(f"    Blocker: {session.blocker_type.value}")
            console.print(f"    Message: {session.blocker_message}")
            console.print(f"    Paused: {session.paused_at.strftime('%Y-%m-%d %H:%M')}")
            console.print()


@app.command()
def apply_resume(
    session_id: Annotated[str, typer.Argument(help="Session ID to resume")],
):
    """
    Resume a paused application session.

    Use this after manually completing a CAPTCHA or logging in.

    Example:
        job-hunter apply-resume abc123-def456
    """
    from src.automation.blockers.handler import BlockerHandler

    handler = BlockerHandler()
    session = handler.get_paused_session(session_id)

    if not session:
        console.print(f"[yellow]Session not found or already completed:[/yellow] {session_id}")
        raise typer.Exit(1)

    console.print(
        Panel(
            f"[bold]Resuming session:[/bold] {session_id}\n"
            f"[dim]Previous blocker:[/dim] {session.blocker_type.value}\n"
            f"[dim]URL:[/dim] {session.page_url or 'N/A'}",
            title="Job Hunter - Resume",
        )
    )

    # Mark as resumed
    handler.resume_session(session_id)

    console.print("\n[green]Session marked as resumed[/green]")
    console.print(
        "[dim]Note: In a full implementation, this would reconnect to the browser session[/dim]"
    )
    console.print("[dim]and continue the form filling process.[/dim]")


@app.command()
def browser_start(
    mode: Annotated[str, typer.Option("--mode", help="Browser mode: playwright")] = "playwright",
    port: Annotated[int, typer.Option("--port", "-p", help="Port for browser service")] = 8001,
):
    """
    Start the browser service.

    This service handles browser automation for job applications.
    Must be running before using 'apply' command.

    Example:
        job-hunter browser-start
        job-hunter browser-start --port 8002
    """
    import uvicorn

    console.print(
        Panel(
            f"[bold]Starting Browser Service[/bold]\n\n"
            f"Mode: {mode}\n"
            f"Port: {port}\n\n"
            f"Press Ctrl+C to stop",
            title="Job Hunter - Browser Service",
        )
    )

    uvicorn.run(
        "src.browser_service.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    app()
