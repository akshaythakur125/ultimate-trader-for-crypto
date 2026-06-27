from enum import Enum


class Bias(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NO_TRADE = "NO_TRADE"


class HypothesisStatus(str, Enum):
    DRAFT = "DRAFT"
    TESTING = "TESTING"
    PASSED = "PASSED"
    REJECTED = "REJECTED"
    RETIRED = "RETIRED"


class SignalStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class RegimeLabel(str, Enum):
    TRENDING = "trending"
    RANGING = "ranging"
    CHOPPY = "choppy"
    SQUEEZED = "squeezed"
    VOLATILE_EXPANSION = "volatile_expansion"
    LIQUIDATION_DRIVEN = "liquidation_driven"
    MANIPULATION_PRONE = "manipulation_prone"
    NO_TRADE = "no_trade"


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
