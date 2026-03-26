"""Generate YAML-fronted Markdown files from MemoryEntry objects."""

from __future__ import annotations

import logging
from typing import List

import yaml

from .models import MemoryEntry

logger = logging.getLogger(__name__)


class MemoryFileGenerator:
    """Produces the canonical Markdown representation of a memory.

    Format::

        ---
        id: abc123
        topic: "Some Topic"
        ...
        ---

        ## Triadic Concepts

        | Topic | Action | Evidence |
        |-------|--------|----------|
        | ...   | ...    | ...      |

        ## Score History

        - **Score:** 0.85
        - **Confidence:** 0.90

        ## Transcript Highlights

        > highlight text ...
    """

    @staticmethod
    def generate(entry: MemoryEntry) -> str:
        """Render a MemoryEntry as a YAML-fronted Markdown string."""
        # -- front matter (exclude body-only fields) -------------------------
        meta = entry.model_dump()
        # transcript_highlights are rendered in body; remove from front-matter
        highlights = meta.pop("transcript_highlights", [])

        front = yaml.dump(meta, default_flow_style=False, allow_unicode=True, sort_keys=False)
        lines: List[str] = ["---", front.rstrip(), "---", ""]

        # -- triadic concepts table ------------------------------------------
        concepts = entry.concepts
        if concepts:
            lines.append("## Triadic Concepts")
            lines.append("")
            lines.append("| Topic | Action | Evidence |")
            lines.append("|-------|--------|----------|")
            for concept in concepts:
                parts = [p.strip() for p in concept.split(";")]
                if len(parts) >= 3:
                    lines.append(f"| {parts[0]} | {parts[1]} | {parts[2]} |")
                else:
                    lines.append(f"| {concept} | | |")
            lines.append("")

        # -- score history ---------------------------------------------------
        lines.append("## Score History")
        lines.append("")
        lines.append(f"- **Score:** {entry.score:.2f}")
        lines.append(f"- **Confidence:** {entry.confidence:.2f}")
        lines.append(f"- **Status:** {entry.status}")
        lines.append(f"- **Strictness:** {entry.strictness:.2f}")
        lines.append("")

        # -- transcript highlights -------------------------------------------
        if highlights:
            lines.append("## Transcript Highlights")
            lines.append("")
            for hl in highlights:
                for hl_line in hl.splitlines():
                    lines.append(f"> {hl_line}")
                lines.append("")

        return "\n".join(lines) + "\n"
