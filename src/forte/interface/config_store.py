from abc import ABC, abstractmethod


class IConfigStore(ABC):
    """
    Interface for reading a vault's raw config data. Implementations handle
    locating and parsing the config file only; interpreting values (applying
    defaults, resolving ``${VAR}`` interpolation) is business logic that
    happens in ConfigService.
    """

    @abstractmethod
    def read(self) -> dict:
        """
        Read the vault's config file.

        Returns:
            (dict) The parsed config data. Empty if the file is missing or
            its top-level content is not a mapping.
        """
        pass
