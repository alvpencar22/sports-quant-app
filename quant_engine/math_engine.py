import math
from collections import defaultdict
from typing import List, Dict, Any, Tuple, Optional

CJ_INTERVALS = [
    ("CJ <= 1.40", "Máxima Confianza", lambda cj: cj <= 1.40),
    ("CJ 1.41 - 1.60", "Confianza Media", lambda cj: 1.40 < cj <= 1.60),
    ("CJ 1.61 - 1.80", "Confianza Moderada", lambda cj: 1.60 < cj <= 1.80),
    ("CJ > 1.80", "Especulativa", lambda cj: cj > 1.80)
]

def get_cj_interval(cj: Optional[float]) -> Tuple[str, str]:
    """Retorna el código y etiqueta de la franja de Cuota Justa."""
    if cj is None:
        return ("CJ Desconocida", "Sin clasificar")
    for code, label, cond in CJ_INTERVALS:
        if cond(cj):
            return (code, label)
    return ("CJ > 1.80", "Especulativa")

class QuantEngine:
    """
    Motor Cuantitativo Imparcial de Análisis de Líneas, Franjas y Márgenes.
    Calcula Hit Rates, Cuotas Break-Even y Valor Esperado (EV) para cualquier mercado
    y cualquier desplazamiento de línea X+k (de X-6 a X+6 y Unders).
    """

    def __init__(self, records: List[Dict[str, Any]]):
        self.raw_records = records
        # Filtrar solo registros concluidos con veredicto SI o NO
        self.settled_records = [
            r for r in records 
            if r.get('veredicto') in ['SI', 'NO']
        ]

    def filter_records(
        self,
        category: Optional[str] = None,
        cj: Optional[float] = None,
        league: Optional[str] = None,
        require_cj: bool = True
    ) -> List[Dict[str, Any]]:
        """Filtra registros por categoría, cuota justa y/o liga."""
        res = self.settled_records
        if require_cj:
            res = [r for r in res if r.get('cj') is not None]
        if category:
            cat_norm = category.strip().lower()
            res = [r for r in res if r.get('cat', '').strip().lower() == cat_norm]
        if cj is not None:
            _, _, cond = next(
                ((code, label, c) for code, label, c in CJ_INTERVALS if c(cj)),
                (None, None, lambda c: True)
            )
            res = [r for r in res if cond(r.get('cj'))]
        if league:
            res = [r for r in res if r.get('league', '').lower() == league.lower()]
        return res

    def compute_basic_stats(self, subset: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calcula estadísticas básicas: N, W, L, Hit Rate %, Cuota Break-Even."""
        n = len(subset)
        if n == 0:
            return {'n': 0, 'w': 0, 'l': 0, 'hr': 0.0, 'be': 999.0}
        w = sum(1 for r in subset if r.get('veredicto') == 'SI')
        l = n - w
        hr = round((w / n) * 100.0, 1)
        be = round(100.0 / hr, 2) if hr > 0 else 999.0
        return {'n': n, 'w': w, 'l': l, 'hr': hr, 'be': be}

    def get_matches_summary(self) -> List[Dict[str, Any]]:
        """
        Retorna el resumen de todos los partidos registrados en el historial:
        match_id, match_name, league, total de pronósticos, muestra concluida, aciertos, HR y BE.
        """
        matches_dict = {}
        for r in self.raw_records:
            mid = r.get('match_id')
            if not mid:
                continue
            if mid not in matches_dict:
                matches_dict[mid] = {
                    'match_id': mid,
                    'match_name': r.get('match_name', f"Partido {mid}"),
                    'league': r.get('league', 'Otras Ligas'),
                    'records': []
                }
            matches_dict[mid]['records'].append(r)

        summary = []
        for mid in sorted(matches_dict.keys()):
            item = matches_dict[mid]
            recs = item['records']
            settled = [r for r in recs if r.get('veredicto') in ['SI', 'NO']]
            st = self.compute_basic_stats(settled)
            summary.append({
                'match_id': mid,
                'match_name': item['match_name'],
                'league': item['league'],
                'total_pronosticos': len(recs),
                'n_concluido': st['n'],
                'w_aciertos': st['w'],
                'hr': st['hr'],
                'be': st['be'],
                'records': recs
            })
        return summary

    def compute_ev(self, cr: Optional[float], hr: float) -> Tuple[Optional[float], Optional[float]]:
        """
        Calcula el Valor Esperado (EV) y el Margen de Valor (CR - BE).
        EV = (CR * HR / 100) - 1
        """
        if cr is None or cr <= 0 or hr <= 0:
            return (None, None)
        be = 100.0 / hr
        ev = round((cr * (hr / 100.0)) - 1.0, 4)
        val_margin = round(cr - be, 2)
        return (ev, val_margin)

    def compute_line_offset_stats(
        self,
        category: str,
        cj: Optional[float] = None,
        league: Optional[str] = None,
        k: int = 0,
        is_under: bool = False,
        cr: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calcula las métricas empíricas para un desplazamiento arbitrario X + k.
        - Para Over X + k: el pronóstico acierta si Margen >= k.
        - Para Under X + k: el pronóstico acierta si Margen < k.
        Soporta k desde -6 hasta +6 sin ningún sesgo.
        """
        subset = self.filter_records(category=category, cj=cj, league=league)
        n_total = len(subset)

        if n_total == 0:
            return {
                'category': category,
                'k': k,
                'is_under': is_under,
                'n': 0,
                'w': 0,
                'hr': 0.0,
                'be': 999.0,
                'ev': None,
                'margin_used': False
            }

        # Records with explicit margin
        with_margin = [r for r in subset if r.get('margen') is not None]
        n_m = len(with_margin)

        if is_under:
            # Under X + k acierta si Margen < k
            if n_m > 0:
                w = sum(1 for r in with_margin if r['margen'] < k)
                n = n_m
            else:
                w = sum(1 for r in subset if r.get('veredicto') == 'NO')
                n = n_total
        else:
            # Over X + k
            if k == 0:
                w = sum(1 for r in subset if r.get('veredicto') == 'SI')
                n = n_total
            else:
                if n_m > 0:
                    w = sum(1 for r in with_margin if r['margen'] >= k)
                    n = n_m
                else:
                    w = sum(1 for r in subset if r.get('veredicto') == 'SI')
                    n = n_total

        hr = round((w / n) * 100.0, 1) if n > 0 else 0.0
        be = round(100.0 / hr, 2) if hr > 0 else 999.0
        ev, val_margin = self.compute_ev(cr, hr)

        label = f"Under X{'+' if k>0 else ''}{k if k!=0 else ''}" if is_under else f"Over X{'+' if k>0 else ''}{k if k!=0 else ''}"

        return {
            'category': category,
            'label': label,
            'k': k,
            'is_under': is_under,
            'n': n,
            'w': w,
            'hr': hr,
            'be': be,
            'cr': cr,
            'ev': ev,
            'val_margin': val_margin
        }

    def compute_all_offsets_spectrum(
        self,
        category: str,
        cj: Optional[float] = None,
        league: Optional[str] = None,
        k_min: int = -6,
        k_max: int = 6
    ) -> List[Dict[str, Any]]:
        """
        Genera el espectro completo de líneas desde X + k_min hasta X + k_max (tanto Overs como Unders).
        Permite al apostador cuantitativo explorar cualquier línea alternativa con precisión matemática.
        """
        spectrum = []
        for k in range(k_min, k_max + 1):
            stat_over = self.compute_line_offset_stats(category=category, cj=cj, league=league, k=k, is_under=False)
            spectrum.append(stat_over)

        # También incluir Unders para los desplazamientos más relevantes
        for k in range(-2, 4):
            stat_under = self.compute_line_offset_stats(category=category, cj=cj, league=league, k=k, is_under=True)
            spectrum.append(stat_under)

        return spectrum

    def compute_margin_distribution(
        self,
        category: str,
        cj: Optional[float] = None,
        league: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calcula la distribución empírica detallada de márgenes:
        media, desviación estándar, percentiles e histograma de frecuencias.
        """
        subset = self.filter_records(category=category, cj=cj, league=league)
        margins = [r['margen'] for r in subset if r.get('margen') is not None]
        if not margins:
            return {'n': 0, 'mean': 0.0, 'std': 0.0, 'distribution': {}}

        n = len(margins)
        mean_m = sum(margins) / n
        variance = sum((m - mean_m) ** 2 for m in margins) / (n - 1) if n > 1 else 0.0
        std_m = math.sqrt(variance)

        # Frecuencias ordenadas
        freq = defaultdict(int)
        for m in margins:
            freq[m] += 1

        sorted_m = sorted(margins)
        p25 = sorted_m[int(0.25 * n)]
        p50 = sorted_m[int(0.50 * n)]
        p75 = sorted_m[int(0.75 * n)]

        return {
            'n': n,
            'mean': round(mean_m, 2),
            'std': round(std_m, 2),
            'median': p50,
            'p25': p25,
            'p75': p75,
            'min': min(margins),
            'max': max(margins),
            'frequencies': dict(sorted(freq.items()))
        }

    def evaluate_selection(
        self,
        mercado: str,
        seleccion: str,
        cj: Optional[float],
        cr: Optional[float] = None,
        league: Optional[str] = None,
        level_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Evalúa una selección completa clasificándola en su categoría y franja CJ,
        calculando sus métricas base (Línea X), descalados empíricos (X-1, X-2, Suelo 0.5+)
        y métricas específicas de liga si están disponibles.
        """
        from .categories import categorize_item, get_line_level_type

        cat = categorize_item(mercado, seleccion)
        lvl = level_override or get_line_level_type(cat, seleccion)
        interval_code, interval_label = get_cj_interval(cj)

        # 1. Muestra en su categoría y franja CJ
        subset_franja = self.filter_records(category=cat, cj=cj)
        
        # 2. Muestra específica por nivel (Línea X vs Suelo vs Alta)
        if lvl == 'Suelo 0.5+':
            subset_lvl = [r for r in subset_franja if get_line_level_type(cat, r.get('seleccion', '')) == 'Suelo 0.5+']
            # Si la muestra de suelo en la franja es pequeña, usar histórico de suelo en toda la categoría
            if len(subset_lvl) < 5:
                all_cat = self.filter_records(category=cat)
                subset_lvl = [r for r in all_cat if get_line_level_type(cat, r.get('seleccion', '')) == 'Suelo 0.5+']
        elif lvl == 'Alta X':
            subset_lvl = [r for r in subset_franja if get_line_level_type(cat, r.get('seleccion', '')) == 'Alta X']
            if len(subset_lvl) < 5:
                subset_lvl = subset_franja
        elif lvl == 'Tarjeta Jugador':
            subset_lvl = [r for r in subset_franja if 'tarjeta' in r.get('seleccion', '').lower()]
            if len(subset_lvl) < 5:
                all_cat = self.filter_records(category=cat)
                subset_lvl = [r for r in all_cat if 'tarjeta' in r.get('seleccion', '').lower()]
        else:
            subset_lvl = subset_franja

        stats_base = self.compute_basic_stats(subset_lvl)
        w, n, hr, be = stats_base['w'], stats_base['n'], stats_base['hr'], stats_base['be']

        # Si aún no hay suficientes datos en la franja, tomar la categoría global
        if n < 5:
            subset_global = self.filter_records(category=cat)
            stats_global = self.compute_basic_stats(subset_global)
            w, n, hr, be = stats_global['w'], stats_global['n'], stats_global['hr'], stats_global['be']

        ev, val_margin = self.compute_ev(cr, hr)

        # 3. Métricas específicas de liga (si se proporciona y tiene datos)
        league_stats = None
        if league:
            subset_league = self.filter_records(category=cat, cj=cj, league=league)
            if len(subset_league) >= 4:
                ls = self.compute_basic_stats(subset_league)
                l_ev, _ = self.compute_ev(cr, ls['hr'])
                league_stats = {
                    'league': league,
                    'n': ls['n'],
                    'w': ls['w'],
                    'hr': ls['hr'],
                    'be': ls['be'],
                    'ev': l_ev
                }

        # 4. Potencial de descalado (X-1 y X-2)
        descalado_x1 = self.compute_line_offset_stats(category=cat, cj=cj, k=-1)
        descalado_x2 = self.compute_line_offset_stats(category=cat, cj=cj, k=-2)

        return {
            'mercado': mercado,
            'seleccion': seleccion,
            'cat': cat,
            'line_level': lvl,
            'cj': cj,
            'cj_franja': interval_code,
            'cr': cr,
            'n': n,
            'w': w,
            'hr': hr,
            'be': be,
            'ev': ev,
            'val_margin': val_margin,
            'league_stats': league_stats,
            'descalado_x1': {
                'hr': descalado_x1['hr'],
                'be': descalado_x1['be'],
                'n': descalado_x1['n']
            },
            'descalado_x2': {
                'hr': descalado_x2['hr'],
                'be': descalado_x2['be'],
                'n': descalado_x2['n']
            }
        }

    def evaluate_selection_deep(
        self,
        mercado: str,
        seleccion: str,
        cj: Optional[float],
        cr: Optional[float] = None,
        league: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Estudio cuantitativo complejo y exhaustivo de una selección.
        Calcula simultáneamente para todas las líneas (Base X, X-1, X-2/Suelo, Unders):
        - Muestra Global (N_glob, W_glob, HR_glob, BE_glob)
        - Muestra Liga (N_liga, W_liga, HR_liga, BE_liga)
        - Cuota Real y EV (Global y Liga)
        - Genera recomendaciones específicas de qué cuotas mirar para Tiempo 2.
        """
        from .categories import (
            categorize_item,
            get_line_level_type,
            extract_line_value,
            extract_player_name,
            format_realistic_line_name,
            is_player_prop_category,
            normalize_text
        )

        cat = categorize_item(mercado, seleccion)
        lvl = get_line_level_type(cat, seleccion)
        player = extract_player_name(seleccion)
        line_val = extract_line_value(seleccion)
        interval_code, interval_label = get_cj_interval(cj)

        # -------------------------------------------------------------
        # 1. LÍNEA BASE X
        # -------------------------------------------------------------
        # Muestra Global en franja CJ y nivel
        subset_glob = self.filter_records(category=cat, cj=cj)
        if lvl == 'Suelo 0.5+':
            sub_lvl = [r for r in subset_glob if get_line_level_type(cat, r.get('seleccion', '')) == 'Suelo 0.5+']
            if len(sub_lvl) < 5:
                all_cat = self.filter_records(category=cat)
                sub_lvl = [r for r in all_cat if get_line_level_type(cat, r.get('seleccion', '')) == 'Suelo 0.5+']
            subset_glob = sub_lvl
        elif lvl == 'Alta X':
            sub_lvl = [r for r in subset_glob if get_line_level_type(cat, r.get('seleccion', '')) == 'Alta X']
            if len(sub_lvl) >= 5:
                subset_glob = sub_lvl
        elif lvl == 'Tarjeta Jugador':
            sub_lvl = [r for r in subset_glob if 'tarjeta' in r.get('seleccion', '').lower()]
            if len(sub_lvl) < 5:
                all_cat = self.filter_records(category=cat)
                sub_lvl = [r for r in all_cat if 'tarjeta' in r.get('seleccion', '').lower()]
            subset_glob = sub_lvl

        # Fallback si muestra franja es mínima
        if len(subset_glob) < 4:
            subset_glob = self.filter_records(category=cat)

        st_base_glob = self.compute_basic_stats(subset_glob)
        ev_base_glob, _ = self.compute_ev(cr, st_base_glob['hr'])

        # Muestra Liga en franja CJ y nivel (subconjunto estricto de subset_glob)
        if league:
            subset_liga = [r for r in subset_glob if r.get('league') == league]
            st_base_liga = self.compute_basic_stats(subset_liga)
            ev_base_liga, _ = self.compute_ev(cr, st_base_liga['hr']) if st_base_liga['n'] > 0 else (None, None)
        else:
            st_base_liga = {'n': 0, 'w': 0, 'l': 0, 'hr': 0.0, 'be': 999.0}
            ev_base_liga = None

        # Base label concreta
        concrete_base_name = format_realistic_line_name(seleccion, mercado, cat, offset_k=0, is_under=False)

        # -------------------------------------------------------------
        # 2. ESPECTRO COMPLETO DE DESCALADOS (X-1, X-2, X-3)
        # -------------------------------------------------------------
        descalados_spectrum = []
        for dk in [-1, -2, -3]:
            d_name = format_realistic_line_name(seleccion, mercado, cat, offset_k=dk, is_under=False)
            if not d_name:
                continue
            d_st_glob = self.compute_line_offset_stats(category=cat, cj=cj, league=None, k=dk, is_under=False)
            if league:
                d_st_liga = self.compute_line_offset_stats(category=cat, cj=cj, league=league, k=dk, is_under=False)
            else:
                d_st_liga = {'n': 0, 'w': 0, 'hr': 0.0, 'be': 999.0}

            descalados_spectrum.append({
                'k': dk,
                'tag': f"Descalado X{dk}",
                'label': d_name,
                'n_glob': d_st_glob['n'],
                'w_glob': d_st_glob['w'],
                'hr_glob': d_st_glob['hr'],
                'be_glob': d_st_glob['be'],
                'n_liga': d_st_liga['n'],
                'w_liga': d_st_liga['w'],
                'hr_liga': d_st_liga['hr'],
                'be_liga': d_st_liga['be']
            })

        st_x1_item = next((d for d in descalados_spectrum if d['k'] == -1), None)
        st_x2_item = next((d for d in descalados_spectrum if d['k'] == -2), None)

        # -------------------------------------------------------------
        # 3. ESPECTRO COMPLETO DE UNDERS (Under X, X+1, X+2, X+3)
        # Excluido para mercados de jugadores (faltas, tiros, TAP, faltas recibidas, entradas)
        # -------------------------------------------------------------
        unders_spectrum = []
        is_player_prop = is_player_prop_category(cat, mercado, seleccion)
        if not is_player_prop:
            for uk in [0, 1, 2, 3]:
                u_name = format_realistic_line_name(seleccion, mercado, cat, offset_k=uk, is_under=True)
                if not u_name:
                    continue
                u_st_glob = self.compute_line_offset_stats(category=cat, cj=cj, league=None, k=uk, is_under=True)
                if league:
                    u_st_liga = self.compute_line_offset_stats(category=cat, cj=cj, league=league, k=uk, is_under=True)
                else:
                    u_st_liga = {'n': 0, 'w': 0, 'hr': 0.0, 'be': 999.0}

                tag_under = f"Under X" if uk == 0 else f"Under X+{uk}"
                unders_spectrum.append({
                    'k': uk,
                    'tag': tag_under,
                    'label': u_name,
                    'n_glob': u_st_glob['n'],
                    'w_glob': u_st_glob['w'],
                    'hr_glob': u_st_glob['hr'],
                    'be_glob': u_st_glob['be'],
                    'n_liga': u_st_liga['n'],
                    'w_liga': u_st_liga['w'],
                    'hr_liga': u_st_liga['hr'],
                    'be_liga': u_st_liga['be']
                })

        # Seleccionar el Under más representativo para resumen
        best_under = next((u for u in unders_spectrum if u['hr_glob'] >= 65.0), (unders_spectrum[0] if unders_spectrum else None))

        # -------------------------------------------------------------
        # 4. RECOMENDACIONES DE CUOTAS A MIRAR PARA TIEMPO 2
        # -------------------------------------------------------------
        t2_scouting = []

        # Regla A: Si X-1 existe y tiene Hit Rate alto (>= 72%)
        if st_x1_item and st_x1_item['n_glob'] >= 4:
            if league and st_x1_item['n_liga'] >= 5:
                hr_x1_ref = st_x1_item['hr_liga']
                be_x1_ref = st_x1_item['be_liga']
                liga_text = f" y {st_x1_item['hr_liga']}% en {league} (N={st_x1_item['n_liga']})"
            else:
                hr_x1_ref = st_x1_item['hr_glob']
                be_x1_ref = st_x1_item['be_glob']
                liga_text = f" (Liga: {st_x1_item['hr_liga']}% con N={st_x1_item['n_liga']}, muestra reducida)" if (league and st_x1_item['n_liga'] > 0) else ""

            if hr_x1_ref >= 72.0:
                t2_scouting.append({
                    'tipo': 'Descalado X-1',
                    'linea_sugerida': st_x1_item['label'],
                    'hr_glob': st_x1_item['hr_glob'],
                    'n_glob': st_x1_item['n_glob'],
                    'w_glob': st_x1_item['w_glob'],
                    'be_glob': st_x1_item['be_glob'],
                    'hr_liga': st_x1_item['hr_liga'] if (league and st_x1_item['n_liga'] > 0) else None,
                    'n_liga': st_x1_item['n_liga'] if (league and st_x1_item['n_liga'] > 0) else 0,
                    'w_liga': st_x1_item['w_liga'] if (league and st_x1_item['n_liga'] > 0) else 0,
                    'be_liga': st_x1_item['be_liga'] if (league and st_x1_item['n_liga'] > 0) else None,
                    'cuota_minima_exigida': be_x1_ref,
                    'cuota_objetivo': round(be_x1_ref * 1.10, 2),
                    'razon': f"La línea X-1 ({st_x1_item['label']}) tiene HR Global: {st_x1_item['hr_glob']}%{liga_text}. Break-Even @ {be_x1_ref:.2f}. Buscar si la casa paga >= @ {be_x1_ref * 1.10:.2f}."
                })

        # Regla B: Si X-2 existe y tiene Hit Rate muy alto (>= 82%)
        if st_x2_item and st_x2_item['n_glob'] >= 4:
            if league and st_x2_item['n_liga'] >= 5:
                hr_x2_ref = st_x2_item['hr_liga']
                be_x2_ref = st_x2_item['be_liga']
                liga_text = f" y {st_x2_item['hr_liga']}% en {league} (N={st_x2_item['n_liga']})"
            else:
                hr_x2_ref = st_x2_item['hr_glob']
                be_x2_ref = st_x2_item['be_glob']
                liga_text = f" (Liga: {st_x2_item['hr_liga']}% con N={st_x2_item['n_liga']}, muestra reducida)" if (league and st_x2_item['n_liga'] > 0) else ""

            if hr_x2_ref >= 82.0:
                t2_scouting.append({
                    'tipo': 'Suelo X-2',
                    'linea_sugerida': st_x2_item['label'],
                    'hr_glob': st_x2_item['hr_glob'],
                    'n_glob': st_x2_item['n_glob'],
                    'w_glob': st_x2_item['w_glob'],
                    'be_glob': st_x2_item['be_glob'],
                    'hr_liga': st_x2_item['hr_liga'] if (league and st_x2_item['n_liga'] > 0) else None,
                    'n_liga': st_x2_item['n_liga'] if (league and st_x2_item['n_liga'] > 0) else 0,
                    'w_liga': st_x2_item['w_liga'] if (league and st_x2_item['n_liga'] > 0) else 0,
                    'be_liga': st_x2_item['be_liga'] if (league and st_x2_item['n_liga'] > 0) else None,
                    'cuota_minima_exigida': be_x2_ref,
                    'cuota_objetivo': round(be_x2_ref * 1.08, 2),
                    'razon': f"Suelo ({st_x2_item['label']}) con HR Global: {st_x2_item['hr_glob']}%{liga_text}. Break-Even @ {be_x2_ref:.2f}. Ideal para combinada si paga >= @ {be_x2_ref * 1.08:.2f}."
                })

        # Regla C: ESPECTRO COMPLETO DE UNDERS (Under X, Under X+1, Under X+2, Under X+3)
        for u_item in unders_spectrum:
            if league and u_item['n_liga'] >= 5:
                hr_u_ref = u_item['hr_liga']
                be_u_ref = u_item['be_liga']
                liga_text = f" y {u_item['hr_liga']}% en {league} (N={u_item['n_liga']})"
            else:
                hr_u_ref = u_item['hr_glob']
                be_u_ref = u_item['be_glob']
                liga_text = f" (Liga: {u_item['hr_liga']}% con N={u_item['n_liga']}, muestra reducida)" if (league and u_item['n_liga'] > 0) else ""

            uk = u_item['k']
            qualifies = False
            tipo_label = ""
            target_margin = 1.10
            
            if uk == 0 and u_item['n_glob'] >= 4:
                # Under X directo: viable si la base Over tiene poco acierto (<= 55%) y el Under tiene >= 50%
                if st_base_glob['hr'] <= 55.0 and hr_u_ref >= 50.0:
                    qualifies = True
                    tipo_label = "Inversión Under X"
                    target_margin = 1.12
            elif uk == 1 and u_item['n_glob'] >= 4:
                # Under X+1: viable si tiene HR >= 65% (ej: Under 3.5 en partido con Over 2.5)
                if hr_u_ref >= 65.0:
                    qualifies = True
                    tipo_label = "Inversión Under X+1"
                    target_margin = 1.10
            elif uk == 2 and u_item['n_glob'] >= 4:
                # Under X+2: alta probabilidad defensiva si tiene HR >= 78% (ej: Under 4.5 goles o 6.5 tarjetas)
                if hr_u_ref >= 78.0:
                    qualifies = True
                    tipo_label = "Alta Seguridad Under X+2"
                    target_margin = 1.08
            elif uk == 3 and u_item['n_glob'] >= 4:
                # Under X+3: suelo ultra-seguro defensivo si tiene HR >= 86%
                if hr_u_ref >= 86.0:
                    qualifies = True
                    tipo_label = "Suelo Defensivo Under X+3"
                    target_margin = 1.06
            
            if qualifies:
                t2_scouting.append({
                    'tipo': tipo_label,
                    'linea_sugerida': u_item['label'],
                    'hr_glob': u_item['hr_glob'],
                    'n_glob': u_item['n_glob'],
                    'w_glob': u_item['w_glob'],
                    'be_glob': u_item['be_glob'],
                    'hr_liga': u_item['hr_liga'] if (league and u_item['n_liga'] > 0) else None,
                    'n_liga': u_item['n_liga'] if (league and u_item['n_liga'] > 0) else 0,
                    'w_liga': u_item['w_liga'] if (league and u_item['n_liga'] > 0) else 0,
                    'be_liga': u_item['be_liga'] if (league and u_item['n_liga'] > 0) else None,
                    'cuota_minima_exigida': be_u_ref,
                    'cuota_objetivo': round(be_u_ref * target_margin, 2),
                    'razon': f"{tipo_label} ({u_item['label']}) presenta HR Global: {u_item['hr_glob']}%{liga_text}. Break-Even @ {be_u_ref:.2f}. Buscar si paga >= @ {be_u_ref * target_margin:.2f}."
                })

        # Regla D: Si la línea base original ya tiene valor directo
        if ev_base_glob and ev_base_glob > 0.05:
            liga_text = f" y {st_base_liga['hr']}% en {league} (N={st_base_liga['n']})" if (league and st_base_liga['n'] >= 5) else ""
            t2_scouting.append({
                'tipo': 'Línea Base con Valor',
                'linea_sugerida': concrete_base_name,
                'hr_glob': st_base_glob['hr'],
                'n_glob': st_base_glob['n'],
                'w_glob': st_base_glob['w'],
                'be_glob': st_base_glob['be'],
                'hr_liga': st_base_liga['hr'] if (league and st_base_liga['n'] > 0) else None,
                'n_liga': st_base_liga['n'] if (league and st_base_liga['n'] > 0) else 0,
                'w_liga': st_base_liga['w'] if (league and st_base_liga['n'] > 0) else 0,
                'be_liga': st_base_liga['be'] if (league and st_base_liga['n'] > 0) else None,
                'cuota_minima_exigida': st_base_glob['be'],
                'cuota_objetivo': cr,
                'razon': f"La línea original ya presenta Edge positivo (EV: {ev_base_glob:+.2f}). HR Global: {st_base_glob['hr']}%{liga_text}."
            })

        return {
            'mercado': mercado,
            'seleccion': seleccion,
            'cat': cat,
            'line_level': lvl,
            'cj': cj,
            'cj_franja': interval_code,
            'cr': cr,
            'player': player,
            'line_val': line_val,
            # Métricas Línea Original (Base X)
            'base': {
                'label': concrete_base_name,
                'n_glob': st_base_glob['n'],
                'w_glob': st_base_glob['w'],
                'hr_glob': st_base_glob['hr'],
                'be_glob': st_base_glob['be'],
                'n_liga': st_base_liga['n'],
                'w_liga': st_base_liga['w'],
                'hr_liga': st_base_liga['hr'],
                'be_liga': st_base_liga['be'],
                'ev_glob': ev_base_glob,
                'ev_liga': ev_base_liga
            },
            # Espectro Completo de Descalados
            'descalados_spectrum': descalados_spectrum,
            # Espectro Completo de Unders
            'unders_spectrum': unders_spectrum,
            # Accesos directos compatibles
            'descalado_x1': st_x1_item,
            'descalado_x2': st_x2_item,
            'under': best_under,
            't2_recommendations': t2_scouting
        }
