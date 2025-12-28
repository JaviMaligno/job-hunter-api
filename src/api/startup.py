"""Application startup tasks."""

import logging

from sqlalchemy import select

from src.db.models import Application, ApplicationStatus
from src.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def recover_interrupted_applications():
    """Recover applications that were in progress during shutdown.

    Marks applications that were IN_PROGRESS or PENDING when the server
    shutdown as FAILED with an appropriate error message.

    This should be called on application startup to clean up state.
    """
    async with AsyncSessionLocal() as db:
        try:
            # Find applications that were interrupted
            query = select(Application).where(
                Application.status.in_([ApplicationStatus.IN_PROGRESS, ApplicationStatus.PENDING])
            )

            result = await db.execute(query)
            interrupted = list(result.scalars().all())

            if interrupted:
                logger.warning(
                    f"Found {len(interrupted)} interrupted applications. " "Marking as FAILED."
                )

                for app in interrupted:
                    app.status = ApplicationStatus.FAILED
                    app.error_message = "Application interrupted by server restart"

                await db.commit()
                logger.info(f"Marked {len(interrupted)} applications as FAILED")
            else:
                logger.info("No interrupted applications found")

        except Exception as e:
            logger.error(f"Error recovering interrupted applications: {e}")
            await db.rollback()


async def cleanup_old_sessions():
    """Clean up old application sessions.

    This is a placeholder for future implementation to remove
    old session data, screenshots, and temporary files.

    Args:
        max_age_days: Maximum age in days for keeping sessions
    """

    logger.info("Session cleanup task started")

    # Future: Implement cleanup logic for:
    # - Old screenshots
    # - Expired browser sessions
    # - Temporary files
    # - Completed applications older than X days

    logger.info("Session cleanup task completed")


async def startup_tasks():
    """Run all startup tasks.

    This function should be registered with FastAPI's startup event:

        @app.on_event("startup")
        async def on_startup():
            await startup_tasks()
    """
    logger.info("Running startup tasks...")

    await recover_interrupted_applications()
    await cleanup_old_sessions()

    logger.info("Startup tasks completed")
