"""
WebSocket connection manager for real-time updates.

Handles:
- Multiple client connections per session
- Broadcasting intervention notifications
- Application progress updates
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class WebSocketMessage:
    """Structured WebSocket message."""
    type: str  # status, intervention, progress, error
    payload: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
        }


class ConnectionManager:
    """
    Manages WebSocket connections and broadcasts.

    Features:
    - Multiple connections per session
    - Global broadcasts for interventions
    - Session-specific updates
    """

    def __init__(self):
        # session_id -> list of websockets
        self._connections: dict[str, list[WebSocket]] = {}
        # user_id -> list of websockets (for user-level broadcasts)
        self._user_connections: dict[str, list[WebSocket]] = {}
        # global connections (for all interventions)
        self._global_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        session_id: str | None = None,
        user_id: str | None = None,
        global_feed: bool = False,
    ) -> None:
        """
        Accept and register a WebSocket connection.

        Args:
            websocket: WebSocket instance
            session_id: Optional session to subscribe to
            user_id: Optional user ID for user-level updates
            global_feed: Subscribe to all interventions
        """
        await websocket.accept()

        async with self._lock:
            if session_id:
                if session_id not in self._connections:
                    self._connections[session_id] = []
                self._connections[session_id].append(websocket)
                logger.info(f"WebSocket connected to session {session_id}")

            if user_id:
                if user_id not in self._user_connections:
                    self._user_connections[user_id] = []
                self._user_connections[user_id].append(websocket)
                logger.info(f"WebSocket connected for user {user_id}")

            if global_feed:
                self._global_connections.append(websocket)
                logger.info("WebSocket connected to global feed")

    async def disconnect(
        self,
        websocket: WebSocket,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            if session_id and session_id in self._connections:
                if websocket in self._connections[session_id]:
                    self._connections[session_id].remove(websocket)
                    if not self._connections[session_id]:
                        del self._connections[session_id]

            if user_id and user_id in self._user_connections:
                if websocket in self._user_connections[user_id]:
                    self._user_connections[user_id].remove(websocket)
                    if not self._user_connections[user_id]:
                        del self._user_connections[user_id]

            if websocket in self._global_connections:
                self._global_connections.remove(websocket)

        logger.info(f"WebSocket disconnected")

    async def send_to_session(
        self,
        session_id: str,
        message: WebSocketMessage | dict,
    ) -> int:
        """
        Send message to all connections watching a session.

        Returns number of successful sends.
        """
        if session_id not in self._connections:
            return 0

        msg_dict = message.to_dict() if isinstance(message, WebSocketMessage) else message
        sent = 0
        dead_connections = []

        for ws in self._connections[session_id]:
            try:
                await ws.send_json(msg_dict)
                sent += 1
            except Exception as e:
                logger.warning(f"Failed to send to session {session_id}: {e}")
                dead_connections.append(ws)

        # Clean up dead connections
        for ws in dead_connections:
            await self.disconnect(ws, session_id=session_id)

        return sent

    async def send_to_user(
        self,
        user_id: str,
        message: WebSocketMessage | dict,
    ) -> int:
        """Send message to all connections for a user."""
        if user_id not in self._user_connections:
            return 0

        msg_dict = message.to_dict() if isinstance(message, WebSocketMessage) else message
        sent = 0
        dead_connections = []

        for ws in self._user_connections[user_id]:
            try:
                await ws.send_json(msg_dict)
                sent += 1
            except Exception as e:
                logger.warning(f"Failed to send to user {user_id}: {e}")
                dead_connections.append(ws)

        for ws in dead_connections:
            await self.disconnect(ws, user_id=user_id)

        return sent

    async def broadcast_global(self, message: WebSocketMessage | dict) -> int:
        """Broadcast to all global feed connections."""
        msg_dict = message.to_dict() if isinstance(message, WebSocketMessage) else message
        sent = 0
        dead_connections = []

        for ws in self._global_connections:
            try:
                await ws.send_json(msg_dict)
                sent += 1
            except Exception as e:
                logger.warning(f"Failed to broadcast: {e}")
                dead_connections.append(ws)

        for ws in dead_connections:
            await self.disconnect(ws)

        return sent

    async def broadcast_intervention(
        self,
        intervention_id: str,
        session_id: str,
        user_id: str,
        intervention_type: str,
        title: str,
        description: str,
        current_url: str | None = None,
    ) -> int:
        """
        Broadcast an intervention notification.

        Sends to:
        - Session subscribers
        - User subscribers
        - Global feed subscribers
        """
        message = WebSocketMessage(
            type="intervention",
            payload={
                "intervention_id": intervention_id,
                "session_id": session_id,
                "user_id": user_id,
                "intervention_type": intervention_type,
                "title": title,
                "description": description,
                "current_url": current_url,
            },
        )

        sent = 0
        sent += await self.send_to_session(session_id, message)
        sent += await self.send_to_user(user_id, message)
        sent += await self.broadcast_global(message)

        logger.info(f"Intervention broadcast sent to {sent} connections")
        return sent

    async def broadcast_progress(
        self,
        session_id: str,
        step: str,
        progress_percent: int,
        details: dict[str, Any] | None = None,
    ) -> int:
        """Broadcast application progress update."""
        message = WebSocketMessage(
            type="progress",
            payload={
                "session_id": session_id,
                "step": step,
                "progress_percent": progress_percent,
                "details": details or {},
            },
        )

        return await self.send_to_session(session_id, message)

    async def broadcast_status_change(
        self,
        session_id: str,
        old_status: str,
        new_status: str,
        reason: str | None = None,
    ) -> int:
        """Broadcast status change notification."""
        message = WebSocketMessage(
            type="status_change",
            payload={
                "session_id": session_id,
                "old_status": old_status,
                "new_status": new_status,
                "reason": reason,
            },
        )

        return await self.send_to_session(session_id, message)

    def get_connection_count(self, session_id: str | None = None) -> int:
        """Get number of active connections."""
        if session_id:
            return len(self._connections.get(session_id, []))
        return sum(len(conns) for conns in self._connections.values())


# Global singleton
_connection_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager instance."""
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ConnectionManager()
    return _connection_manager
