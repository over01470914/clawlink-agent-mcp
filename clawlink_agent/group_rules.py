"""Group chat rules: @mention parsing, response checks, message fetching."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_MENTION_RE = re.compile(r"@([\w\-\.]+)")


def parse_mentions(content: str) -> List[str]:
    """Extract all @agent_id / @user tokens from message text.

    Args:
        content: Raw message text.

    Returns:
        List of mentioned identifiers (without the @ prefix).
    """
    return _MENTION_RE.findall(content)


def should_respond(message_content: str, my_agent_id: str) -> bool:
    """Check whether *my_agent_id* is explicitly @mentioned in the message.

    Args:
        message_content: Raw message text.
        my_agent_id: This agent's identifier.

    Returns:
        True if the agent should respond.
    """
    mentions = parse_mentions(message_content)
    return my_agent_id.lower() in [m.lower() for m in mentions]


def format_mention(agent_id: str) -> str:
    """Return the canonical @mention string for an agent.

    Args:
        agent_id: Agent identifier.

    Returns:
        Formatted mention string, e.g. ``"@my-agent"``.
    """
    return f"@{agent_id}"


async def fetch_messages(
    router_url: str,
    session_id: str,
    agent_id: str,
    since: Optional[datetime] = None,
) -> List[Dict]:
    """Fetch group chat messages from the Router's ``/fetch-messages`` endpoint.

    Args:
        router_url: Base URL of the Router (e.g. ``http://localhost:8420``).
        session_id: Chat session / room ID.
        agent_id: Requesting agent's ID.
        since: Optional datetime; only return messages after this time.

    Returns:
        List of message dicts as returned by the Router.
    """
    url = f"{router_url.rstrip('/')}/fetch-messages"
    params: Dict[str, str] = {
        "session_id": session_id,
        "agent_id": agent_id,
    }
    if since is not None:
        params["since"] = since.isoformat(timespec="seconds") + "Z"

    logger.debug("Fetching messages from %s with params %s", url, params)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            messages: List[Dict] = data if isinstance(data, list) else data.get("messages", [])
            logger.info("Fetched %d messages from Router", len(messages))
            return messages
    except httpx.HTTPStatusError as exc:
        logger.error("Router returned %s: %s", exc.response.status_code, exc.response.text)
        return []
    except httpx.RequestError as exc:
        logger.error("Failed to reach Router at %s: %s", url, exc)
        return []


def fetch_messages_sync(
    router_url: str,
    session_id: str,
    agent_id: str,
    since: Optional[datetime] = None,
) -> List[Dict]:
    """Synchronous variant of :func:`fetch_messages`.

    Useful for CLI or non-async contexts.
    """
    url = f"{router_url.rstrip('/')}/fetch-messages"
    params: Dict[str, str] = {
        "session_id": session_id,
        "agent_id": agent_id,
    }
    if since is not None:
        params["since"] = since.isoformat(timespec="seconds") + "Z"

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            messages: List[Dict] = data if isinstance(data, list) else data.get("messages", [])
            return messages
    except httpx.HTTPStatusError as exc:
        logger.error("Router returned %s: %s", exc.response.status_code, exc.response.text)
        return []
    except httpx.RequestError as exc:
        logger.error("Failed to reach Router at %s: %s", url, exc)
        return []
