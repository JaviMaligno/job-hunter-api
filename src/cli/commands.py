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
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Output file path")
    ] = None,
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
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Output file path")
    ] = None,
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

    console.print(Panel(
        "[bold]Gmail Authentication[/bold]\n\n"
        "A browser window will open for Google login.\n"
        "Grant access to read your emails.",
        title="Job Hunter",
    ))

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
    unread_only: Annotated[bool, typer.Option("--unread", "-u", help="Only fetch unread emails")] = False,
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
            subject = email["subject"][:60] + "..." if len(email["subject"]) > 60 else email["subject"]
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
    console.print(f"  Langfuse: {'[green]Configured[/green]' if settings.langfuse_secret_key else '[yellow]Not configured[/yellow]'}")

    # Claude API / Bedrock
    if settings.bedrock_enabled:
        console.print(f"  [green]AWS Bedrock: Enabled[/green] ({settings.bedrock_region})")
        console.print(f"  Model: {settings.bedrock_model_id}")
    elif settings.anthropic_api_key:
        console.print("  [green]Claude API: Configured[/green]")
    else:
        console.print("  [yellow]Claude: Not configured (enable Bedrock or set API key)[/yellow]")

    console.print(f"  Gmail: {'[green]Connected[/green]' if is_authenticated() else '[yellow]Not connected (run gmail-login)[/yellow]'}")
    console.print(f"  Google OAuth: {'[green]Configured[/green]' if settings.google_client_id else '[yellow]Not configured[/yellow]'}")


if __name__ == "__main__":
    app()
