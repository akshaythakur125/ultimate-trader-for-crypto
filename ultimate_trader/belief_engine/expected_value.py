import math
from typing import Optional

from pydantic import BaseModel


class ExpectedValueResult(BaseModel):
    probability_of_win: float
    probability_of_loss: float
    average_win_r: float
    average_loss_r: float
    expected_value_r: float
    required_win_rate_for_breakeven: float
    margin_of_safety: float
    is_positive_ev: bool
    ev_summary: str = ""


class ExpectedValueCalculator:
    def calculate(
        self,
        probability_of_win: float,
        average_win_r: float,
        probability_of_loss: float,
        average_loss_r: float,
    ) -> ExpectedValueResult:
        total = probability_of_win + probability_of_loss
        if total == 0:
            return ExpectedValueResult(
                probability_of_win=0,
                probability_of_loss=0,
                average_win_r=average_win_r,
                average_loss_r=average_loss_r,
                expected_value_r=0.0,
                required_win_rate_for_breakeven=0.0,
                margin_of_safety=0.0,
                is_positive_ev=False,
                ev_summary="No probabilities provided",
            )

        p_win = probability_of_win / total
        p_loss = probability_of_loss / total

        ev = p_win * average_win_r - p_loss * average_loss_r

        if average_win_r + average_loss_r > 0:
            breakeven = average_loss_r / (average_win_r + average_loss_r)
        else:
            breakeven = 0.5

        margin = p_win - breakeven

        return ExpectedValueResult(
            probability_of_win=round(p_win, 4),
            probability_of_loss=round(p_loss, 4),
            average_win_r=average_win_r,
            average_loss_r=average_loss_r,
            expected_value_r=round(ev, 4),
            required_win_rate_for_breakeven=round(breakeven, 4),
            margin_of_safety=round(margin, 4),
            is_positive_ev=ev > 0,
            ev_summary=(
                f"EV={ev:+.3f}R | Win={p_win:.1%} @ {average_win_r:.1f}R / "
                f"Loss={p_loss:.1%} @ {average_loss_r:.1f}R | "
                f"Breakeven win rate={breakeven:.1%}"
            ),
        )

    def calculate_from_beliefs(
        self,
        probability_of_win: float,
        average_win_r: float,
        probability_of_no_trade: float = 0.0,
        average_loss_r: float = 1.0,
    ) -> ExpectedValueResult:
        prob_loss = max(0.0, 1.0 - probability_of_win - probability_of_no_trade)
        return self.calculate(probability_of_win, average_win_r, prob_loss, average_loss_r)
