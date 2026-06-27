from pydantic import BaseModel, Field

from ultimate_trader.validation_lab.performance_metrics import TradeResult


class TransactionCostModel(BaseModel):
    taker_fee_rate: float = 0.0004
    maker_fee_rate: float = 0.0002
    estimated_slippage_bps: float = 1.0
    funding_cost_rate: float = 0.0001

    def apply_fees(self, trade: TradeResult) -> TradeResult:
        fee_rate = self.taker_fee_rate
        if trade.gross_r != 0:
            trade.fees_r = abs(trade.gross_r) * fee_rate
        return trade

    def apply_slippage(self, trade: TradeResult) -> TradeResult:
        slippage_fraction = self.estimated_slippage_bps / 10000.0
        if trade.gross_r != 0:
            trade.slippage_r = abs(trade.gross_r) * slippage_fraction
        return trade

    def apply_funding(self, trade: TradeResult) -> TradeResult:
        if trade.gross_r != 0:
            trade.funding_r = abs(trade.gross_r) * self.funding_cost_rate
        return trade

    def calculate_net_r(self, trade: TradeResult) -> TradeResult:
        trade = self.apply_fees(trade)
        trade = self.apply_slippage(trade)
        trade = self.apply_funding(trade)
        trade.net_r = trade.gross_r - trade.fees_r - trade.slippage_r - trade.funding_r
        return trade
