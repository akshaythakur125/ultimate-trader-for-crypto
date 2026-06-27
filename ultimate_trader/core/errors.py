class UltimateTraderError(Exception):
    """Base exception for all Ultimate Trader errors."""


class LiveTradingDisabledError(UltimateTraderError):
    """Raised when live trading is attempted while disabled."""


class ConfigurationError(UltimateTraderError):
    """Raised when system configuration is invalid."""


class DatabaseError(UltimateTraderError):
    """Raised on database connection or query failure."""


class SchemaValidationError(UltimateTraderError):
    """Raised when schema validation fails."""


class HealthCheckError(UltimateTraderError):
    """Raised when a health check fails."""


class DataProviderError(UltimateTraderError):
    """Raised when a data provider fails to return data."""


class EngineError(UltimateTraderError):
    """Raised when an intelligence engine encounters an error."""


class HypothesisError(UltimateTraderError):
    """Raised when a hypothesis is invalid or cannot be processed."""
