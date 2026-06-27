from pydantic import BaseModel, Field


class BacktestProtocol(BaseModel):
    protocol_id: str
    minimum_trades_required: int = 50
    include_fees: bool = True
    include_slippage: bool = True
    include_funding: bool = True
    reject_if_too_few_trades: bool = True
    reject_if_negative_expectancy: bool = True
    reject_if_drawdown_excessive: bool = True
    reject_if_overfit_detected: bool = True
    required_out_of_sample_pass: bool = True
