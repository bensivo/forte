import re

from forte.interface.document_searcher import IDocumentSearcher
from forte.model.document import DocumentMatch
from forte.model.document_markdown import from_markdown
from forte.model.vault import VaultContext, VaultLayout


class FsDocumentSearcher(IDocumentSearcher):
    """
    Filesystem implementation of IDocumentSearcher. Scans the processed copy
    of every document (``docs/processed/<id>.md``) directly on disk, one file
    at a time, in pure Python.

    Deliberately does not shell out to an external tool like ``ripgrep``:
    forte cannot assume such a tool is installed on the user's machine. If
    that assumption ever changes, the swap lives entirely behind the
    ``IDocumentSearcher`` interface — a new client can be dropped in without
    touching the service or controller layers.

    Resolves the vault root (via the injected `VaultContext`) lazily on each
    call, so it can be constructed unconditionally at wiring time, before the
    active vault is known — same pattern as `SqliteDocumentDb`.
    """

    def __init__(self, context: VaultContext):
        """
        Args:
            context (VaultContext): Holds the active vault root, resolved
                lazily on each call.
        """
        self._context = context

    def _layout(self) -> VaultLayout:
        root = self._context.get_root()
        return VaultLayout(root)

    def search(
        self, pattern: re.Pattern, limit_per_document: int | None
    ) -> list[tuple[int, list[DocumentMatch]]]:
        layout = self._layout()
        processed_dir = layout.docs_processed_dir
        if not processed_dir.is_dir():
            return []

        results: list[tuple[int, list[DocumentMatch]]] = []
        for path in sorted(processed_dir.glob("*.md")):
            try:
                document_id = int(path.stem)
            except ValueError:
                continue

            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            try:
                parsed = from_markdown(text)
            except ValueError:
                continue

            body = parsed.body
            # Cheap prefilter: I/O dominates the runtime of a typical search,
            # so run the pattern once against the whole body and only pay for
            # the line-by-line scan (which builds DocumentMatch objects and
            # spans) on files that actually contain a hit.
            if not pattern.search(body):
                continue

            matches: list[DocumentMatch] = []
            for line_number, line in enumerate(body.splitlines(), start=1):
                spans = [(m.start(), m.end()) for m in pattern.finditer(line)]
                if not spans:
                    continue
                matches.append(DocumentMatch(line_number=line_number, line=line, spans=spans))
                if limit_per_document is not None and len(matches) >= limit_per_document:
                    break

            if matches:
                results.append((document_id, matches))

        return results
