from ultimate_trader.belief_engine.evidence_likelihood import EvidenceLikelihood
from ultimate_trader.belief_engine.market_belief import MarketBelief


class BayesianUpdater:
    def update(
        self,
        prior: float,
        likelihood_if_true: float,
        likelihood_if_false: float,
        reliability: float = 1.0,
    ) -> float:
        prior = max(0.001, min(0.999, prior))
        reliability = max(0.0, min(1.0, reliability))

        if reliability < 1.0:
            effective_true = 0.5 + (likelihood_if_true - 0.5) * reliability
            effective_false = 0.5 + (likelihood_if_false - 0.5) * reliability
        else:
            effective_true = likelihood_if_true
            effective_false = likelihood_if_false

        evidence_ratio = effective_true / max(effective_false, 0.001)
        prior_odds = prior / max(1.0 - prior, 0.001)
        posterior_odds = prior_odds * evidence_ratio
        posterior = posterior_odds / (1.0 + posterior_odds)

        return max(0.01, min(0.99, posterior))

    def update_belief(
        self,
        belief: MarketBelief,
        likelihood: EvidenceLikelihood,
    ) -> float:
        prior = belief.posterior_probability or belief.prior_probability
        posterior = self.update(
            prior=prior,
            likelihood_if_true=likelihood.likelihood_if_belief_true,
            likelihood_if_false=likelihood.likelihood_if_belief_false,
            reliability=likelihood.reliability_score * likelihood.evidence_weight,
        )
        return posterior

    def update_multiple(
        self,
        beliefs: list[MarketBelief],
        likelihoods: list[EvidenceLikelihood],
    ) -> list[MarketBelief]:
        likelihood_map: dict[str, list[EvidenceLikelihood]] = {}
        for lh in likelihoods:
            likelihood_map.setdefault(lh.target_belief_id, []).append(lh)

        for belief in beliefs:
            if belief.belief_id in likelihood_map:
                for lh in likelihood_map[belief.belief_id]:
                    posterior = self.update_belief(belief, lh)
                    belief.posterior_probability = posterior

        total = sum(
            b.posterior_probability or b.prior_probability
            for b in beliefs
            if b.status != "REJECTED"
        )
        if total > 0:
            for b in beliefs:
                p = b.posterior_probability or b.prior_probability
                b.posterior_probability = max(0.01, min(0.99, p / total))

        return beliefs
