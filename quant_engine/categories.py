import re
import unicodedata

def normalize_text(text: str) -> str:
    """Elimina acentos y normaliza espacios y minúsculas."""
    if not text:
        return ""
    # Remove accents
    nfkd = unicodedata.normalize('NFKD', text)
    clean = "".join([c for c in nfkd if not unicodedata.combining(c)])
    clean = re.sub(r'\s+', ' ', clean).strip().lower()
    return clean

def extract_line_value(seleccion: str) -> float | None:
    """Extrae el valor numérico de la línea (ej: 0.5, 1.5, 2.5, 9.5, etc.),
    evitando confundirlo con años o identificadores numéricos de clubes (ej. Como 1907, Schalke 04, Hannover 96)."""
    s = normalize_text(seleccion)

    # 1. Prioridad: Buscar explícitamente tras 'más de', 'menos de', 'over', 'under' con delimitador de palabra
    m_ou = re.search(r'\b(?:mas\s+de|menos\s+de|over|under)\b\s*(\d+(?:\.\d+)?)', s)
    if m_ou:
        try:
            return float(m_ou.group(1))
        except ValueError:
            pass

    # 2. Prioridad: Buscar notación de umbral X+ (ej. 1+, 2+, 3+)
    m_plus = re.search(r'\b(\d+(?:\.\d+)?)\s*\+', s)
    if m_plus:
        try:
            return float(m_plus.group(1))
        except ValueError:
            pass

    # 3. Prioridad: Si hay un guión separador, buscar en la parte de la apuesta (después del guión)
    if '—' in s or '-' in s or '–' in s:
        parts = re.split(r'\s*[-—–]\s*', s)
        if len(parts) >= 2:
            bet_part = parts[-1]
            m_part = re.search(r'\b(?:mas\s+de|menos\s+de|over|under)\b\s*(\d+(?:\.\d+)?)', bet_part)
            if not m_part:
                m_part = re.search(r'\b(\d+(?:\.\d+)?)\b', bet_part)
            if m_part:
                try:
                    return float(m_part.group(1))
                except ValueError:
                    pass

    # 4. Fallback: Buscar números típicos de líneas deportivas (descartando años como 1907, 1860, 2024)
    for m in re.finditer(r'\b(\d+(?:\.\d+)?)\b', s):
        try:
            val = float(m.group(1))
            if val <= 99.5:
                return val
        except ValueError:
            pass

    return None

def extract_player_name(seleccion: str) -> str | None:
    """Extrae el nombre del jugador si la selección corresponde a un player prop."""
    parts = re.split(r'\s*[-—–]\s*', seleccion)
    if len(parts) >= 2:
        candidate = parts[0].strip()
        lower_c = normalize_text(candidate)
        generic_words = ['partido', 'totales', 'ambos', 'mas', 'menos', 'resultado', 'doble', 'tarjetas', 'corners', 'goles', 'tiros']
        if not any(g in lower_c for g in generic_words):
            return candidate
    return None

def extract_team_name(seleccion: str) -> str | None:
    """Extrae el nombre del equipo de una selección de resultado o equipo."""
    parts = re.split(r'\s*[-—–]\s*', seleccion)
    if len(parts) >= 2:
        cand = parts[0].strip()
        if not any(w in normalize_text(cand) for w in ['mas', 'menos', 'total', 'partido', 'ambos']):
            return cand
    if 'victoria de' in normalize_text(seleccion):
        m = re.search(r'victoria de\s+([A-Za-z0-9\s]+)', seleccion, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None

def is_player_prop_category(cat: str = "", mercado: str = "", seleccion: str = "") -> bool:
    """Identifica si una selección pertenece a un mercado de jugador (player prop)."""
    c = normalize_text(cat)
    m = normalize_text(mercado)
    s = normalize_text(seleccion)
    if 'player' in c or 'jugador' in m:
        return True
    if any(k in m for k in ['de jugador', 'tiros de jugador', 'tiros a puerta de jugador', 'faltas cometidas de jugador', 'faltas recibidas de jugador', 'entradas / tackles de jugador', 'entradas de jugador', 'tarjetas de jugador']):
        return True
    if any(k in c for k in ['tiros totales', 'tiros a puerta', 'entradas', 'faltas cometidas', 'faltas recibidas', 'tarjetas']) and ('player' in c or 'jugador' in m):
        return True
    return False

def format_realistic_line_name(
    seleccion: str,
    mercado: str = "",
    cat: str = "",
    offset_k: int = 0,
    is_under: bool = False
) -> str:
    """
    Genera el nombre realista, intuitivo y concreto de la línea de apuesta
    para descalados (X-1, X-2, Suelos) e inversiones (Under X, X+1, X+2, X+3).
    Para mercados de jugadores (tiros, TAP, faltas, entradas), no se ofrecen Unders.
    """
    sel_norm = normalize_text(seleccion)
    cat_norm = normalize_text(cat)
    team = extract_team_name(seleccion)
    player = extract_player_name(seleccion)
    line_val = extract_line_value(seleccion)

    # REGLA FUNDAMENTAL DE MERCADO:
    # En mercados de jugadores (faltas cometidas, tiros, tiros a puerta, faltas recibidas, entradas),
    # las casas de apuestas NO ofrecen líneas Under. Solo aplican descalados Over (X-1, X-2).
    if is_under and is_player_prop_category(cat, mercado, seleccion):
        return None

    # 1. Mercado de Resultado / 1X2 Directo
    if '1x2' in cat_norm or 'resultado' in cat_norm or 'victoria' in sel_norm or 'gana' in sel_norm:
        t_name = team or (seleccion.split('—')[0].strip() if '—' in seleccion else "Equipo")
        if not is_under:
            if offset_k == 0:
                return f"{t_name} — Victoria (1X2)"
            elif offset_k == -1:
                return f"{t_name} o Empate (Doble Oportunidad 1X / X2)"
            elif offset_k == -2:
                return f"{t_name} — Hándicap Asiático +1.5"
            elif offset_k == -3:
                return f"{t_name} — Hándicap Asiático +2.5"
            elif offset_k == 1:
                return f"{t_name} — Victoria por 2+ Goles (Hándicap -1.5)"
            elif offset_k >= 2:
                return f"{t_name} — Hándicap -{offset_k}.5"
        else:
            if offset_k == 0:
                return f"Empate o Derrota de {t_name} (Inversión X2 contra Victoria)"
            elif offset_k == 1:
                return f"{t_name} NO gana por 2+ goles (Rival Hándicap +1.5)"
            elif offset_k == 2:
                return f"{t_name} NO gana por 3+ goles (Rival Hándicap +2.5)"
            elif offset_k == 3:
                return f"{t_name} NO gana por 4+ goles (Rival Hándicap +3.5)"

    # 2. Ambos Equipos Marcan (BTTS)
    if 'btts' in cat_norm or 'ambos marcan' in cat_norm or 'ambos equipos marcan' in sel_norm:
        if not is_under:
            if offset_k == 0:
                return "Ambos Equipos Marcan — Sí"
            # Un mercado binario sí/no no tiene descalados X-1 o X-2
            return None
        else:
            if offset_k == 0:
                return "Ambos Equipos Marcan — NO"
            elif offset_k == 1:
                return "Menos de 2.5 Goles Totales (Under 2.5 / BTTS NO)"
            elif offset_k == 2:
                return "Menos de 3.5 Goles Totales"
            elif offset_k == 3:
                return "Menos de 4.5 Goles Totales"

    # 3. Tarjeta de Jugador
    if 'player' in cat_norm and 'tarjeta' in cat_norm:
        p_name = player or seleccion.split('—')[0].strip()
        if not is_under:
            if offset_k == 0:
                return f"{p_name} — Recibirá Tarjeta"
            # Tarjeta de jugador es evento discreto (0 ó 1); no tiene descalado numérico
            return None
        else:
            if offset_k == 0:
                return f"{p_name} — NO Recibirá Tarjeta"
            return None

    # 4. Líneas Numéricas (Goles, Córners, Tarjetas, Tiros, Faltas, Entradas)
    if line_val is not None:
        new_val = line_val + offset_k
        if new_val < 0.5:
            return None
        val_str = f"{new_val:g}"

        # Separar equipo/jugador del cuerpo de la apuesta para nunca alterar nombres propios (ej. Como 1907, Schalke 04)
        if '—' in seleccion or '–' in seleccion or (' - ' in seleccion):
            parts = re.split(r'(\s*[-—–]\s*)', seleccion, maxsplit=1)
            prefix = parts[0] + parts[1]
            bet_raw = parts[2]
        else:
            prefix = ""
            bet_raw = seleccion

        # Limpiar cualquier sufijo explicativo entre paréntesis previo (ej. "(2+)", "(1+ / Suelo)")
        bet_clean = re.sub(r'\s*\([^)]*\)$', '', bet_raw).strip()

        pattern_over = re.compile(r'(\b(?:m[aá]s\s+de|over)\b\s*)\d+(?:\.\d+)?', re.IGNORECASE)
        pattern_under = re.compile(r'(\b(?:menos\s+de|under)\b\s*)\d+(?:\.\d+)?', re.IGNORECASE)

        if not is_under:
            if pattern_over.search(bet_clean):
                bet_out = pattern_over.sub(rf'\g<1>{val_str}', bet_clean)
            elif pattern_under.search(bet_clean):
                bet_out = pattern_under.sub(rf'\g<1>{val_str}', bet_clean)
            else:
                bet_out = re.sub(r'\b\d+(?:\.\d+)?\b', val_str, bet_clean, count=1)

            # Añadir etiqueta aclaratoria de suelo o tiros si es player prop
            if 'player' in cat_norm or is_player_prop_category(cat, mercado, seleccion):
                if new_val == 0.5 or '0.5' in val_str:
                    bet_out += " (1+ / Suelo)"
                elif new_val == 1.5 and any(k in sel_norm for k in ['tiro', 'puerta', 'tap']):
                    bet_out += " (2 tiros)"
                elif new_val == 1.5 and any(k in sel_norm for k in ['entrada', 'tackle']):
                    bet_out += " (2 entradas)"
                elif new_val == 1.5 and any(k in sel_norm for k in ['falta']):
                    bet_out += " (2 faltas)"
            elif new_val == 0.5:
                bet_out += " (1+ / Suelo)"

            return f"{prefix}{bet_out}"
        else:
            # Under
            if pattern_over.search(bet_clean):
                bet_out = pattern_over.sub(f'Menos de {val_str}', bet_clean)
            elif pattern_under.search(bet_clean):
                bet_out = pattern_under.sub(rf'Menos de {val_str}', bet_clean)
            else:
                bet_out = f"Menos de {val_str} {re.sub(r'\b\d+(?:\.\d+)?\b', '', bet_clean).strip()}"

            return f"{prefix}{bet_out}"

    # 5. Fallback genérico
    if is_under:
        return f"Under X{'+' if offset_k > 0 else ''}{offset_k if offset_k != 0 else ''}"
    return f"Línea X{'+' if offset_k > 0 else ''}{offset_k if offset_k != 0 else ''}"

def categorize_item(mercado: str, seleccion: str, raw: str = "") -> str:
    """Clasifica de forma objetiva e imparcial cada selección en su categoría canónica."""
    m = normalize_text(mercado)
    s = normalize_text(seleccion)
    r = normalize_text(raw)

    # 1. Player Props
    if 'entrada' in m or 'tackle' in m or 'entrada' in s or 'tackle' in s:
        return 'Player - Entradas'

    if 'falta recibida' in m or 'faltas recibidas' in m or 'falta recibida' in s or 'faltas recibidas' in s:
        return 'Player - Faltas Recibidas'

    if 'falta' in m or 'faltas cometidas' in m or 'faltas de jugador' in m or 'falta' in s:
        if 'recibida' in s or 'recibe' in s or 'provoca' in s:
            return 'Player - Faltas Recibidas'
        return 'Player - Faltas Cometidas'

    if 'tiros a puerta de jugador' in m or 'tiro a puerta de jugador' in m or 'tap de jugador' in m:
        return 'Player - Tiros a Puerta (TAP)'
    if ('tiro a puerta' in s or 'tiros a puerta' in s or 'tap' in s) and ('jugador' in m or any(w in s for w in ['0.5', '1.5', '2.5', '1+', '2+'])):
        if not any(k in s for k in ['partido', 'totales del partido', 'totales', 'total']):
            if extract_player_name(seleccion) is not None or 'jugador' in m:
                return 'Player - Tiros a Puerta (TAP)'

    if 'tiros de jugador' in m or 'tiro de jugador' in m or 'remates de jugador' in m:
        if 'puerta' in s or 'tap' in s:
            return 'Player - Tiros a Puerta (TAP)'
        return 'Player - Tiros Totales'

    if 'tarjeta' in m or 'tarjetas' in m:
        if 'jugador' in m:
            return 'Player - Tarjetas'
        if any(w in s for w in ['recibira tarjeta', 'sera amonestado', 'amonestado', 'recibe tarjeta', 'tarjeta amarilla']):
            if not any(k in s for k in ['partido', 'totales', 'equipo']):
                return 'Player - Tarjetas'
        if any(k in s for k in ['totales', 'partido', 'mas de', 'menos de']) and 'equipo' not in m and 'equipo' not in s:
            return 'Partido - Tarjetas Totales'
        if 'equipo' in m or 'equipo' in s:
            return 'Equipo - Tarjetas'
        return 'Partido - Tarjetas Totales'

    if 'goleador' in m or 'anotara' in s or 'marca gol' in s or 'anota' in s:
        return 'Player - Goleador'

    # 2. Córners
    if 'corner' in m or 'corners' in m:
        if 'menos' in s or 'under' in s:
            return 'Partido - Córners Unders'
        if 'equipo' in m or ('equipo' in s and 'totales' not in s):
            return 'Equipo - Córners de un Equipo'
        if any(k in s for k in ['totales', 'total', 'partido']) or 'mas de' in s:
            if any(team_flag in s for team_flag in ['chelsea', 'manchester', 'atletico', 'vallecano', 'tottenham', 'getafe', 'mainz', 'villarreal', 'espanyol']):
                if 'totales' not in s:
                    return 'Equipo - Córners de un Equipo'
            return 'Partido - Córners Totales (Overs)'
        return 'Córners - Otros'

    # 3. Tiros a Puerta
    if 'tiros a puerta' in m or 'remates a puerta' in m or 'disparos a puerta' in m:
        if 'menos' in s or 'under' in s:
            return 'Tiros a Puerta - Unders'
        if 'equipo' in m:
            return 'Equipo - Tiros a Puerta'
        if any(k in s for k in ['totales', 'total', 'partido']):
            return 'Partido - Tiros a Puerta Totales'
        parts = re.split(r'\s*[-—–]\s*', seleccion)
        if len(parts) >= 2 and 'totales' not in s:
            return 'Equipo - Tiros a Puerta'
        return 'Partido - Tiros a Puerta Totales'

    # 4. Tiros Totales
    if 'tiros' in m or 'remates' in m or 'disparos' in m:
        if 'menos' in s or 'under' in s:
            return 'Tiros - Unders'
        if 'equipo' in m:
            return 'Equipo - Tiros Totales'
        if any(k in s for k in ['totales', 'total', 'partido']):
            return 'Partido - Tiros Totales (Overs)'
        parts = re.split(r'\s*[-—–]\s*', seleccion)
        if len(parts) >= 2 and 'totales' not in s:
            return 'Equipo - Tiros Totales'
        return 'Partido - Tiros Totales (Overs)'

    # 5. Goles
    if 'gol' in m or 'goles' in m or 'marcan' in m or 'btts' in m:
        if 'ambos' in s or 'btts' in s or 'marcan' in s:
            return 'Goles - Ambos Marcan (BTTS)'
        if 'menos' in s or 'under' in s:
            return 'Goles - Menos de (Unders)'
        if 'mas' in s or 'over' in s:
            return 'Goles - Más de (Overs)'
        return 'Goles - Otros'

    # 6. Resultado
    if 'resultado' in m or 'doble oportunidad' in m or 'handicap' in m or '1x2' in m:
        if 'doble oportunidad' in m or 'doble oportunidad' in s or '1x' in s or 'x2' in s or 'o empate' in s:
            return 'Resultado - Doble Oportunidad'
        if 'empate no valido' in s or 'dnb' in s or 'handicap' in s or 'asiatico' in s:
            return 'Resultado - Hándicap / DNB'
        if 'empate' in s and '(' in s and not ('1x' in s or 'x2' in s):
            return 'Resultado - Empate / Marcador'
        return 'Resultado - 1X2 Directo'

    # 7. Combinadas
    if 'combinada' in m or 'combo' in m or '&' in s or ' y ' in s:
        if 'marcan' in s and ('gana' in s or 'victoria' in s or '1x' in s):
            return 'Goles - Ambos Marcan (BTTS)'
        return 'Otros Mercados'

    return 'Otros Mercados'

def get_line_level_type(cat: str, seleccion: str) -> str:
    """Determina si la línea es Suelo, Alta, Descalado o Directa."""
    s = normalize_text(seleccion)
    if 'player' in cat.lower():
        if 'tarjeta' in s:
            return 'Tarjeta Jugador'
        line_val = extract_line_value(seleccion)
        if line_val is not None:
            if line_val <= 0.5:
                return 'Suelo 0.5+'
            elif line_val >= 1.5:
                return 'Alta X'
        if any(x in s for x in ['1.5', '2.5', '3.5', '4.5', '2+', '3+', '4+', '2 tiros', '3 tiros', '2 faltas', '3 faltas', '2 entradas', '3 entradas']):
            return 'Alta X'
        if any(x in s for x in ['0.5', '1+', '1 tiro', '1 falta', '1 entrada']):
            return 'Suelo 0.5+'
        return 'Línea X'
    return 'Línea X'
