from ultimate_trader.strategy_engine.models import StrategyCandidate


def generate_candidate_report(candidate: StrategyCandidate) -> str:
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append(f"Candidate:       {candidate.candidate_id}")
    lines.append(f"Symbol:          {candidate.symbol} ({candidate.timeframe})")
    lines.append(f"Timestamp:       {candidate.timestamp}")
    lines.append(f"Direction:       {candidate.direction.value}")
    lines.append(f"Entry:           {candidate.entry_price}")
    lines.append(f"Stop Loss:       {candidate.stop_loss or 'N/A'}")
    lines.append(f"Target:          {candidate.target_price or 'N/A'}")
    lines.append(f"Total Confidence: {candidate.total_confidence:.1f}%")
    lines.append(f"Threshold:       {candidate._threshold if hasattr(candidate, '_threshold') else 60.0}")
    lines.append(f"Approved:        {'YES' if candidate.approved else 'NO'}")
    if candidate.rejection_reason:
        lines.append(f"Rejection:       {candidate.rejection_reason}")
    lines.append(f"Passed Filters:  {len(candidate.filters_passed)}/{len(candidate.filters_passed) + len(candidate.filters_failed)}")
    lines.append("-" * 70)
    lines.append(f"Filter          Score  Wght  WScore  Pass  Data")
    lines.append(f"{'─' * 70}")

    for name, result in candidate.filter_results.items():
        ws = f"{result.weighted_score:.1f}" if result.data_available else "N/A"
        data_flag = "Y" if result.data_available else "N"
        pass_flag = "Y" if result.passed else "N"
        lines.append(f"{name:<18} {result.score:>5.1f} {result.weight:>4.2f} {ws:>6}  {pass_flag:>4}  {data_flag}")

    lines.append("-" * 70)
    lines.append("Reasoning:")
    for name, result in candidate.filter_results.items():
        for reason in result.reasoning:
            lines.append(f"  [{name}] {reason}")

    lines.append("=" * 70)
    return "\n".join(lines)
