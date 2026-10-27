from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from typing import Iterable

from computer_use.controllers.browser_controller import EdgeWindowInfo


@dataclass(frozen=True)
class GleanReferenceResult:
    """Parsed Glean search hit — reference only; never auto-executed."""

    title: str
    url: str
    snippet: str
    confidence: str = "reference"


@dataclass
class GleanHelper:
    """Suggest using an existing Edge Glean tab; parse results for human review only."""

    glean_title_markers: tuple[str, ...] = ("glean", "go/glean")

    def suggest_open_glean_tab(
        self,
        edge_windows: Iterable[EdgeWindowInfo],
    ) -> str:
        matches = [
            w
            for w in edge_windows
            if any(m in w.title.lower() for m in self.glean_title_markers)
        ]
        if not matches:
            return (
                "Glean: 실행 중인 Edge 창에서 Glean 탭을 찾지 못했습니다. "
                "기존 Edge에서 Glean을 연 뒤 Browser 모드에서 해당 창을 선택하세요 "
                "(새 launch/CDP 금지)."
            )
        titles = ", ".join(w.title for w in matches[:3])
        return (
            f"Glean: 기존 Edge Glean 탭 후보 — {titles}. "
            "검색 결과는 참고용으로만 파싱하며, 위험한 자동 실행은 하지 않습니다."
        )

    def parse_reference_results(self, html_or_text: str) -> list[GleanReferenceResult]:
        """Best-effort parse of Glean result HTML or plain text (no network, no clicks)."""
        text = unescape(html_or_text)
        results: list[GleanReferenceResult] = []

        for match in re.finditer(
            r'<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>',
            text,
            re.I,
        ):
            url, title = match.group(1), match.group(2).strip()
            if not title or url.startswith("javascript:"):
                continue
            snippet = self._snippet_after(text, match.end())
            results.append(GleanReferenceResult(title=title, url=url, snippet=snippet))

        if results:
            return results[:20]

        for line in text.splitlines():
            line = line.strip()
            if not line or len(line) < 8:
                continue
            url_m = re.search(r"https?://\S+", line)
            if url_m:
                results.append(
                    GleanReferenceResult(
                        title=line[:120],
                        url=url_m.group(0).rstrip(").,"),
                        snippet="",
                    )
                )
        return results[:20]

    @staticmethod
    def _snippet_after(text: str, start: int, *, max_len: int = 160) -> str:
        chunk = re.sub(r"\s+", " ", text[start : start + max_len]).strip()
        return chunk[: max_len - 3] + "..." if len(chunk) >= max_len else chunk

    def format_results_for_log(self, results: list[GleanReferenceResult]) -> str:
        if not results:
            return "Glean parse: 결과 없음 (HTML/텍스트를 붙여넣어 참고용으로만 확인하세요)."
        lines = ["Glean parse (reference only — do not auto-run):"]
        for i, r in enumerate(results[:10], 1):
            lines.append(f"  {i}. {r.title} — {r.url}")
            if r.snippet:
                lines.append(f"     {r.snippet}")
        return "\n".join(lines)
