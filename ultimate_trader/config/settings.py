from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Ultimate Trader"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    DATABASE_URL: str = "sqlite:///ultimate_trader.db"

    BINGX_API_KEY: Optional[str] = None
    BINGX_SECRET_KEY: Optional[str] = None
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None

    PAPER_TRADING_MODE: bool = True
    LIVE_TRADING_ENABLED: bool = False
    MAX_DAILY_DRAWDOWN_PERCENT: float = 10.0
    TARGET_MIN_PROFITABLE_OPPORTUNITIES_PER_DAY: int = 2
    TARGET_MAX_PROFITABLE_OPPORTUNITIES_PER_DAY: int = 4
    MIN_ACCEPTABLE_WIN_RATE: float = 0.60
    MIN_ACCEPTABLE_RR: float = 3.0
    PREFERRED_RR: float = 5.0
    MIN_CONFIDENCE_SCORE: float = 70.0
    MAX_RISK_SCORE: float = 40.0
    DEFAULT_HOLDING_TIME_MIN_HOURS: float = 4.0
    DEFAULT_HOLDING_TIME_MAX_HOURS: float = 8.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
