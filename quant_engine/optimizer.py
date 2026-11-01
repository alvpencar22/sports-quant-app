import itertools
from typing import List, Dict, Any, Tuple, Optional

class BulletLeg:
    def __init__(self, leg_id: str, desc: str, cr: float, hr: float, be: float, ev: float, category: str, player: Optional[str] = None):
        self.leg_id = leg_id
        self.desc = desc
        self.cr = cr
        self.hr = hr          # in % (e.g. 75.0)
        self.prob = hr / 100.0
        self.be = be
        self.ev = ev
        self.category = category
        self.player = player

    def to_dict(self) -> Dict[str, Any]:
        return {
            'leg_id': self.leg_id,
            'desc': self.desc,
            'cr': self.cr,
            'hr': self.hr,
            'be': self.be,
            'ev': self.ev,
            'category': self.category,
            'player': self.player
        }

class Bullet:
    def __init__(self, legs: List[BulletLeg]):
        self.legs = legs
        self.num_legs = len(legs)
        
        # Combined odds
        prod_cr = 1.0
        for leg in legs:
            prod_cr *= leg.cr
        self.cr = round(prod_cr, 2)
        
        # Joint probability assuming empirical independence
        prod_prob = 1.0
        for leg in legs:
            prod_prob *= leg.prob
        self.prob = prod_prob
        self.hr = round(prod_prob * 100.0, 1)
        
        self.be = round(1.0 / self.prob, 2) if self.prob > 0 else 999.0
        self.ev = round((self.cr * self.prob) - 1.0, 4)
        
        # Unique identifier of legs
        self.leg_ids = set(leg.leg_id for leg in legs)
        self.players = set(leg.player for leg in legs if leg.player)

    def shares_legs_with(self, other: 'Bullet') -> bool:
        """Verifica si comparte alguna selección individual o jugador con otra bala."""
        if not self.leg_ids.isdisjoint(other.leg_ids):
            return True
        if self.players and other.players and not self.players.isdisjoint(other.players):
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            'tipo': 'Simple (1 Leg)' if self.num_legs == 1 else 'Doble (2 Legs)',
            'cr': self.cr,
            'hr': self.hr,
            'be': self.be,
            'ev': self.ev,
            'legs': [l.to_dict() for l in self.legs]
        }

class BulletOptimizer:
    """
    Optimizador Combinatorio de Balas Definitivas.
    Construye candidatos (simples y dobles), aplica restricciones de cuota objetivo [@ 1.80 – @ 2.35]
    y resuelve la selección óptima de 3 Balas estrictamente disjuntas (0 solapamiento).
    """

    def __init__(
        self,
        min_odds: float = 1.80,
        max_odds: float = 2.35,
        max_legs_per_bullet: int = 2
    ):
        self.min_odds = min_odds
        self.max_odds = max_odds
        self.max_legs_per_bullet = max_legs_per_bullet

    def build_candidate_bullets(self, legs: List[BulletLeg]) -> List[Bullet]:
        """Genera todas las balas individuales y dobles válidas dentro del rango de cuotas."""
        candidates = []

        # 1. Balas simples (1 Leg)
        for leg in legs:
            if self.min_odds <= leg.cr <= self.max_odds:
                b = Bullet([leg])
                if b.ev > -0.05: # Allow slightly neutral/positive EV
                    candidates.append(b)

        # 2. Balas dobles (2 Legs)
        for leg1, leg2 in itertools.combinations(legs, 2):
            # No combinar pronósticos del mismo jugador o categoría idéntica en la misma bala
            if leg1.player and leg2.player and leg1.player.lower() == leg2.player.lower():
                continue
            combined_cr = leg1.cr * leg2.cr
            if self.min_odds <= combined_cr <= self.max_odds:
                b = Bullet([leg1, leg2])
                if b.ev > -0.05:
                    candidates.append(b)

        # Ordenar candidatos por EV descendente
        candidates.sort(key=lambda b: (b.ev, b.hr), reverse=True)
        return candidates

    def optimize_triplets(
        self,
        candidate_bullets: List[Bullet],
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Encuentra los mejores tríos de 3 Balas con 0 solapamiento entre ellas,
        maximizando el EV conjunto y la probabilidad de acierto múltiple.
        """
        valid_triplets = []
        n_cand = len(candidate_bullets)

        # Limitar espacio de búsqueda a los mejores candidatos para máxima eficiencia
        pool = candidate_bullets[:45]

        for i in range(len(pool)):
            b1 = pool[i]
            for j in range(i + 1, len(pool)):
                b2 = pool[j]
                if b1.shares_legs_with(b2):
                    continue
                for k in range(j + 1, len(pool)):
                    b3 = pool[k]
                    if b1.shares_legs_with(b3) or b2.shares_legs_with(b3):
                        continue

                    # Calcular métricas conjuntas del trío
                    ev_total = round(b1.ev + b2.ev + b3.ev, 4)
                    
                    p1, p2, p3 = b1.prob, b2.prob, b3.prob
                    
                    # Probabilidad de ganar exactamente k balas
                    prob_3_wins = p1 * p2 * p3
                    prob_2_wins = (p1 * p2 * (1 - p3)) + (p1 * (1 - p2) * p3) + ((1 - p1) * p2 * p3)
                    prob_at_least_2 = round((prob_3_wins + prob_2_wins) * 100.0, 1)
                    
                    prob_0_wins = (1 - p1) * (1 - p2) * (1 - p3)
                    prob_at_least_1 = round((1.0 - prob_0_wins) * 100.0, 1)

                    avg_hr = round(((b1.hr + b2.hr + b3.hr) / 3.0), 1)

                    score_ev = ev_total
                    score_certainty = prob_at_least_2

                    valid_triplets.append({
                        'b1': b1,
                        'b2': b2,
                        'b3': b3,
                        'ev_total': ev_total,
                        'prob_at_least_2': prob_at_least_2,
                        'prob_at_least_1': prob_at_least_1,
                        'avg_hr': avg_hr,
                        'score_balanced': round(ev_total * 10.0 + (prob_at_least_2 / 10.0), 2)
                    })

        if not valid_triplets:
            return []

        # Ordenar por diferentes criterios estratégicos
        by_ev = sorted(valid_triplets, key=lambda t: t['ev_total'], reverse=True)
        by_certainty = sorted(valid_triplets, key=lambda t: (t['prob_at_least_2'], t['ev_total']), reverse=True)
        by_balanced = sorted(valid_triplets, key=lambda t: t['score_balanced'], reverse=True)

        results = []
        seen_signatures = set()

        def add_result(label: str, t: Dict[str, Any]):
            sig = tuple(sorted([
                tuple(sorted(t['b1'].leg_ids)),
                tuple(sorted(t['b2'].leg_ids)),
                tuple(sorted(t['b3'].leg_ids))
            ]))
            if sig not in seen_signatures:
                seen_signatures.add(sig)
                results.append({
                    'estrategia': label,
                    'ev_total': t['ev_total'],
                    'prob_al_menos_2_aciertos': f"{t['prob_at_least_2']}%",
                    'prob_al_menos_1_acierto': f"{t['prob_at_least_1']}%",
                    'hr_promedio': f"{t['avg_hr']}%",
                    'bala_1': t['b1'].to_dict(),
                    'bala_2': t['b2'].to_dict(),
                    'bala_3': t['b3'].to_dict()
                })

        if by_ev:
            add_result('Opción A: Máximo EV / Edge Puro', by_ev[0])
        if by_certainty:
            add_result('Opción B: Máxima Certeza (P>=2 Wins)', by_certainty[0])
        if by_balanced:
            add_result('Opción C: Balance Óptimo (Sharpe / Consistencia)', by_balanced[0])

        # Rellenar con los siguientes mejores si hace falta
        for t in by_balanced:
            if len(results) >= top_k:
                break
            add_result(f"Opción Alternativa #{len(results) + 1}", t)

        return results
