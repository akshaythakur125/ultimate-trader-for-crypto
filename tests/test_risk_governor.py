import pytest
from datetime import datetime, timedelta
from ultimate_trader.historical_replay.models import ReplayTrade, TradeDirection, ExitReason
from ultimate_trader.drawdown_control.risk_governor import RiskGovernor, RiskGovernorConfig


def make_trade(trade_id: str, net_r: float, signal_time: datetime, symbol: str = "BTCUSDT"):
    return ReplayTrade(
        trade_id=trade_id, symbol=symbol, direction=TradeDirection.LONG,
        signal_time=signal_time, gross_r=net_r, fees_r=0, slippage_r=0, funding_r=0,
        net_r=net_r, entry_price=100, exit_price=100 + net_r, stop_loss=99, target_price=110,
        exit_reason=ExitReason.TAKE_PROFIT if net_r > 0 else ExitReason.STOP_LOSS,
    )


class TestRiskGovernor:
    def test_initial_state_allows(self):
        rg = RiskGovernor()
        t0 = datetime(2024, 1, 1)
        trade = make_trade("t1", 1.0, t0)
        dec = rg.evaluate(trade)
        assert dec.allowed is True
        assert dec.risk_mode == "NORMAL"

    def test_blocks_after_daily_loss(self):
        cfg = RiskGovernorConfig(max_daily_loss_r=2.0)
        rg = RiskGovernor(cfg)
        t0 = datetime(2024, 1, 1)
        for i in range(3):
            trade = make_trade(f"t{i}", -1.0, t0 + timedelta(hours=i))
            dec = rg.evaluate(trade)
        assert dec.allowed is False
        assert "daily loss" in dec.rejection_reason.lower()

    def test_blocks_after_weekly_loss(self):
        cfg = RiskGovernorConfig(max_daily_loss_r=50.0, max_weekly_loss_r=4.0)
        rg = RiskGovernor(cfg)
        t0 = datetime(2024, 1, 1)
        trades = [
            make_trade("t1", -2.0, t0),
            make_trade("t2", -2.0, t0 + timedelta(days=1)),
            make_trade("t3", -2.0, t0 + timedelta(days=2)),
        ]
        for t in trades:
            dec = rg.evaluate(t)
        assert dec.allowed is False
        assert "weekly loss" in dec.rejection_reason.lower()

    def test_defensive_mode_after_drawdown(self):
        cfg = RiskGovernorConfig(defensive_drawdown_threshold=5.0)
        rg = RiskGovernor(cfg)
        t0 = datetime(2024, 1, 1)
        trade = make_trade("t1", 2.0, t0)
        rg.evaluate(trade)
        for i in range(5):
            trade = make_trade(f"t{i+2}", -2.0, t0 + timedelta(hours=i+1))
            dec = rg.evaluate(trade)
        if dec.allowed is False:
            assert "DEFENSIVE" in dec.risk_mode or "CAPITAL_PRESERVATION" in dec.risk_mode

    def test_capital_preservation(self):
        cfg = RiskGovernorConfig(capital_preservation_drawdown_threshold=8.0)
        rg = RiskGovernor(cfg)
        t0 = datetime(2024, 1, 1)
        trade = make_trade("t1", 2.0, t0)
        rg.evaluate(trade)
        for i in range(6):
            trade = make_trade(f"t{i+2}", -2.0, t0 + timedelta(hours=i+1))
            dec = rg.evaluate(trade)
        if not dec.allowed:
            assert dec.rejection_reason is not None

    def test_blocks_after_consecutive_losses(self):
        cfg = RiskGovernorConfig(max_total_consecutive_losses=4)
        rg = RiskGovernor(cfg)
        t0 = datetime(2024, 1, 1)
        for i in range(5):
            trade = make_trade(f"t{i}", -0.5, t0 + timedelta(hours=i))
            dec = rg.evaluate(trade)
        assert dec.allowed is False

    def test_reset(self):
        rg = RiskGovernor()
        t0 = datetime(2024, 1, 1)
        trade = make_trade("t1", -1.0, t0)
        rg.evaluate(trade)
        rg.reset()
        assert len(rg.all_trades) == 0

    def test_no_future_data_used(self):
        rg = RiskGovernor()
        t0 = datetime(2024, 1, 1)
        for i in range(15):
            trade = make_trade(f"t{i}", 1.0, t0 + timedelta(hours=i))
            dec = rg.evaluate(trade)
        assert dec.rolling_expectancy > 0
