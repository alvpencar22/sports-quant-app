import json
import os
from typing import List, Dict, Any, Tuple, Optional

class MatchAuditor:
    """
    Auditor Post-Partido y Reconciliador del Historial.
    Liquida las 3 Balas jugadas, audita el PnL exacto, restaura Cuotas Justas
    y sincroniza el dataset histórico y la matriz 2D.
    """

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.hist_path = os.path.join(data_dir, 'historial_prompt.txt')
        self.dataset_path = os.path.join(data_dir, 'categorized_dataset.json')
        self.matrix_path = os.path.join(data_dir, 'matrix_2d.json')

    def audit_bullets(
        self,
        bullets: List[Dict[str, Any]],
        settlements: Dict[str, str], # leg_id -> 'SI' / 'NO' / 'ANULADA'
        unit_stake: float = 1.0
    ) -> Dict[str, Any]:
        """
        Audita el resultado de las balas jugadas.
        Calcula unidades apostadas, unidades devueltas, beneficio neto y ROI / Yield %.
        """
        total_staked = len(bullets) * unit_stake
        total_returned = 0.0
        bullet_results = []

        for idx, b in enumerate(bullets, start=1):
            legs = b.get('legs', [])
            all_won = True
            any_lost = False
            has_void = False

            leg_details = []
            for leg in legs:
                leg_id = leg.get('leg_id') or leg.get('desc')
                res = settlements.get(leg_id, settlements.get(leg.get('desc'), 'PENDIENTE'))
                leg_details.append({
                    'desc': leg.get('desc'),
                    'resultado': res
                })
                if res == 'NO':
                    any_lost = True
                    all_won = False
                elif res in ['ANULADA', 'VOID', 'PUSH']:
                    has_void = True
                elif res != 'SI':
                    all_won = False

            if any_lost:
                status = 'PERDIDA'
                ret = 0.0
                profit = -unit_stake
            elif all_won:
                status = 'GANADA'
                ret = b['cr'] * unit_stake
                profit = ret - unit_stake
            elif has_void:
                status = 'ANULADA'
                ret = unit_stake
                profit = 0.0
            else:
                status = 'PENDIENTE'
                ret = 0.0
                profit = 0.0

            total_returned += ret
            bullet_results.append({
                'bala_id': f"Bala #{idx}",
                'cr': b['cr'],
                'hr_teorico': b.get('hr'),
                'estado': status,
                'retorno': round(ret, 2),
                'beneficio': round(profit, 2),
                'legs': leg_details
            })

        net_profit = round(total_returned - total_staked, 2)
        yield_pct = round((net_profit / total_staked) * 100.0, 1) if total_staked > 0 else 0.0

        return {
            'total_balas': len(bullets),
            'unidades_apostadas': total_staked,
            'unidades_retornadas': round(total_returned, 2),
            'beneficio_neto': net_profit,
            'yield_pct': f"{yield_pct:+}%",
            'balas': bullet_results
        }

    def sync_settled_match(
        self,
        match_id: int,
        match_name: str,
        league: str,
        settled_lines: List[Dict[str, Any]],
        append_to_historial_file: bool = True
    ) -> int:
        """
        Incorpora un partido recién concluido al archivo historial_prompt.txt
        y actualiza el dataset categorizado.
        """
        # 1. Cargar dataset existente
        existing_records = []
        if os.path.exists(self.dataset_path):
            with open(self.dataset_path, 'r', encoding='utf-8') as f:
                existing_records = json.load(f)

        # Eliminar registros previos de este mismo match_id si existieran para evitar duplicados
        filtered_records = [r for r in existing_records if r.get('match_id') != match_id]

        new_records = []
        text_lines = []

        for item in settled_lines:
            rec = {
                'match_id': match_id,
                'match_name': match_name,
                'league': league,
                'mercado': item.get('mercado', ''),
                'seleccion': item.get('seleccion', ''),
                'cj': item.get('cj'),
                'cr': item.get('cr'),
                'veredicto': item.get('veredicto', 'NO'),
                'margen': item.get('margen'),
                'cat': item.get('cat', ''),
                'line_level': item.get('line_level', 'Línea X'),
                'raw': item.get('raw', '')
            }
            new_records.append(rec)

            # Generar línea formateada para el historial
            cj_str = f"{rec['cj']:.2f}" if rec['cj'] is not None else ""
            cr_str = f"[{rec['cr']:.2f} ]" if rec['cr'] is not None else "[]"
            ver_str = f"[{rec['veredicto']} ]" if rec['veredicto'] else "[]"
            mar_str = f"[{rec['margen']:+} ]" if rec['margen'] is not None else "[]"
            
            line_str = f"Mercado: {rec['mercado']} | Selección: {rec['seleccion']} | Cuota Justa: {cj_str} | Cuota Real: {cr_str} | Veredicto: {ver_str} | Margen: {mar_str}"
            text_lines.append(line_str)

        all_records = filtered_records + new_records

        # Guardar dataset actualizado
        with open(self.dataset_path, 'w', encoding='utf-8') as f:
            json.dump(all_records, f, indent=2, ensure_ascii=False)

        # Si se solicita, añadir al archivo historial_prompt.txt
        if append_to_historial_file and os.path.exists(self.hist_path):
            block_text = "\n" + "\n".join(text_lines) + "\n"
            with open(self.hist_path, 'a', encoding='utf-8') as f:
                f.write(block_text)

        return len(all_records)
