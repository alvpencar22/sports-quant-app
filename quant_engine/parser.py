import re
import os
import json
from .categories import categorize_item, get_line_level_type, extract_line_value, extract_player_name, normalize_text

# Regex for standard line with Cuota Justa or Cuota Mínima
LINE_PATTERN = re.compile(
    r"Mercado:\s*(.*?)\s*\|\s*Selecci[oó]n:\s*(.*?)\s*\|\s*(?:Cuota Justa|Cuota M[ií]nima):\s*(.*?)\s*\|\s*Cuota Real:\s*\[(.*?)\s*\]\s*\|\s*Veredicto:\s*\[(.*?)\s*\]\s*\|\s*Margen:\s*\[(.*?)\s*\]",
    re.IGNORECASE
)

# Alternative regex if only some fields are present (e.g., pre-match without Margen/Veredicto)
PREMATCH_LINE_PATTERN = re.compile(
    r"Mercado:\s*(.*?)\s*\|\s*Selecci[oó]n:\s*(.*?)\s*\|\s*(?:Cuota Justa|Cuota M[ií]nima):\s*(.*?)\s*\|\s*Cuota Real:\s*\[(.*?)\s*\]",
    re.IGNORECASE
)

def parse_float(val_str: str) -> float | None:
    if not val_str:
        return None
    cleaned = val_str.strip().replace('[', '').replace(']', '').replace(',', '.').strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None

def parse_int(val_str: str) -> int | None:
    if not val_str:
        return None
    cleaned = val_str.strip().replace('[', '').replace(']', '').replace('+', '').strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None

def parse_veredicto(val_str: str) -> str | None:
    if not val_str:
        return None
    cleaned = val_str.strip().replace('[', '').replace(']', '').strip().upper()
    # Normalize accents
    cleaned = cleaned.replace('Í', 'I').replace('Á', 'A').replace('É', 'E')
    if cleaned in ['SI', 'NO', 'ANULADA', 'VOID', 'PUSH']:
        return 'SI' if cleaned == 'SI' else ('NO' if cleaned == 'NO' else 'ANULADA')
    return None

def parse_single_line(line_text: str) -> dict | None:
    """Parsea una línea individual del formato estándar de pronósticos."""
    line = line_text.strip()
    if not line or 'Mercado:' not in line:
        return None

    m = LINE_PATTERN.search(line)
    if m:
        mercado, seleccion, cj_raw, cr_raw, ver_raw, mar_raw = m.groups()
    else:
        # Try prematch pattern
        m2 = PREMATCH_LINE_PATTERN.search(line)
        if m2:
            mercado, seleccion, cj_raw, cr_raw = m2.groups()
            ver_raw, mar_raw = "", ""
        else:
            # Fallback by splitting by pipe '|'
            parts = [p.strip() for p in line.split('|')]
            mercado, seleccion, cj_raw, cr_raw, ver_raw, mar_raw = "", "", "", "", "", ""
            for p in parts:
                lower = p.lower()
                if lower.startswith('mercado:'):
                    mercado = p.split(':', 1)[1].strip()
                elif 'selecci' in lower and ':' in p:
                    seleccion = p.split(':', 1)[1].strip()
                elif ('cuota justa:' in lower) or ('cuota minima:' in lower) or ('cuota mínima:' in lower):
                    cj_raw = p.split(':', 1)[1].strip()
                elif 'cuota real:' in lower:
                    cr_raw = p.split(':', 1)[1].strip()
                elif 'veredicto:' in lower:
                    ver_raw = p.split(':', 1)[1].strip()
                elif 'margen:' in lower:
                    mar_raw = p.split(':', 1)[1].strip()

    mercado = mercado.strip()
    seleccion = seleccion.strip()
    cj = parse_float(cj_raw)
    cr = parse_float(cr_raw)
    veredicto = parse_veredicto(ver_raw)
    margen = parse_int(mar_raw)

    cat = categorize_item(mercado, seleccion, line)
    lvl = get_line_level_type(cat, seleccion)
    line_val = extract_line_value(seleccion)
    player = extract_player_name(seleccion)

    return {
        'mercado': mercado,
        'seleccion': seleccion,
        'cj': cj,
        'cr': cr,
        'veredicto': veredicto,
        'margen': margen,
        'cat': cat,
        'line_level': lvl,
        'line_value': line_val,
        'player': player,
        'raw': line
    }

def detect_league(match_name: str, selections: list[str]) -> str:
    """
    Infiere la liga basándose en el nombre del partido (prioridad 1)
    y nombres de equipos, competiciones y jugadores (prioridad 2).
    Cubre el 100% de los clubes de Primera División (Serie A, La Liga, Premier, Bundesliga)
    y menciones explícitas de torneo.
    """
    m_norm = normalize_text(match_name or "").lower()
    all_text = ((match_name or "") + " " + " ".join(selections)).lower()
    all_norm = normalize_text(all_text)
    
    # 1. Menciones explícitas directas de competición
    if any(k in all_norm for k in ['champions league', 'champions', 'ucl', 'uefa champions']):
        return 'Champions League'
    if any(k in all_norm for k in ['serie a', 'calcio', 'liga italiana', 'coppa italia']):
        return 'Serie A'
    if any(k in all_norm for k in ['la liga', 'laliga', 'liga espanola', 'primera division']):
        return 'La Liga'
    if any(k in all_norm for k in ['premier league', 'premier', 'fa cup', 'carabao cup']):
        return 'Premier League'
    if any(k in all_norm for k in ['bundesliga', 'dfb pokal', 'liga alemana']):
        return 'Bundesliga'

    # 2. Choques cruzados conocidos entre equipos de distintos países (competiciones europeas)
    cl_pairs = [
        ('liverpool', 'villarreal'),
        ('bayern', 'arsenal'),
        ('porto', 'psv'),
        ('brujas', 'lens'),
        ('real madrid', 'manchester city'),
        ('barcelona', 'bayern'),
        ('inter', 'arsenal'),
        ('psg', 'atletico'),
        ('sporting', 'brugge'),
        ('dinamo', 'monaco')
    ]
    for ta, tb in cl_pairs:
        if (ta in m_norm and tb in m_norm) or (ta in all_norm and tb in all_norm):
            return 'Champions League'

    # Clubes Serie A (Todos los clubes de 1ª División de Italia y recientes)
    serie_a_clubs = [
        'inter', 'internazionale', 'ac milan', 'milan', 'juventus', 'juve',
        'napoli', 'napoles', 'roma', 'as roma', 'lazio', 'atalanta', 'fiorentina',
        'bologna', 'bolonia', 'torino', 'monza', 'genoa', 'genova', 'verona',
        'hellas verona', 'udinese', 'cagliari', 'lecce', 'empoli', 'parma',
        'como', 'venezia', 'venecia', 'salernitana', 'sassuolo', 'frosinone',
        'spezia', 'sampdoria', 'cremonese', 'brescia'
    ]

    # Clubes La Liga (Todos los clubes de 1ª División de España y recientes)
    la_liga_clubs = [
        'atletico', 'atleti', 'real madrid', 'barcelona', 'barca', 'athletic',
        'bilbao', 'real sociedad', 'sociedad', 'betis', 'sevilla', 'villarreal',
        'valencia', 'celta', 'mallorca', 'osasuna', 'rayo', 'vallecano',
        'getafe', 'girona', 'alaves', 'las palmas', 'espanyol', 'espanol',
        'leganes', 'valladolid', 'cadiz', 'granada', 'almeria', 'elche',
        'levante', 'malaga', 'racing', 'depor'
    ]

    # Clubes Premier League (Todos los clubes de Inglaterra)
    premier_clubs = [
        'manchester city', 'manchester united', 'manchester', 'arsenal',
        'liverpool', 'chelsea', 'tottenham', 'spurs', 'aston villa',
        'newcastle', 'brighton', 'west ham', 'fulham', 'brentford',
        'crystal palace', 'wolves', 'wolverhampton', 'everton', 'nottingham',
        'forest', 'leicester', 'southampton', 'ipswich', 'bournemouth', 'coventry'
    ]

    # Clubes Bundesliga (Alemania)
    bundesliga_clubs = [
        'bayern', 'dortmund', 'leverkusen', 'bayer leverkusen', 'leipzig',
        'frankfurt', 'eintracht', 'stuttgart', 'freiburg', 'friburgo', 'friburg',
        'wolfsburg', 'augsburg', 'werder', 'bremen', 'heidenheim', 'mainz',
        'gladbach', 'monchengladbach', 'union berlin', 'bochum', 'st. pauli', 'st pauli',
        'kiel', 'hoffenheim', 'elversberg', 'paderborn'
    ]

    # 3. ALTA PRIORIDAD: Inferencia directa desde el nombre del partido si está disponible
    if m_norm:
        if any(re.search(r'\b' + re.escape(c) + r'\b', m_norm) for c in premier_clubs):
            return 'Premier League'
        if any(re.search(r'\b' + re.escape(c) + r'\b', m_norm) for c in la_liga_clubs):
            return 'La Liga'
        if any(re.search(r'\b' + re.escape(c) + r'\b', m_norm) for c in serie_a_clubs):
            return 'Serie A'
        if any(re.search(r'\b' + re.escape(c) + r'\b', m_norm) for c in bundesliga_clubs):
            return 'Bundesliga'

    # 4. Inferencia secundaria desde las selecciones (evitando falsos positivos como jugadores llamados "Milan van...")
    safe_norm = re.sub(r'\bmilan\s+van\b', 'dutch_player', all_norm)

    if any(re.search(r'\b' + re.escape(c) + r'\b', safe_norm) for c in premier_clubs):
        return 'Premier League'
    if any(re.search(r'\b' + re.escape(c) + r'\b', safe_norm) for c in la_liga_clubs):
        return 'La Liga'
    if any(re.search(r'\b' + re.escape(c) + r'\b', safe_norm) for c in serie_a_clubs):
        return 'Serie A'
    if any(re.search(r'\b' + re.escape(c) + r'\b', safe_norm) for c in bundesliga_clubs):
        return 'Bundesliga'

    return 'Otras Ligas'

def parse_historial_file(file_path: str, canonical_dataset_path: str = None) -> list[dict]:
    """
    Parsea completamente el archivo historial_prompt.txt.
    Reconoce encabezados de partido (ej. 'chelsea vs manchester united'),
    asocia match_name y match_id a cada registro, y restaura Cuotas Justas.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"No se encontró el archivo: {file_path}")

    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    # Cargar datos canónicos si están disponibles para restaurar CJs y nombres de partidos previos
    cj_lookup = {}
    can_match_names = {}
    if canonical_dataset_path and os.path.exists(canonical_dataset_path):
        try:
            with open(canonical_dataset_path, 'r', encoding='utf-8') as f_can:
                can_records = json.load(f_can)
                for r in can_records:
                    if r.get('cj') is not None and r.get('seleccion'):
                        key = (r.get('match_id'), normalize_text(r.get('seleccion')))
                        cj_lookup[key] = r.get('cj')
                    mid = r.get('match_id')
                    mname = r.get('match_name')
                    if mid and mname and mid not in can_match_names:
                        can_match_names[mid] = mname
        except Exception as e:
            print(f"Aviso al cargar lookup canónico: {e}")

    chunks = [c.strip() for c in re.split(r'\n{2,}', content) if c.strip()]
    all_records = []

    match_idx = 0
    for chunk in chunks:
        lines = [l.strip() for l in chunk.split('\n') if l.strip()]
        market_lines = [l for l in lines if 'Mercado:' in l]
        if not market_lines:
            continue
        match_idx += 1

        # Detectar nombre del partido desde encabezado no-Mercado
        non_market = [l for l in lines if 'Mercado:' not in l and '|' not in l]
        if non_market:
            raw_mname = non_market[0]
            m_clean = re.sub(r'^(?:partido|match|encuentro)\s*:\s*', '', raw_mname, flags=re.IGNORECASE).strip()
            match_name = m_clean.title() if m_clean.islower() else m_clean
        elif match_idx in can_match_names:
            match_name = can_match_names[match_idx]
        else:
            match_name = f"Partido {match_idx}"

        # Inferencia de liga utilizando el nombre del partido y las selecciones
        sample_sels = [l.split('|')[1].strip() for l in market_lines if '|' in l]
        league = detect_league(match_name, sample_sels)

        for l in market_lines:
            rec = parse_single_line(l)
            if not rec:
                continue
            rec['match_id'] = match_idx
            rec['match_name'] = match_name
            rec['league'] = league

            # Restaurar CJ si venía en blanco
            if rec.get('cj') is None:
                key = (match_idx, normalize_text(rec.get('seleccion', '')))
                if key in cj_lookup:
                    rec['cj'] = cj_lookup[key]

            all_records.append(rec)

    return all_records

def parse_descalados_shorthand(shorthand_text: str) -> list[dict]:
    """
    Parsea texto abreviado de Tiempo 2 proporcionado por el usuario,
    ejemplo: 'julian 2 tiros 1.18, manu sanchez 2 entradas 1.28, over 1.5 goles 1.16'
    """
    items = []
    # Split by comma or newline
    tokens = re.split(r'[,;\n]+', shorthand_text)
    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue
        # Extract odds at the end
        m = re.search(r'(\d+(?:\.\d+)?)\s*$', tok)
        if not m:
            continue
        cr = float(m.group(1))
        desc = tok[:m.start()].strip()
        items.append({
            'descripcion': desc,
            'cr': cr,
            'raw': tok
        })
    return items

def extract_match_name_from_sheet(sheet_text: str, default: str = "Partido 1") -> str:
    """Extrae el nombre del partido desde un encabezado 'Partido: ...', 'equipo1 vs equipo2' o infiere por equipo."""
    for line in sheet_text.split('\n'):
        line_clean = line.strip()
        if not line_clean:
            continue
        m = re.match(r'^(?:partido|match|encuentro)\s*:\s*(.+)$', line_clean, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        # Si es una línea de enfrentamiento tipo "Chelsea vs Manchester United" o "Levante vs Atletico"
        if (' vs ' in line_clean.lower() or ' vs. ' in line_clean.lower()) and '|' not in line_clean and 'mercado:' not in line_clean.lower():
            return line_clean.title() if line_clean.islower() else line_clean
        # Si es la primera línea no vacía antes de cualquier mercado y no tiene pipes
        if 'mercado:' not in line_clean.lower() and '|' not in line_clean:
            return line_clean.title() if line_clean.islower() else line_clean
        break
    
    # Si no hay encabezado explícito, buscar el primer equipo de la selección
    from .categories import extract_team_name
    for line in sheet_text.split('\n'):
        if '|' in line:
            parts = line.split('|')
            if len(parts) > 1:
                sel = parts[1].replace('Selección:', '').replace('Seleccion:', '').strip()
                team = extract_team_name(sel)
                if team:
                    return f"{team} (Pre-Partido)"
    return default
