import os
import shutil
import re
from typing import List, Dict, Any, Tuple, Optional
from .parser import parse_single_line, detect_league, normalize_text

def update_line_verdict(line: str, cr: Optional[Any] = None, ver: Optional[Any] = None, mar: Optional[Any] = None) -> str:
    """
    Actualiza de forma no destructiva Cuota Real, Veredicto y Margen en una línea de pronóstico.
    Preserva intactos el Mercado, Selección, Cuota Mínima y cualquier otro dato.
    """
    res = line.strip()
    if not res or 'Mercado:' not in res:
        return line

    # 1. Cuota Real
    if cr is not None:
        cr_clean = str(cr).strip()
        cr_val = f" {cr_clean} " if cr_clean and cr_clean not in ['[ ]', 'NONE', ''] else " "
        if re.search(r'\|\s*Cuota Real:\s*\[.*?\]', res, flags=re.IGNORECASE):
            res = re.sub(r'(\|\s*Cuota Real:\s*\[).*?(\])', rf'\g<1>{cr_val}\g<2>', res, flags=re.IGNORECASE)
        else:
            res += f" | Cuota Real: [{cr_val}]"

    # 2. Veredicto
    if ver is not None:
        ver_clean = str(ver).strip().upper()
        # Normalizar valores habituales
        if ver_clean in ['SÍ', 'SI', 'ACIERTO', 'GANADA', 'WIN', 'W']:
            ver_clean = 'SI'
        elif ver_clean in ['NO', 'FALLO', 'PERDIDA', 'LOSS', 'L']:
            ver_clean = 'NO'
        elif ver_clean in ['ANULADA', 'VOID', 'PUSH', 'CANCELADA']:
            ver_clean = 'ANULADA'
        elif ver_clean in ['[ ]', 'PENDIENTE', 'NONE', '-', '']:
            ver_clean = ''

        ver_val = f" {ver_clean} " if ver_clean else " "
        if re.search(r'\|\s*Veredicto:\s*\[.*?\]', res, flags=re.IGNORECASE):
            res = re.sub(r'(\|\s*Veredicto:\s*\[).*?(\])', rf'\g<1>{ver_val}\g<2>', res, flags=re.IGNORECASE)
        else:
            res += f" | Veredicto: [{ver_val}]"

    # 3. Margen
    if mar is not None:
        mar_clean = str(mar).strip()
        if mar_clean and mar_clean not in ['[ ]', 'PENDIENTE', 'NONE', '-', '']:
            try:
                mar_int = int(float(mar_clean))
                mar_val = f" {mar_int:+d} " if mar_int != 0 else " 0 "
            except ValueError:
                mar_val = f" {mar_clean} "
        else:
            mar_val = " "

        if re.search(r'\|\s*Margen:\s*\[.*?\]', res, flags=re.IGNORECASE):
            res = re.sub(r'(\|\s*Margen:\s*\[).*?(\])', rf'\g<1>{mar_val}\g<2>', res, flags=re.IGNORECASE)
        else:
            res += f" | Margen: [{mar_val}]"

    return res

def analyze_selection_type(seleccion: str, mercado: str = "") -> Dict[str, Any]:
    """
    Analiza una selección y su mercado para determinar si es numérica o binaria,
    extrayendo el objetivo exacto, sujeto, unidad de medida y pregunta natural.
    """
    s_norm = normalize_text(seleccion)
    m_norm = normalize_text(mercado)
    
    # 0. Detección de mercados de estadísticas (tiros, córners, faltas, entradas, tarjetas)
    is_stat_market = any(k in s_norm or k in m_norm for k in [
        'tiro', 'disparo', 'remate', 'corner', 'falta', 'entrada', 'tackle',
        'tarjeta', 'asistencia', 'pase'
    ])

    # 1. Detección estricta de Doble Oportunidad (nunca aplica a mercados estadísticos)
    is_doble_oportunidad = (
        not is_stat_market and (
            'doble oportunidad' in m_norm or 'doble oportunidad' in s_norm or
            bool(re.search(r'\b1x\b', s_norm)) or '(1x)' in s_norm or
            bool(re.search(r'\bx2\b', s_norm)) or '(x2)' in s_norm or
            (bool(re.search(r'\b12\b', s_norm)) and ('doble' in s_norm or 'doble' in m_norm or 'oportunidad' in s_norm or '(12)' in s_norm or 'local o visitante' in s_norm))
        )
    )

    # 2. Mercados binarios / directos explícitos
    is_binary_market = (
        is_doble_oportunidad or
        '1x2' in m_norm or 'resultado final' in m_norm or 'ganador' in m_norm or
        'ambos marcan' in m_norm or 'ambos marcan' in s_norm or
        'ambos equipos marcan' in s_norm or
        'recibira tarjeta' in s_norm or 'recibe tarjeta' in s_norm or 'sera amonestado' in s_norm or
        'anotara' in s_norm or 'marcara' in s_norm or 'marca gol' in s_norm or
        'combinada' in m_norm or 'combo' in m_norm or
        'handicap' in m_norm or 'handicap' in s_norm or
        ('descanso' in m_norm and not ('mas de' in s_norm or 'menos de' in s_norm)) or
        ('descanso' in s_norm and not ('mas de' in s_norm or 'menos de' in s_norm))
    )
    
    # 3. Identificar si es Under
    is_under = ('menos de' in s_norm or 'under' in s_norm)
    
    # 4. Detectar si tiene patrón de Over/Under explícito o X+
    has_ou_pattern = (
        'mas de' in s_norm or 'menos de' in s_norm or
        'over' in s_norm or 'under' in s_norm or
        bool(re.search(r'\d+\s*\+', s_norm))
    )
    
    line_val = None
    m_plus = re.search(r'(\d+)\s*\+', s_norm)
    m_ou_num = re.search(r'(?:mas de|menos de|over|under)\s*(\d+(?:\.\d+)?)', s_norm)
    m_any_num = re.search(r'(\d+(?:\.\d+)?)', s_norm)
    
    if not is_binary_market and has_ou_pattern:
        if m_plus:
            line_val = float(m_plus.group(1))
        elif m_ou_num:
            line_val = float(m_ou_num.group(1))
        elif m_any_num:
            line_val = float(m_any_num.group(1))
            
    is_numerical = (line_val is not None and not is_binary_market and has_ou_pattern)
    
    # 5. Extraer sujeto (jugador o equipo)
    parts = re.split(r'\s*[-—–]\s*', seleccion)
    subject = parts[0].strip() if len(parts) >= 2 else ""
    subj_norm = normalize_text(subject)
    if any(g in subj_norm for g in ['mas de', 'menos de', 'total', 'partido', 'ambos', 'resultado', 'doble oportunidad']):
        subject = ""

    # 6. Unidad de medida y verbo de acción
    unit = "unidades"
    action = "hubo"
    if 'gol' in s_norm or 'gol' in m_norm:
        unit = "goles"
        action = "marcó" if subject else "hubo"
    elif 'corner' in s_norm or 'corner' in m_norm:
        unit = "córners"
        action = "lanzó" if subject else "hubo"
    elif 'puerta' in s_norm or 'tap' in s_norm or 'puerta' in m_norm:
        unit = "tiros a puerta"
        action = "hizo"
    elif 'tiro' in s_norm or 'disparo' in s_norm or 'remate' in s_norm:
        unit = "tiros totales"
        action = "hizo"
    elif 'entrada' in s_norm or 'tackle' in s_norm:
        unit = "entradas / tackles"
        action = "hizo"
    elif 'recibida' in s_norm or 'provoca' in s_norm:
        unit = "faltas recibidas"
        action = "recibió"
    elif 'falta' in s_norm or 'falta' in m_norm:
        unit = "faltas cometidas"
        action = "cometió"
    elif 'tarjeta' in s_norm or 'tarjeta' in m_norm:
        unit = "tarjetas"
        action = "recibió" if subject else "hubo"

    target_or_limit = None
    if is_numerical:
        if not is_under:
            if m_plus:
                target_or_limit = int(line_val)
            elif line_val % 1 != 0:
                target_or_limit = int(line_val + 0.5)
            else:
                target_or_limit = int(line_val) + 1
        else:
            target_or_limit = int(line_val)

    if is_numerical:
        if subject:
            question = f"¿Cuántos {unit} {action} {subject}?"
        else:
            question = f"¿Cuántos {unit} hubo en el partido?"
        cond_text = f"Objetivo: >= {target_or_limit} {unit}" if not is_under else f"Límite: <= {target_or_limit} {unit}"
    else:
        if 'ambos' in s_norm:
            question = "¿Marcaron ambos equipos gol?"
        elif is_doble_oportunidad:
            question = f"¿Se cumplió la Doble Oportunidad ({seleccion})?"
        elif 'recibira tarjeta' in s_norm or 'recibe tarjeta' in s_norm or 'amonestado' in s_norm:
            question = f"¿Recibió tarjeta {subject if subject else seleccion}?"
        elif 'handicap' in m_norm or 'handicap' in s_norm:
            question = f"¿Se cubrió el hándicap ({seleccion})?"
        elif subject:
            question = f"¿Se cumplió: '{seleccion}'?"
        else:
            question = f"¿Se cumplió el pronóstico: '{seleccion}'?"
        cond_text = "Mercado directo (SÍ / NO / ANULADA)"

    is_result_market = (
        not is_stat_market and (
            is_doble_oportunidad or
            '1x2' in m_norm or 'resultado final' in m_norm or 'ganador' in m_norm or
            'handicap' in m_norm or 'handicap' in s_norm or
            'resultado al descanso' in m_norm or
            ('empate' in s_norm and not any(k in s_norm for k in ['mas de', 'menos de'])) or
            ('victoria' in s_norm and not any(k in s_norm for k in ['mas de', 'menos de']))
        )
    )

    return {
        'is_numerical': is_numerical,
        'line_val': line_val,
        'is_under': is_under,
        'target_or_limit': target_or_limit,
        'unit': unit,
        'action': action,
        'subject': subject,
        'question': question,
        'cond_text': cond_text,
        'is_result_market': is_result_market
    }

def parse_match_teams(match_name: str) -> Tuple[str, str]:
    """
    Extrae los nombres del equipo local y visitante a partir del nombre del partido.
    Soporta separadores como 'vs.', 'vs', 'contra', '-'.
    """
    clean_name = re.sub(r'^(?:partido|match|encuentro)\s*:\s*', '', match_name, flags=re.IGNORECASE).strip()
    parts = re.split(r'\s+(?:vs\.?|contra|-)\s+', clean_name, flags=re.IGNORECASE)
    if len(parts) >= 2:
        return parts[0].strip(), parts[1].strip()
    return "Equipo Local", "Equipo Visitante"

def resolve_from_match_score(
    seleccion: str,
    mercado: str,
    home_team: str,
    away_team: str,
    home_goals: int,
    away_goals: int
) -> Optional[Tuple[str, int, str]]:
    """
    Calcula automáticamente veredicto y margen para selecciones de resultado, doble oportunidad,
    hándicap, ambos marcan o goles a partir del marcador del partido (home_goals - away_goals).
    Retorna None si la selección no depende del marcador global (ej. tiros o entradas de jugador).
    """
    s_norm = normalize_text(seleccion)
    m_norm = normalize_text(mercado)
    h_norm = normalize_text(home_team)
    a_norm = normalize_text(away_team)

    diff = home_goals - away_goals  # >0: local, 0: empate, <0: visitante
    tot_goals = home_goals + away_goals
    both_scored = (home_goals > 0 and away_goals > 0)

    # Malla de seguridad: estadísticas de tiros, córners, faltas, entradas o tarjetas no dependen del marcador global
    if any(k in s_norm or k in m_norm for k in ['tiro', 'disparo', 'remate', 'corner', 'falta', 'entrada', 'tackle', 'tarjeta']):
        return None

    # Identificar a qué bando se refiere la selección
    is_home = (h_norm in s_norm) or ('(1)' in s_norm) or (' 1 ' in f" {s_norm} ") or ('1x2' in m_norm and h_norm in s_norm)
    is_away = (a_norm in s_norm) or ('(2)' in s_norm) or (' 2 ' in f" {s_norm} ") or ('1x2' in m_norm and a_norm in s_norm)
    is_draw = ('empate' in s_norm and not any(k in s_norm for k in ['o empate', 'empate o', '1x', 'x2', 'sin empate', 'no valida', 'descanso']))

    # 1. Ambos Equipos Marcan
    if 'ambos marcan' in s_norm or 'ambos marcan' in m_norm or 'ambos equipos marcan' in s_norm:
        is_no = ('no' in s_norm and not 'anotan' in s_norm)
        if 'gana' not in s_norm and 'victoria' not in s_norm and '1x' not in s_norm and 'x2' not in s_norm:
            if both_scored:
                if not is_no:
                    return ("SI", 0, f"Acertada (SÍ): Ambos marcaron ({home_goals}-{away_goals}). Margen: 0")
                else:
                    return ("NO", -1, f"Fallada (NO): Ambos marcaron ({home_goals}-{away_goals}). Margen: -1")
            else:
                if is_no:
                    return ("SI", 0, f"Acertada (SÍ): Al menos un equipo no marcó ({home_goals}-{away_goals}). Margen: 0")
                else:
                    return ("NO", -1, f"Fallada (NO): Al menos un equipo no marcó ({home_goals}-{away_goals}). Margen: -1")

    # 2. Doble Oportunidad
    if '1x' in s_norm or ('o empate' in s_norm and is_home) or ('empate o' in s_norm and is_home):
        if diff >= 0:
            mar = max(0, diff)
            return ("SI", mar, f"Acertada (SÍ): {home_team} {home_goals} - {away_goals} {away_team}. Margen: {mar:+d}")
        else:
            return ("NO", diff, f"Fallada (NO): {home_team} perdió por {-diff} goles. Margen: {diff:+d}")

    if 'x2' in s_norm or ('o empate' in s_norm and is_away) or ('empate o' in s_norm and is_away):
        away_diff = -diff
        if away_diff >= 0:
            mar = max(0, away_diff)
            return ("SI", mar, f"Acertada (SÍ): {home_team} {home_goals} - {away_goals} {away_team}. Margen: {mar:+d}")
        else:
            return ("NO", away_diff, f"Fallada (NO): {away_team} perdió por {-away_diff} goles. Margen: {away_diff:+d}")

    if (bool(re.search(r'\b12\b', s_norm)) and ('doble' in s_norm or 'doble' in m_norm)) or 'local o visitante' in s_norm:
        if diff != 0:
            return ("SI", abs(diff), f"Acertada (SÍ): Hubo ganador ({home_goals}-{away_goals}). Margen: +{abs(diff)}")
        else:
            return ("NO", -1, f"Fallada (NO): Hubo empate ({home_goals}-{away_goals}). Margen: -1")

    # 3. Empate (X)
    if is_draw:
        if diff == 0:
            return ("SI", 0, f"Acertada (SÍ): Hubo empate ({home_goals}-{away_goals}). Margen: 0")
        else:
            return ("NO", -abs(diff), f"Fallada (NO): No hubo empate ({home_goals}-{away_goals}). Margen: {-abs(diff):+d}")

    # 4. Hándicap Asiático / Europeo
    if 'handicap' in s_norm or 'handicap' in m_norm:
        m_hcap = re.search(r'([+-]?\d+(?:\.\d+)?)', s_norm)
        hcap_val = float(m_hcap.group(1)) if m_hcap else 0.0
        target_diff = diff if is_home else -diff
        net_diff = target_diff + hcap_val
        team_name = home_team if is_home else away_team
        if net_diff > 0:
            mar = int(net_diff) if net_diff % 1 == 0 else int(net_diff + 0.5)
            return ("SI", mar, f"Acertada (SÍ): {team_name} cubrió el hándicap ({hcap_val:+g}). Margen: {mar:+d}")
        elif net_diff == 0:
            return ("ANULADA", 0, f"Anulada (PUSH): {team_name} empató con el hándicap ({hcap_val:+g}). Margen: 0")
        else:
            mar = int(net_diff) if net_diff % 1 == 0 else int(net_diff - 0.5)
            return ("NO", mar, f"Fallada (NO): {team_name} no cubrió el hándicap ({hcap_val:+g}). Margen: {mar:+d}")

    # 5. Combinada / Match Combo (ej. BTTS y Gana)
    if 'ambos' in s_norm and ('gana' in s_norm or 'victoria' in s_norm or '1x' in s_norm):
        home_win = (diff > 0)
        away_win = (diff < 0)
        win_ok = (home_win if is_home else (away_win if is_away else (diff >= 0 if '1x' in s_norm else False)))
        if both_scored and win_ok:
            return ("SI", 0, f"Acertada (SÍ): Se cumplió resultado y ambos marcaron ({home_goals}-{away_goals}). Margen: 0")
        else:
            return ("NO", -1, f"Fallada (NO): No se cumplieron ambas condiciones ({home_goals}-{away_goals}). Margen: -1")

    # 6. Victoria 1X2
    if 'resultado final' in m_norm or '1x2' in m_norm or 'victoria' in s_norm or 'gana' in s_norm:
        if is_away:
            away_diff = -diff
            if away_diff > 0:
                return ("SI", away_diff, f"Acertada (SÍ): {away_team} ganó por {away_diff} goles. Margen: +{away_diff}")
            elif away_diff == 0:
                return ("NO", -1, f"Fallada (NO): Hubo empate ({home_goals}-{away_goals}). Margen: -1")
            else:
                return ("NO", away_diff, f"Fallada (NO): {away_team} perdió por {-away_diff} goles. Margen: {away_diff:+d}")
        else:
            if diff > 0:
                return ("SI", diff, f"Acertada (SÍ): {home_team} ganó por {diff} goles. Margen: +{diff}")
            elif diff == 0:
                return ("NO", -1, f"Fallada (NO): Hubo empate ({home_goals}-{away_goals}). Margen: -1")
            else:
                return ("NO", diff, f"Fallada (NO): {home_team} perdió por {-diff} goles. Margen: {diff:+d}")

    # 7. Total de Goles del partido
    if 'total de goles' in m_norm or ('goles' in m_norm and ('mas de' in s_norm or 'menos de' in s_norm) and not is_home and not is_away):
        m_num = re.search(r'(?:mas de|menos de|over|under)\s*(\d+(?:\.\d+)?)', s_norm)
        if m_num:
            line_v = float(m_num.group(1))
            is_under = ('menos de' in s_norm or 'under' in s_norm)
            if not is_under:
                target = int(line_v + 0.5) if line_v % 1 != 0 else int(line_v) + 1
                if tot_goals >= target:
                    mar = int(tot_goals - target)
                    return ("SI", mar, f"Acertada (SÍ): Hubo {tot_goals} goles (Objetivo: >= {target}). Margen: {mar:+d}")
                else:
                    mar = int(tot_goals - target)
                    return ("NO", mar, f"Fallada (NO): Hubo {tot_goals} goles (Objetivo: >= {target}). Margen: {mar:+d}")
            else:
                limit = int(line_v)
                if tot_goals <= limit:
                    mar = int(tot_goals - limit)
                    return ("SI", mar, f"Acertada (SÍ): Hubo {tot_goals} goles (Límite: <= {limit}). Margen: {mar:+d}")
                else:
                    mar = int(tot_goals - limit)
                    return ("NO", mar, f"Fallada (NO): Hubo {tot_goals} goles (Límite: <= {limit}). Margen: {mar:+d}")

    return None

def auto_resolve_selection(
    seleccion: str,
    mercado: str = "",
    stat_value: Optional[float] = None
) -> Tuple[Optional[str], Optional[int], str]:
    """
    Calcula automáticamente el veredicto ('SI' o 'NO') y el Margen numérico exacto (+/- N)
    a partir del dato estadístico real ingresado.
    Retorna: (veredicto, margen, explicacion)
    """
    if stat_value is None:
        return (None, None, "Pendiente de dato estadístico real.")

    info = analyze_selection_type(seleccion, mercado)
    if not info['is_numerical']:
        return (None, None, "Mercado directo (selecciona SÍ / NO / ANULADA).")

    s = float(stat_value)
    target = info['target_or_limit']
    is_under = info['is_under']

    if not is_under:
        # OVER
        if s >= target:
            ver = "SI"
            margin = int(s - target)
            exp = f"Acertada (SÍ): Registró {s:g} (Objetivo: >= {target}). Margen: {margin:+d}"
        else:
            ver = "NO"
            margin = int(s - target)
            exp = f"Fallada (NO): Registró {s:g} (Objetivo: >= {target}). Margen: {margin:+d}"
    else:
        # UNDER
        if s <= target:
            ver = "SI"
            margin = int(s - target)
            exp = f"Acertada (SÍ): Registró {s:g} (Límite: <= {target}). Margen: {margin:+d}"
        else:
            ver = "NO"
            margin = int(s - target)
            exp = f"Fallada (NO): Registró {s:g} (Límite: <= {target}). Margen: {margin:+d}"

    return (ver, margin, exp)

class HistorialUpdater:
    """
    Gestor transaccional seguro para consultar y actualizar veredictos y márgenes
    en el archivo 'historial_prompt.txt' sin pérdida ni corrupción de datos.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path

    def _read_parts(self) -> Tuple[List[str], List[Dict[str, Any]]]:
        """
        Lee el archivo preservando separadores y mapea cada match a su índice de bloque.
        """
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Archivo no encontrado: {self.file_path}")

        with open(self.file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        parts = re.split(r'(\n{2,})', content)
        
        matches = []
        match_idx = 0
        for part_pos, part_text in enumerate(parts):
            if part_pos % 2 == 1:
                # Es un delimitador de saltos de línea
                continue
            lines = [l.strip() for l in part_text.split('\n') if l.strip()]
            market_lines = [l for l in lines if 'Mercado:' in l]
            if not market_lines:
                continue
            
            match_idx += 1
            non_market = [l for l in lines if 'Mercado:' not in l and '|' not in l]
            if non_market:
                raw_mname = non_market[0]
                m_clean = re.sub(r'^(?:partido|match|encuentro)\s*:\s*', '', raw_mname, flags=re.IGNORECASE).strip()
                match_name = m_clean.title() if m_clean.islower() else m_clean
            else:
                match_name = f"Partido {match_idx}"

            sample_sels = [l.split('|')[1].strip() for l in market_lines if '|' in l]
            league = detect_league(match_name, sample_sels)

            records = []
            m_line_idx = 0
            settled_cnt = 0
            pending_cnt = 0
            
            for l in lines:
                if 'Mercado:' not in l:
                    continue
                rec = parse_single_line(l)
                if rec:
                    rec['line_index'] = m_line_idx
                    rec['raw_line'] = l
                    ver = rec.get('veredicto')
                    if ver in ['SI', 'NO']:
                        settled_cnt += 1
                    elif ver in ['ANULADA', 'VOID', 'PUSH']:
                        pass
                    else:
                        pending_cnt += 1
                    records.append(rec)
                    m_line_idx += 1

            matches.append({
                'match_id': match_idx,
                'part_pos': part_pos,
                'match_name': match_name,
                'league': league,
                'total_lines': len(records),
                'settled_count': settled_cnt,
                'pending_count': pending_cnt,
                'raw_chunk': part_text,
                'records': records
            })

        return parts, matches

    def get_matches_info(self) -> List[Dict[str, Any]]:
        """Retorna el listado completo de partidos con su estado de pendientes / concluidos."""
        _, matches = self._read_parts()
        return matches

    def get_pending_matches(self) -> List[Dict[str, Any]]:
        """Retorna únicamente los partidos que tengan al menos 1 pronóstico pendiente."""
        _, matches = self._read_parts()
        return [m for m in matches if m['pending_count'] > 0]

    def update_match_records(
        self,
        match_id: int,
        updates_dict: Dict[int, Dict[str, Any]],
        backup: bool = True
    ) -> bool:
        """
        Actualiza los registros de un partido dado su match_id.
        updates_dict es un diccionario: {line_index: {'cr': ..., 'veredicto': ..., 'margen': ...}}
        """
        parts, matches = self._read_parts()
        target_match = next((m for m in matches if m['match_id'] == match_id), None)
        if not target_match:
            raise ValueError(f"No se encontró el partido con ID #{match_id}")

        part_pos = target_match['part_pos']
        old_chunk = parts[part_pos]
        old_lines = old_chunk.split('\n')

        new_lines = []
        market_line_idx = 0
        for l in old_lines:
            if 'Mercado:' in l:
                if market_line_idx in updates_dict:
                    upd = updates_dict[market_line_idx]
                    new_l = update_line_verdict(
                        line=l,
                        cr=upd.get('cr'),
                        ver=upd.get('veredicto'),
                        mar=upd.get('margen')
                    )
                    new_lines.append(new_l)
                else:
                    new_lines.append(l)
                market_line_idx += 1
            else:
                new_lines.append(l)

        parts[part_pos] = "\n".join(new_lines)
        new_content = "".join(parts)

        # Crear backup antes de escribir
        if backup:
            bak_path = self.file_path + '.bak'
            shutil.copyfile(self.file_path, bak_path)

        with open(self.file_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(new_content)

        return True

    def update_match_raw_chunk(
        self,
        match_id: int,
        new_chunk_text: str,
        backup: bool = True
    ) -> bool:
        """Reemplaza directamente el bloque de texto completo de un partido."""
        parts, matches = self._read_parts()
        target_match = next((m for m in matches if m['match_id'] == match_id), None)
        if not target_match:
            raise ValueError(f"No se encontró el partido con ID #{match_id}")

        part_pos = target_match['part_pos']
        parts[part_pos] = new_chunk_text.strip()
        new_content = "".join(parts)

        if backup:
            bak_path = self.file_path + '.bak'
            shutil.copyfile(self.file_path, bak_path)

        with open(self.file_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(new_content)

        return True

    def append_new_match(
        self,
        match_name: str,
        lines_text: str,
        backup: bool = True
    ) -> bool:
        """
        Añade un nuevo partido con sus líneas al final de historial_prompt.txt de forma limpia.
        """
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Archivo no encontrado: {self.file_path}")

        raw_lines = [l.strip() for l in lines_text.split('\n') if l.strip() and 'Mercado:' in l]
        if not raw_lines:
            return False

        chunk_lines = [match_name.strip()]
        for l in raw_lines:
            rec = parse_single_line(l)
            if not rec:
                continue
            cr_val = f" {rec['cr']} " if rec.get('cr') else " "
            ver_val = f" {rec['veredicto']} " if rec.get('veredicto') else " "
            mar_val = f" {rec['margen']} " if rec.get('margen') is not None else " "
            cj_val = f"{rec['cj']:.2f}" if rec.get('cj') else "1.50"
            formatted_l = f"Mercado: {rec['mercado']} | Selección: {rec['seleccion']} | Cuota Mínima: {cj_val} | Cuota Real: [{cr_val}] | Veredicto: [{ver_val}] | Margen: [{mar_val}]"
            chunk_lines.append(formatted_l)

        chunk_text = "\n".join(chunk_lines)

        if backup:
            bak_path = self.file_path + '.bak'
            shutil.copyfile(self.file_path, bak_path)

        with open(self.file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read().rstrip()

        new_content = content + "\n\n\n\n" + chunk_text + "\n"

        with open(self.file_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(new_content)

        return True
