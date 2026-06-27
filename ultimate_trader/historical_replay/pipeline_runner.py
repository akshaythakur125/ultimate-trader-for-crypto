from datetime import datetime
from typing import Any, Optional

from ultimate_trader.historical_replay.candle_replayer import CandleReplayer
from ultimate_trader.historical_replay.data_loader import HistoricalDataLoader
from ultimate_trader.historical_replay.models import (
    HistoricalCandle,
    ReplayConfig,
    TradeDirection,
    TradePlan,
)
from ultimate_trader.historical_replay.replay_journal import ReplayJournal


class ReplayPipelineRunner:
    def __init__(
        self,
        config: ReplayConfig,
        journal: ReplayJournal,
        liquidity_smart_money: Optional[Any] = None,
        microstructure_engine: Optional[Any] = None,
        orderflow_intelligence: Optional[Any] = None,
        research_brain: Optional[Any] = None,
        belief_engine: Optional[Any] = None,
        validation_lab: Optional[Any] = None,
        signal_engine: Optional[Any] = None,
    ) -> None:
        self._config = config
        self._journal = journal
        self._lsm = liquidity_smart_money
        self._ms = microstructure_engine
        self._ofi = orderflow_intelligence
        self._research = research_brain
        self._belief = belief_engine
        self._validation = validation_lab
        self._signal = signal_engine
        self._pending_plans: list[TradePlan] = []
        self._current_candle_index = 0

    @property
    def journal(self) -> ReplayJournal:
        return self._journal

    @property
    def pending_plans(self) -> list[TradePlan]:
        return self._pending_plans

    def run_candle(
        self,
        candle: HistoricalCandle,
        candle_index: int,
    ) -> Optional[TradePlan]:
        self._current_candle_index = candle_index
        reason = None

        lsm_report = None
        if self._lsm is not None:
            try:
                lsm_report = self._run_lsm(candle)
            except Exception as e:
                self._journal.add_engine_skip("liquidity_smart_money", str(e))
                lsm_report = None
        else:
            self._journal.add_engine_skip("liquidity_smart_money", "Engine not provided")

        ms_report = None
        if self._ms is not None:
            try:
                ms_report = self._run_ms(candle)
            except Exception as e:
                self._journal.add_engine_skip("microstructure_engine", str(e))
                ms_report = None
        else:
            self._journal.add_engine_skip("microstructure_engine", "Engine not provided")

        ofi_report = None
        if self._ofi is not None:
            try:
                ofi_report = self._run_ofi(candle)
            except Exception as e:
                self._journal.add_engine_skip("orderflow_intelligence", str(e))
                ofi_report = None
        else:
            self._journal.add_engine_skip("orderflow_intelligence", "Engine not provided")

        research_result = None
        if self._research is not None:
            try:
                research_result = self._run_research(candle)
            except Exception as e:
                self._journal.add_engine_skip("research_brain", str(e))
        else:
            self._journal.add_engine_skip("research_brain", "Engine not provided")

        belief_result = None
        if self._belief is not None:
            try:
                belief_result = self._run_belief(candle)
            except Exception as e:
                self._journal.add_engine_skip("belief_engine", str(e))
        else:
            self._journal.add_engine_skip("belief_engine", "Engine not provided")

        validation_result = None
        if self._validation is not None:
            try:
                validation_result = self._run_validation(candle)
            except Exception as e:
                self._journal.add_engine_skip("validation_lab", str(e))
        else:
            self._journal.add_engine_skip("validation_lab", "Engine not provided")

        if self._signal is None:
            self._journal.add_engine_skip("signal_engine", "Engine not provided")

        try:
            trade_permission = None
            confluence_score = 0.0
            if lsm_report is not None and hasattr(lsm_report, "trade_permission"):
                trade_permission = lsm_report.trade_permission
            if lsm_report is not None and hasattr(lsm_report, "confluence"):
                if lsm_report.confluence is not None:
                    confluence_score = lsm_report.confluence.confluence_score

            plan = self._generate_plan(
                candle=candle,
                lsm_report=lsm_report,
                ms_report=ms_report,
                ofi_report=ofi_report,
                trade_permission=trade_permission,
                confluence_score=confluence_score,
            )
            if plan is not None:
                self._pending_plans.append(plan)
                self._journal.add_plan(plan)
                return plan
        except Exception as e:
            self._journal.add_engine_skip("signal_engine", str(e))

        return None

    def _run_lsm(self, candle: HistoricalCandle) -> Any:
        swing = self._lsm.get("swing_detector")
        pools = self._lsm.get("liquidity_pool_detector")
        sweep = self._lsm.get("sweep_detector")
        structure = self._lsm.get("market_structure_engine")
        fvg_det = self._lsm.get("fair_value_gap_detector")
        ob_det = self._lsm.get("order_block_detector")
        pd = self._lsm.get("premium_discount_engine")
        disp = self._lsm.get("displacement_engine")
        conf = self._lsm.get("confluence_engine")

        ls_candle = None
        if swing is not None:
            swing.add_candle(candle)

        sh = swing.get_swing_highs() if swing else []
        sl = swing.get_swing_lows() if swing else []
        eh = swing.get_equal_highs() if swing else []
        el = swing.get_equal_lows() if swing else []

        current_price = candle.close
        zones = pools.analyze(sh, sl, eh, el, current_price, []) if pools else []
        sweeps_list = sweep.analyze([candle], zones) if sweep else []
        struct_events = structure.analyze(sh, sl, [candle]) if structure else []
        fvgs_list = fvg_det.analyze([candle]) if fvg_det else []
        obs = ob_det.analyze([candle], fvgs_list) if ob_det else []
        pd_state = pd.analyze(sh, sl, current_price) if pd else None
        disp_result = disp.analyze([candle]) if disp else None

        from ultimate_trader.liquidity_smart_money.liquidity_report import (
            LiquiditySmartMoneyReport,
        )

        conf_result = conf.analyze(zones, sweeps_list, struct_events, fvgs_list, obs, pd_state, [disp_result] if disp_result else []) if conf else None
        if conf_result is None:
            return None

        report = LiquiditySmartMoneyReport.build(
            symbol=candle.symbol,
            swing_highs=sh,
            swing_lows=sl,
            equal_highs=eh,
            equal_lows=el,
            liquidity_pools=zones,
            sweeps=sweeps_list,
            structure_events=struct_events,
            fvgs=fvgs_list,
            order_blocks=obs,
            premium_discount=pd_state,
            displacements=[disp_result] if disp_result else [],
            confluence=conf_result,
            timeframe=candle.timeframe,
        )
        return report

    def _run_ms(self, candle: HistoricalCandle) -> Any:
        return {"status": "skipped", "reason": "microstructure requires orderbook data"}

    def _run_ofi(self, candle: HistoricalCandle) -> Any:
        return {"status": "skipped", "reason": "orderflow requires trade print data"}

    def _run_research(self, candle: HistoricalCandle) -> Any:
        return {"status": "skipped", "reason": "research_brain not connected"}

    def _run_belief(self, candle: HistoricalCandle) -> Any:
        return {"status": "skipped", "reason": "belief_engine not connected"}

    def _run_validation(self, candle: HistoricalCandle) -> Any:
        return {"status": "skipped", "reason": "validation_lab not connected"}

    def _generate_plan(
        self,
        candle: HistoricalCandle,
        lsm_report: Any,
        ms_report: Any,
        ofi_report: Any,
        trade_permission: Any,
        confluence_score: float,
    ) -> Optional[TradePlan]:
        if trade_permission is not None and trade_permission == "BLOCK":
            self._journal.add_rejection(candle.timestamp.isoformat(), "trade_permission=BLOCK")
            return None

        if confluence_score < self._config.confluence_score_threshold:
            self._journal.add_rejection(
                candle.timestamp.isoformat(),
                f"confluence_score={confluence_score:.1f} < threshold={self._config.confluence_score_threshold}",
            )
            return None

        direction = None
        bias = None
        if lsm_report is not None and hasattr(lsm_report, "directional_bias"):
            bias = lsm_report.directional_bias
        if bias is not None and bias.value in ("LONG", "SHORT"):
            direction = TradeDirection(bias.value)
        else:
            self._journal.add_rejection(candle.timestamp.isoformat(), f"no clear directional bias: {bias}")
            return None

        stop_dist = (candle.high - candle.low) * self._config.stop_distance_multiplier
        if stop_dist <= 0:
            self._journal.add_rejection(candle.timestamp.isoformat(), "stop_dist <= 0")
            return None

        if direction == TradeDirection.LONG:
            entry_zone_low = candle.close - stop_dist * 0.1
            entry_zone_high = candle.close + stop_dist * 0.1
            stop_loss = candle.close - stop_dist
            target_price = candle.close + stop_dist * self._config.target_rr
        else:
            entry_zone_low = candle.close - stop_dist * 0.1
            entry_zone_high = candle.close + stop_dist * 0.1
            stop_loss = candle.close + stop_dist
            target_price = candle.close - stop_dist * self._config.target_rr

        import uuid

        plan = TradePlan(
            plan_id=f"TP-{uuid.uuid4().hex[:8].upper()}",
            symbol=candle.symbol,
            direction=direction,
            signal_time=candle.timestamp,
            entry_zone_high=entry_zone_high,
            entry_zone_low=entry_zone_low,
            stop_loss=stop_loss,
            target_price=target_price,
            plan_reason=f"confluence_score={confluence_score:.1f}, bias={direction.value}",
        )
        return plan

    def reset(self) -> None:
        self._pending_plans.clear()
        self._current_candle_index = 0
