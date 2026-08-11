import re
from abc import ABC, abstractmethod

from forte.model.document import DocumentMatch


class IDocumentSearcher(ABC):
    """
    Interface for scanning stored document text for lines matching a
    pattern. Implementations handle the raw text scan only; they know
    nothing about which document ids exist as metadata, output formatting,
    or grouping order.
    """

    @abstractmethod
    def search(
        self, pattern: re.Pattern, limit_per_document: int | None
    ) -> list[tuple[int, list[DocumentMatch]]]:
        """
        Scan stored document text for lines matching ``pattern``.

        Args:
            pattern (re.Pattern): The pre-compiled pattern to match against
                each line of a document's body text.
            limit_per_document (int | None): The maximum number of matches
                to return per document, or None for no cap.

        Returns:
            (list[tuple[int, list[DocumentMatch]]]) One entry per document
                that has at least one match, pairing the document id with
                its matching lines (each capped at ``limit_per_document``).
        """
        pass
