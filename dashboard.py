import streamlit as st
import pandas as pd
import os
import sys
import json
import re
import importlib

# Ensure UTF-8 output and local imports work cleanly
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# Forzar recarga de módulos subyacentes para que nunca queden en caché de Python/Streamlit
import quant_engine.categories
import quant_engine.parser
import quant_engine.math_engine
import quant_engine.optimizer
import quant_engine.auditor
import quant_engine.updater

importlib.reload(quant_engine.categories)
importlib.reload(quant_engine.parser)
importlib.reload(quant_engine.math_engine)
importlib.reload(quant_engine.optimizer)
importlib.reload(quant_engine.auditor)
importlib.reload(quant_engine.updater)

from quant_engine.parser import parse_historial_file, parse_single_line, parse_descalados_shorthand, detect_league, extract_match_name_from_sheet
from quant_engine.categories import categorize_item, get_line_level_type, extract_player_name
from quant_engine.math_engine import QuantEngine, CJ_INTERVALS
from quant_engine.optimizer import BulletOptimizer, BulletLeg
from quant_engine.updater import HistorialUpdater, analyze_selection_type, auto_resolve_selection, parse_match_teams, resolve_from_match_score

# Invalidar automáticamente sesiones heredadas obsoletas
SESSION_VERSION = "5.4_fix_team_year_descaling"
if st.session_state.get('app_session_version') != SESSION_VERSION:
    st.session_state.clear()
    st.session_state['app_session_version'] = SESSION_VERSION

DATA_DIR = os.path.join(BASE_DIR, 'data')
HIST_PATH = os.path.join(DATA_DIR, 'historial_prompt.txt')
DATASET_PATH = os.path.join(DATA_DIR, 'categorized_dataset.json')
MATCHES_DIR = os.path.join(DATA_DIR, 'matches')
VALUE_BOARD_PATH = os.path.join(MATCHES_DIR, 'match_value_board.json')

st.set_page_config(
    page_title="Sports Quant App",
    page_icon="⚽",
    layout="wide"
)

# -------------------------------------------------------------
# MOTOR CUANTITATIVO CON AUTO-RECARGA DINÁMICA MULTI-ARCHIVO
# -------------------------------------------------------------
def get_engine_cache_key() -> tuple:
    files = [
        HIST_PATH,
        DATASET_PATH,
        os.path.join(BASE_DIR, 'quant_engine', 'math_engine.py'),
        os.path.join(BASE_DIR, 'quant_engine', 'categories.py'),
        os.path.join(BASE_DIR, 'quant_engine', 'parser.py'),
    ]
    return tuple(os.path.getmtime(f) if os.path.exists(f) else 0.0 for f in files)

@st.cache_resource
def load_engine(cache_key: tuple):
    records = parse_historial_file(HIST_PATH, DATASET_PATH)
    return QuantEngine(records)

engine = load_engine(get_engine_cache_key())
hist_updater = HistorialUpdater(HIST_PATH)

# -------------------------------------------------------------
# GESTIÓN DE TABLA MAESTRA DE SELECCIONES CON VALOR (MULTI-PARTIDO)
# -------------------------------------------------------------
def load_value_board() -> list:
    board = None
    if 'match_value_board' in st.session_state and st.session_state['match_value_board'] is not None:
        board = st.session_state['match_value_board']
    elif os.path.exists(VALUE_BOARD_PATH):
        try:
            with open(VALUE_BOARD_PATH, 'r', encoding='utf-8') as f:
                board = json.load(f)
        except Exception:
            pass
    if board is None:
        board = []
    
    # Retrocompatibilidad: asegurar que cada apuesta tenga su partido asignado
    for b in board:
        if 'partido' not in b or not b['partido']:
            b['partido'] = "Partido General"
            
    st.session_state['match_value_board'] = board
    return board

def save_value_board(board: list):
    st.session_state['match_value_board'] = board
    os.makedirs(MATCHES_DIR, exist_ok=True)
    with open(VALUE_BOARD_PATH, 'w', encoding='utf-8') as f:
        json.dump(board, f, indent=2, ensure_ascii=False)

def make_value_entry(
    seleccion: str,
    tipo: str,
    mercado: str,
    cr: float,
    hr_glob: float,
    be_glob: float,
    n_glob: int,
    w_glob: int,
    hr_liga: float = None,
    be_liga: float = None,
    n_liga: int = 0,
    w_liga: int = 0,
    partido: str = "Partido General"
) -> dict:
    ev_glob = round((cr * (hr_glob / 100.0)) - 1.0, 4) if (hr_glob and be_glob) else None
    ev_liga = round((cr * (hr_liga / 100.0)) - 1.0, 4) if (hr_liga and be_liga and n_liga > 0) else None
    
    if ev_glob is not None and ev_liga is not None and ev_glob > 0 and ev_liga > 0:
        sello = "🔥 DOBLE VALOR (+EV Glo & Lig)"
    elif ev_liga is not None and ev_liga > 0:
        sello = "🟢 VALOR LIGA (+EV Lig)"
    elif ev_glob is not None and ev_glob > 0:
        sello = "🟡 VALOR GLOBAL (+EV Glo)"
    else:
        sello = "⚠️ SIN VALOR (CR < BE)"

    return {
        'partido': partido,
        'seleccion': seleccion,
        'tipo': tipo,
        'mercado': mercado,
        'cr': cr,
        'hr_glob': hr_glob,
        'be_glob': be_glob,
        'n_glob': n_glob,
        'w_glob': w_glob,
        'ev_glob': ev_glob,
        'hr_liga': hr_liga,
        'be_liga': be_liga,
        'n_liga': n_liga,
        'w_liga': w_liga,
        'ev_liga': ev_liga,
        'sello': sello
    }

# -------------------------------------------------------------
# SIDEBAR
# -------------------------------------------------------------
st.sidebar.markdown("### 📁 Base de Datos Cuantitativa")
pending_matches_list = hist_updater.get_pending_matches()
total_pending_count = sum(m['pending_count'] for m in pending_matches_list)

st.sidebar.info(
    f"📄 **historial_prompt.txt**\n"
    f"- Total pronósticos: **{len(engine.raw_records)}**\n"
    f"- Muestra concluida: **{len(engine.settled_records)}**\n"
    f"- Partidos analizados: **{len(set(r.get('match_id') for r in engine.raw_records if r.get('match_id')))}**"
)

if pending_matches_list:
    st.sidebar.warning(f"⏳ **Partidos Pendientes:** {len(pending_matches_list)}\n({total_pending_count} pronósticos sin resolver)")
else:
    st.sidebar.success("✅ **Todos los partidos cerrados** (0 pendientes)")

if st.sidebar.button("🔄 Recargar Historial Ahora"):
    st.cache_resource.clear()
    st.session_state.clear()
    st.toast("Base de datos y sesión recargadas con éxito.")
    st.rerun()

if os.path.exists(HIST_PATH):
    with open(HIST_PATH, 'r', encoding='utf-8') as f_dl:
        hist_content = f_dl.read()
    st.sidebar.download_button(
        label="📥 Descargar historial_prompt.txt",
        data=hist_content,
        file_name="historial_prompt.txt",
        mime="text/plain",
        help="Descarga una copia de tu historial con los partidos rellenados.",
        use_container_width=True
    )

st.sidebar.markdown("---")
board_count = len(load_value_board())
st.sidebar.markdown(f"### 💎 Selecciones con Valor: **{board_count}**")
if st.sidebar.button("🗑️ Vaciar Tabla de Valor"):
    save_value_board([])
    st.rerun()

# -------------------------------------------------------------
# MAIN APP TABS
# -------------------------------------------------------------
st.title("⚽ Sports Quant App — Plataforma Cuantitativa de Apuestas")
st.caption("Motor matemático sin sesgo empírico. Evaluación integral de cuotas, márgenes, descalados y optimización de balas.")

tab_status, tab_t1, tab_board, tab_t2, tab_explore, tab_fill = st.tabs([
    "📊 Estado y Ligas",
    "⏱️ Tiempo 1 (Ex-Ante)",
    "💎 Tabla Maestra de Valor",
    "🎯 Tiempo 2 (Optimización Balas)",
    "🔍 Explorador de Líneas (X+k / Unders)",
    "📝 Cierre de Partidos (Historial)"
])

# -------------------------------------------------------------
# TAB 1: ESTADO Y LIGAS
# -------------------------------------------------------------
with tab_status:
    st.subheader("Estado del Sistema Cuantitativo")
    
    col1, col2, col3, col4 = st.columns(4)
    total_records = len(engine.raw_records)
    settled_records = len(engine.settled_records)
    matches_count = len(set(r.get('match_id') for r in engine.raw_records if r.get('match_id')))
    overall_hr = engine.compute_basic_stats(engine.settled_records)['hr']

    col1.metric("Total Pronósticos", total_records)
    col2.metric("Partidos Registrados", matches_count)
    col3.metric("Muestra Concluida", settled_records)
    col4.metric("Hit Rate Global", f"{overall_hr}%")

    st.markdown("---")
    st.subheader("Rendimiento Empírico por Liga")
    
    leagues = sorted(list(set(r.get('league', 'Otras Ligas') for r in engine.settled_records)))
    league_rows = []
    for lg in leagues:
        sub = [r for r in engine.settled_records if r.get('league') == lg]
        st_lg = engine.compute_basic_stats(sub)
        league_rows.append({
            'Liga': lg,
            'Muestra (N)': st_lg['n'],
            'Aciertos (W)': st_lg['w'],
            'Hit Rate (%)': f"{st_lg['hr']}%",
            'Cuota Break-Even': f"@ {st_lg['be']:.2f}"
        })
    st.dataframe(pd.DataFrame(league_rows), use_container_width=True)

    st.markdown("---")
    st.subheader("Rendimiento Empírico por Franja de Cuota Justa")
    franja_rows = []
    for code, label, cond in CJ_INTERVALS:
        sub = [r for r in engine.settled_records if r.get('cj') is not None and cond(r['cj'])]
        st_fr = engine.compute_basic_stats(sub)
        franja_rows.append({
            'Franja CJ': code,
            'Nivel de Confianza': label,
            'Muestra (N)': st_fr['n'],
            'Aciertos (W)': st_fr['w'],
            'Hit Rate (%)': f"{st_fr['hr']}%",
            'Cuota Break-Even': f"@ {st_fr['be']:.2f}"
        })
    st.dataframe(pd.DataFrame(franja_rows), use_container_width=True)

    st.markdown("---")
    st.subheader("⚽ Desglose y Auditoría de Historial por Partido")
    st.caption("Resumen consolidado de todos los partidos registrados en `historial_prompt.txt` con su liga detectada, volumen de pronósticos y efectividad empírica.")
    
    matches_summary = engine.get_matches_summary()
    if matches_summary:
        c_m_lg, c_m_search = st.columns([1, 2])
        all_hist_leagues = ["Todas las Ligas"] + sorted(list(set(m['league'] for m in matches_summary)))
        selected_hist_lg = c_m_lg.selectbox("Filtrar por Liga:", all_hist_leagues, key="hist_filter_lg")
        search_match = c_m_search.text_input("Buscar Partido por Nombre:", "", placeholder="Ej: Chelsea, Bologna, Leverkusen...", key="hist_search_match")

        filtered_summary = matches_summary
        if selected_hist_lg != "Todas las Ligas":
            filtered_summary = [m for m in filtered_summary if m['league'] == selected_hist_lg]
        if search_match.strip():
            kw = search_match.strip().lower()
            filtered_summary = [m for m in filtered_summary if kw in m['match_name'].lower()]

        table_m_rows = []
        for m in filtered_summary:
            table_m_rows.append({
                'ID': f"#{m['match_id']:02d}",
                'Partido': m['match_name'],
                'Liga': m['league'],
                'Total Pronósticos': m['total_pronosticos'],
                'Muestra Concluida (N)': m['n_concluido'],
                'Aciertos (W)': m['w_aciertos'],
                'Hit Rate (%)': f"{m['hr']}%" if m['n_concluido'] > 0 else "N/A",
                'Cuota Break-Even': f"@ {m['be']:.2f}" if m['n_concluido'] > 0 else "N/A"
            })
        st.dataframe(pd.DataFrame(table_m_rows), use_container_width=True)

        with st.expander("🔍 Inspeccionar Pronósticos de un Partido Específico", expanded=False):
            match_opts = {f"#{m['match_id']:02d} — {m['match_name']} ({m['league']})": m for m in filtered_summary}
            if match_opts:
                sel_m_label = st.selectbox("Selecciona Partido:", list(match_opts.keys()))
                sel_m_data = match_opts[sel_m_label]
                
                det_rows = []
                for r in sel_m_data['records']:
                    ver = r.get('veredicto')
                    ver_badge = "✅ SÍ" if ver == 'SI' else ("❌ NO" if ver == 'NO' else "🟡 " + str(ver or "Pendiente"))
                    det_rows.append({
                        'Mercado': r.get('mercado'),
                        'Selección': r.get('seleccion'),
                        'Cuota Justa': f"@ {r['cj']:.2f}" if r.get('cj') else "-",
                        'Cuota Real': f"@ {r['cr']:.2f}" if r.get('cr') else "-",
                        'Veredicto': ver_badge,
                        'Margen': f"{r['margen']:+d}" if r.get('margen') is not None else "-"
                    })
                st.dataframe(pd.DataFrame(det_rows), use_container_width=True)

# -------------------------------------------------------------
# TAB 2: TIEMPO 1 (EX-ANTE)
# -------------------------------------------------------------
with tab_t1:
    st.subheader("⏱️ Tiempo 1: Estudio Cuantitativo Completo y Ex-Ante")
    st.write("Análisis exhaustivo pre-partido con métricas empíricas Globales vs Liga, espectro completo de descalados y radar de cuotas a buscar en Tiempo 2.")
    
    atletico_example_text = """Mercado: Resultado Final (1X2) | Selección: Atlético de Madrid — Victoria | Cuota Mínima: 1.55 | Cuota Real: [1.5 ] | Veredicto: [ ] | Margen: [ ]
Mercado: Ambos Equipos Marcan | Selección: Ambos Equipos Marcan — Sí | Cuota Mínima: 1.58 | Cuota Real: [1.61 ] | Veredicto: [ ] | Margen: [ ]
Mercado: Total de Goles | Selección: Más de 2.5 Goles Totales | Cuota Mínima: 1.52 | Cuota Real: [ 1.53] | Veredicto: [ ] | Margen: [ ]
Mercado: Córners Totales | Selección: Más de 8.5 Córners Totales | Cuota Mínima: 1.45 | Cuota Real: [ 1.44] | Veredicto: [ ] | Margen: [ ]
Mercado: Entradas / Tackles de Jugador | Selección: Manu Sánchez — Más de 2.5 Entradas / Tackles | Cuota Mínima: 1.55 | Cuota Real: [ 1.83] | Veredicto: [ ] | Margen: [ ]
Mercado: Entradas / Tackles de Jugador | Selección: Álex Baena — Más de 0.5 Entradas / Tackles | Cuota Mínima: 1.38 | Cuota Real: [ 1.36] | Veredicto: [ ] | Margen: [ ]
Mercado: Tarjetas Totales | Selección: Más de 4.5 Tarjetas Amarillas Totales | Cuota Mínima: 1.58 | Cuota Real: [2.37 ] | Veredicto: [ ] | Margen: [ ]
Mercado: Tiros de Jugador | Selección: Julián Álvarez — Más de 2.5 Tiros Totales | Cuota Mínima: 1.45 | Cuota Real: [1.57 ] | Veredicto: [ ] | Margen: [ ]
Mercado: Tiros a Puerta de Jugador | Selección: Alejandro Grimaldo — Más de 0.5 Tiros a Puerta | Cuota Mínima: 1.80 | Cuota Real: [ 1.83] | Veredicto: [ ] | Margen: [ ]"""

    # Iniciar siempre vacío al entrar a la aplicación
    if 't1_sheet_input_widget' not in st.session_state:
        st.session_state['t1_sheet_input_widget'] = ""

    curr_sheet = st.session_state.get('t1_sheet_input_widget', '')

    c_hdr_txt, c_hdr_opt = st.columns([3, 1])
    with c_hdr_opt:
        with st.popover("⚙️ Opciones de Hoja"):
            if st.button("📄 Cargar Ejemplo (Atlético de Madrid)", use_container_width=True):
                sheet_file = os.path.join(MATCHES_DIR, 'sheet_atletico_prematch.txt')
                ex_text = atletico_example_text
                if os.path.exists(sheet_file):
                    try:
                        with open(sheet_file, 'r', encoding='utf-8') as f:
                            c = f.read().strip()
                            if c:
                                ex_text = c
                    except Exception:
                        pass
                st.session_state['t1_sheet_input_widget'] = ex_text
                st.rerun()
            if st.button("🗑️ Vaciar Hoja", use_container_width=True):
                st.session_state['t1_sheet_input_widget'] = ""
                st.rerun()
            if curr_sheet.strip():
                if st.button("📥 Guardar en Historial como Pendiente", use_container_width=True):
                    m_title = extract_match_name_from_sheet(curr_sheet, "Nuevo Partido")
                    try:
                        hist_updater.append_new_match(m_title, curr_sheet, backup=True)
                        st.cache_resource.clear()
                        st.toast(f"✅ Partido '{m_title}' guardado como pendiente en historial.")
                        st.rerun()
                    except Exception as e_app:
                        st.error(f"Error al guardar: {e_app}")

    sheet_input = st.text_area(
        "Hoja de Pronósticos Pre-Partido:",
        height=200,
        placeholder="Pega aquí el listado de selecciones del partido a analizar...\nFormato:\nMercado: Total de Goles | Selección: Más de 2.5 Goles Totales | Cuota Mínima: 1.50 | Cuota Real: [1.60]",
        key="t1_sheet_input_widget"
    )

    # Inferencia automática de liga y nombre del partido a partir del contenido de la hoja
    sample_sels = [l.split('|')[1].strip() for l in sheet_input.split('\n') if '|' in l]
    auto_lg = detect_league("", sample_sels) if sample_sels else "Global (Sin Filtro)"
    league_options = ["La Liga", "Serie A", "Premier League", "Bundesliga", "Champions League", "Global (Sin Filtro)"]
    default_lg_idx = league_options.index(auto_lg) if auto_lg in league_options else 5

    col_match, col_lg, col_btn = st.columns([2, 1, 1])
    inferred_match_name = extract_match_name_from_sheet(sheet_input, "Nuevo Partido") if sheet_input.strip() else "Nuevo Partido"
    match_name_input = col_match.text_input("Identificador del Partido:", value=inferred_match_name)
    league_selected = col_lg.selectbox("Liga del Partido", league_options, index=default_lg_idx)
    league_param = None if league_selected.startswith("Global") else league_selected

    # Detección de cambios de texto, partido o liga para auto-recálculo instantáneo
    sheet_hash = hash((sheet_input.strip(), league_param, match_name_input.strip()))
    btn_eval = col_btn.button("⚡ Ejecutar Estudio Cuantitativo T1", type="primary")

    deep_items = []
    if not sheet_input.strip():
        st.session_state['t1_deep_items'] = []
        st.session_state['t1_sheet_hash'] = sheet_hash
        st.info("📋 **La hoja de pronósticos está vacía.** Pega en el cuadro superior las selecciones de tu partido en formato `Mercado: ... | Selección: ... | Cuota Mínima: ... | Cuota Real: [...]` para ejecutar el estudio cuantitativo, o despliega '⚙️ Opciones de Hoja' para cargar un ejemplo de prueba.")
    else:
        need_eval = (
            't1_deep_items' not in st.session_state
            or st.session_state.get('t1_sheet_hash') != sheet_hash
            or btn_eval
        )

        if need_eval:
            lines = [l.strip() for l in sheet_input.split('\n') if l.strip() and 'Mercado:' in l]
            deep_items = []
            for l in lines:
                rec = parse_single_line(l)
                if not rec:
                    continue
                ev_deep = engine.evaluate_selection_deep(
                    mercado=rec['mercado'],
                    seleccion=rec['seleccion'],
                    cj=rec['cj'],
                    cr=rec['cr'],
                    league=league_param
                )
                deep_items.append(ev_deep)
            st.session_state['t1_deep_items'] = deep_items
            st.session_state['t1_sheet_hash'] = sheet_hash
            st.session_state['t1_league'] = league_param
            st.session_state['t1_match_name'] = match_name_input

            # AUTO-POBLACIÓN AUTOMÁTICA EN LA TABLA MAESTRA DE VALOR (SECCIÓN DEL PARTIDO)
            board = load_value_board()
            # Eliminar únicamente las apuestas previas tipo Base X de este mismo partido para sincronizar sin duplicar
            board = [x for x in board if not (x.get('partido') == match_name_input and x.get('tipo') == "Base X Pre-Partido")]
            auto_added_count = 0
            for it in deep_items:
                b = it.get('base', {})
                cr = it.get('cr')
                if cr and ((b.get('ev_glob') and b['ev_glob'] > 0) or (b.get('ev_liga') and b['ev_liga'] > 0)):
                    entry = make_value_entry(
                        partido=match_name_input,
                        seleccion=it['seleccion'],
                        tipo="Base X Pre-Partido",
                        mercado=it['cat'],
                        cr=cr,
                        hr_glob=b.get('hr_glob', 0.0),
                        be_glob=b.get('be_glob', 1.0),
                        n_glob=b.get('n_glob', 0),
                        w_glob=b.get('w_glob', 0),
                        hr_liga=b.get('hr_liga'),
                        be_liga=b.get('be_liga'),
                        n_liga=b.get('n_liga', 0),
                        w_liga=b.get('w_liga', 0)
                    )
                    board.append(entry)
                    auto_added_count += 1
            save_value_board(board)
            st.session_state['t1_auto_added_count'] = auto_added_count
        else:
            deep_items = st.session_state.get('t1_deep_items', [])

    if deep_items:
        current_match_label = st.session_state.get('t1_match_name', match_name_input)
        val_count = sum(1 for it in deep_items if it.get('cr') and ((it['base'].get('ev_glob') and it['base']['ev_glob'] > 0) or (it['base'].get('ev_liga') and it['base']['ev_liga'] > 0)))
        st.success(f"✨ **{current_match_label}**: Se detectaron **{val_count} selecciones con valor pre-partido ($+EV$)** integradas automáticamente en la **Tabla Maestra de Valor**.")

        # -------------------------------------------------------------
        # 1. TABLA 1: MATRIZ MAESTRA COMPARATIVA — LÍNEA BASE X
        # -------------------------------------------------------------
        st.markdown("### 📋 Tabla 1: Matriz Comparativa — Línea Base X (Global vs Liga)")
        st.caption("Comparación directa de N muestral, W aciertos, Hit Rate y Cuota Justa / Break-Even tanto para el Global como para la Liga específica.")
        
        table1_rows = []
        for it in deep_items:
            b = it.get('base', {})
            hr_g = b.get('hr_glob', b.get('hr', 0.0))
            be_g = b.get('be_glob', b.get('be', 1.0))
            n_g = b.get('n_glob', b.get('n', 0))
            w_g = b.get('w_glob', b.get('w', 0))
            hr_l = b.get('hr_liga')
            be_l = b.get('be_liga')
            n_l = b.get('n_liga', 0)
            w_l = b.get('w_liga', 0)

            table1_rows.append({
                'Selección': it['seleccion'],
                'Categoría': it['cat'],
                'CJ': it['cj'],
                'CR': it['cr'],
                'N Global': n_g,
                'W Global': w_g,
                'HR Global (%)': f"{hr_g}%",
                'Cuota Justa Global': f"@ {be_g:.2f}",
                'N Liga': n_l if n_l > 0 else "-",
                'W Liga': w_l if n_l > 0 else "-",
                'HR Liga (%)': f"{hr_l}%" if n_l > 0 and hr_l is not None else "-",
                'Cuota Justa Liga': f"@ {be_l:.2f}" if n_l > 0 and be_l is not None else "-",
                'EV Global': round(b.get('ev_glob'), 4) if b.get('ev_glob') is not None else None,
                'EV Liga': round(b.get('ev_liga'), 4) if b.get('ev_liga') is not None else None
            })
        df_t1 = pd.DataFrame(table1_rows)
        st.dataframe(df_t1, use_container_width=True)

        # -------------------------------------------------------------
        # 2. TABLA 2: ESTUDIO DE LÍNEAS ALTERNATIVAS (DESCALADOS Y UNDERS)
        # -------------------------------------------------------------
        st.markdown("### 🔍 Tabla 2: Estudio Completo de Líneas Alternativas (Descalados X-1..X-3 y Espectro Completo de Unders X..X+3)")
        st.caption("Evolución matemática del Hit Rate y Cuota Justa conforme se descala la línea o se evalúa la opción Under con sus nombres reales de mercado. En mercados de jugadores (tiros, faltas, entradas, etc.) no existen líneas Under; solo aplican descalados Over.")

        table2_rows = []
        for it in deep_items:
            # Base
            b = it.get('base', {})
            hr_g = b.get('hr_glob', b.get('hr', 0.0))
            be_g = b.get('be_glob', b.get('be', 1.0))
            table2_rows.append({
                'Selección Base': it['seleccion'],
                'Nivel / Tipo': 'Línea Base X',
                'Línea Concreta de Apuesta': b.get('label', it['seleccion']),
                'N Global': b.get('n_glob', 0),
                'W Global': b.get('w_glob', 0),
                'HR Global (%)': f"{hr_g}%",
                'Cuota Justa Global': f"@ {be_g:.2f}",
                'N Liga': b.get('n_liga') if b.get('n_liga', 0) > 0 else "-",
                'W Liga': b.get('w_liga') if b.get('n_liga', 0) > 0 else "-",
                'HR Liga (%)': f"{b.get('hr_liga')}%" if b.get('n_liga', 0) > 0 else "-",
                'Cuota Justa Liga': f"@ {b.get('be_liga'):.2f}" if b.get('n_liga', 0) > 0 and b.get('be_liga') else "-"
            })
            # Descalados
            for d in it.get('descalados_spectrum', []):
                table2_rows.append({
                    'Selección Base': it['seleccion'],
                    'Nivel / Tipo': d['tag'],
                    'Línea Concreta de Apuesta': d['label'],
                    'N Global': d.get('n_glob', 0),
                    'W Global': d.get('w_glob', 0),
                    'HR Global (%)': f"{d.get('hr_glob', 0.0)}%",
                    'Cuota Justa Global': f"@ {d.get('be_glob', 1.0):.2f}",
                    'N Liga': d.get('n_liga') if d.get('n_liga', 0) > 0 else "-",
                    'W Liga': d.get('w_liga') if d.get('n_liga', 0) > 0 else "-",
                    'HR Liga (%)': f"{d.get('hr_liga')}%" if d.get('n_liga', 0) > 0 else "-",
                    'Cuota Justa Liga': f"@ {d.get('be_liga'):.2f}" if d.get('n_liga', 0) > 0 and d.get('be_liga') else "-"
                })
            # Unders
            for u in it.get('unders_spectrum', []):
                table2_rows.append({
                    'Selección Base': it['seleccion'],
                    'Nivel / Tipo': u['tag'],
                    'Línea Concreta de Apuesta': u['label'],
                    'N Global': u.get('n_glob', 0),
                    'W Global': u.get('w_glob', 0),
                    'HR Global (%)': f"{u.get('hr_glob', 0.0)}%",
                    'Cuota Justa Global': f"@ {u.get('be_glob', 1.0):.2f}",
                    'N Liga': u.get('n_liga') if u.get('n_liga', 0) > 0 else "-",
                    'W Liga': u.get('w_liga') if u.get('n_liga', 0) > 0 else "-",
                    'HR Liga (%)': f"{u.get('hr_liga')}%" if u.get('n_liga', 0) > 0 else "-",
                    'Cuota Justa Liga': f"@ {u.get('be_liga'):.2f}" if u.get('n_liga', 0) > 0 and u.get('be_liga') else "-"
                })
        
        df_t2 = pd.DataFrame(table2_rows)
        st.dataframe(df_t2, use_container_width=True)

        # -------------------------------------------------------------
        # INSPECTOR GRÁFICO VISUAL DE CURVA DE LÍNEAS
        # -------------------------------------------------------------
        st.markdown("### 📊 Inspector Visual de Curva de Probabilidades (Hit Rate por Línea)")
        sel_names = [it['seleccion'] for it in deep_items]
        chosen_sel = st.selectbox("Selecciona una apuesta para visualizar su curva de probabilidad:", sel_names)
        
        target_item = next((it for it in deep_items if it['seleccion'] == chosen_sel), None)
        if target_item:
            chart_data = []
            b = target_item.get('base', {})
            chart_data.append({'Línea': f"Base: {b.get('label', target_item['seleccion'])[:25]}", 'Hit Rate Global (%)': b.get('hr_glob', 0.0)})
            for d in target_item.get('descalados_spectrum', []):
                chart_data.append({'Línea': f"{d['tag']}: {d['label'][:25]}", 'Hit Rate Global (%)': d.get('hr_glob', 0.0)})
            for u in target_item.get('unders_spectrum', []):
                chart_data.append({'Línea': f"{u['tag']}: {u['label'][:25]}", 'Hit Rate Global (%)': u.get('hr_glob', 0.0)})
            
            df_chart = pd.DataFrame(chart_data).set_index('Línea')
            st.bar_chart(df_chart, use_container_width=True)

        # -------------------------------------------------------------
        # 3. SECCIÓN 3: RADAR DE CUOTAS A MIRAR PARA TIEMPO 2
        # -------------------------------------------------------------
        st.markdown("### 🎯 Radar de Sugerencias para Tiempo 2 (Descalados y Espectro Completo de Unders)")
        st.info("Revisa las cuotas en tu casa de apuestas para las líneas sugeridas. Nota: En mercados de jugadores solo se evalúan descalados Over (no existen líneas Under en casas de apuestas). Si pagan por encima de la Cuota Mínima, escribe la Cuota Real y haz clic en **➕ Añadir a Tabla de Valor**.")

        recs_count = 0
        for it in deep_items:
            recs = it.get('t2_recommendations', [])
            if recs:
                with st.expander(f"📌 Sugerencias para: **{it['seleccion']}** ({len(recs)} opciones)", expanded=True):
                    for r in recs:
                        recs_count += 1
                        badge_color = "🟢" if "Suelo" in r.get('tipo', '') or "X-1" in r.get('tipo', '') else ("🔄" if "Under" in r.get('tipo', '') else "🔥")
                        st.markdown(f"**{badge_color} [{r.get('tipo', 'Línea')}]** `{r.get('linea_sugerida', '')}`")
                        
                        hr_g = r.get('hr_glob', r.get('hr'))
                        w_g = r.get('w_glob', r.get('w', 0))
                        n_g = r.get('n_glob', r.get('n', 0))
                        be_g = r.get('be_glob', r.get('be'))

                        # Malla de seguridad ante dicts antiguos
                        if hr_g is None or hr_g == 0.0:
                            if 'Base' in r.get('tipo', ''):
                                hr_g = it.get('base', {}).get('hr_glob', 0.0)
                                w_g = it.get('base', {}).get('w_glob', 0)
                                n_g = it.get('base', {}).get('n_glob', 0)
                                be_g = it.get('base', {}).get('be_glob', 1.0)
                            else:
                                m_all = re.findall(r'([0-9]+(?:\.[0-9]+)?)\s*%', r.get('razon', ''))
                                if m_all:
                                    hr_g = float(m_all[0])
                                    if be_g is None and hr_g > 0:
                                        be_g = round(100.0 / hr_g, 2)

                        if be_g is None:
                            be_g = round(100.0 / hr_g, 2) if hr_g and hr_g > 0 else 1.0
                        
                        hr_l = r.get('hr_liga')
                        w_l = r.get('w_liga', 0)
                        n_l = r.get('n_liga', 0)
                        be_l = r.get('be_liga')
                        if hr_l is not None and be_l is None and hr_l > 0:
                            be_l = round(100.0 / hr_l, 2)

                        c_r1, c_r2, c_r3, c_r4 = st.columns(4)
                        c_r1.metric("Hit Rate Global", f"{hr_g}%", f"W={w_g}/{n_g} (BE @{be_g:.2f})" if n_g > 0 else f"BE @{be_g:.2f}")
                        if league_param is None:
                            c_r2.metric("Hit Rate Liga", "N/A", "Filtro Global activo")
                        elif hr_l is not None and n_l > 0:
                            be_str = f"W={w_l}/{n_l} (BE @{be_l:.2f})" if be_l else f"W={w_l}/{n_l}"
                            c_r2.metric(f"Hit Rate {league_param}", f"{hr_l}%", be_str)
                        else:
                            c_r2.metric(f"Hit Rate {league_param if league_param else 'Liga'}", "N/A", "Sin datos liga")
                        
                        min_exigida = r.get('cuota_minima_exigida', be_g)
                        obj_sug = r.get('cuota_objetivo', round(min_exigida * 1.10, 2))
                        c_r3.metric("Cuota Mínima Exigida", f"@ {min_exigida:.2f}")
                        c_r4.metric("Cuota Objetivo Sugerida", f">= @ {obj_sug:.2f}")
                        st.caption(f"**Justificación Matemática:** {r.get('razon', '')}")

                        # Formulario interactivo para registrar la Cuota Real encontrada
                        c_in_cr, c_btn_add = st.columns([3, 1])
                        user_cr_val = c_in_cr.number_input(
                            f"Cuota Real en casa para '{r.get('linea_sugerida', '')}':",
                            min_value=1.01,
                            max_value=50.0,
                            value=float(obj_sug),
                            step=0.01,
                            key=f"cr_sug_input_{recs_count}"
                        )
                        if c_btn_add.button("➕ Añadir a Tabla de Valor", key=f"btn_add_board_{recs_count}"):
                            board = load_value_board()
                            match_name_curr = st.session_state.get('t1_match_name', match_name_input)
                            entry = make_value_entry(
                                partido=match_name_curr,
                                seleccion=r.get('linea_sugerida', ''),
                                tipo=r.get('tipo', 'Línea'),
                                mercado=it.get('cat', ''),
                                cr=user_cr_val,
                                hr_glob=hr_g,
                                be_glob=be_g,
                                n_glob=n_g,
                                w_glob=w_g,
                                hr_liga=hr_l,
                                be_liga=be_l,
                                n_liga=n_l,
                                w_liga=w_l
                            )
                            board = [x for x in board if not (x.get('partido') == entry['partido'] and x['seleccion'] == entry['seleccion'])]
                            board.append(entry)
                            save_value_board(board)
                            st.toast(f"✅ Añadida a Tabla de Valor [{match_name_curr}]: {entry['seleccion']} [@ {user_cr_val:.2f}]")
                            st.rerun()

                        st.markdown("---")

        if recs_count == 0:
            st.success("Todas las líneas de la hoja operan en rangos estables sin necesidad de descalados urgentes.")

# -------------------------------------------------------------
# TAB 3: SECCIÓN ESPECÍFICA — TABLA MAESTRA DE VALOR (MULTI-PARTIDO)
# -------------------------------------------------------------
with tab_board:
    st.subheader("💎 Tabla Maestra de Selecciones con Valor")
    st.write(
        "Panel central y persistente de **todas las selecciones con ventaja cuantitativa ($+EV$)** organizadas por partido. "
        "Permite auditar el Hit Rate Global y de Liga, la Cuota Break-Even, el EV generado con la Cuota Real, "
        "dividir la visualización por partido específico o consolidada, y transferir estas apuestas a Tiempo 2."
    )

    current_board = load_value_board()
    all_matches = sorted(list(set(x.get('partido', 'Partido General') for x in current_board)))

    if current_board:
        # Filtros de visualización y selector de modo
        c_filter_match, c_filter_seal, c_filter_view = st.columns([1.5, 1.2, 1.3])
        match_filter_options = ["Todos los Partidos (Vista Consolidada)"] + all_matches
        selected_match = c_filter_match.selectbox("⚽ Filtrar por Partido:", match_filter_options)
        
        filter_opt = c_filter_seal.selectbox(
            "🏷️ Filtrar por Sello:",
            ["Mostrar Todas", "🔥 Solo Doble Valor", "🟢 Solo Valor Liga", "🟡 Solo Valor Global"]
        )

        view_mode = c_filter_view.radio("Modo de Visualización:", ["🎴 Tarjetas Visuales", "📊 Tabla Interactiva Pro"], horizontal=True)

        filtered_board = current_board
        if not selected_match.startswith("Todos"):
            filtered_board = [x for x in filtered_board if x.get('partido') == selected_match]

        if filter_opt == "🔥 Solo Doble Valor":
            filtered_board = [x for x in filtered_board if "DOBLE VALOR" in x.get('sello', '')]
        elif filter_opt == "🟢 Solo Valor Liga":
            filtered_board = [x for x in filtered_board if "VALOR LIGA" in x.get('sello', '')]
        elif filter_opt == "🟡 Solo Valor Global":
            filtered_board = [x for x in filtered_board if "VALOR GLOBAL" in x.get('sello', '')]

        # ORDENACIÓN OBLIGATORIA: De mayor a menor Valor Esperado (+EV descendente)
        filtered_board = sorted(
            filtered_board,
            key=lambda x: (
                x.get('ev_glob') if x.get('ev_glob') is not None else -999.0,
                x.get('ev_liga') if x.get('ev_liga') is not None else -999.0,
                x.get('cr', 0.0)
            ),
            reverse=True
        )

        # Métricas superiores del subconjunto filtrado (KPIs Visuales)
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        total_val_bets = len(filtered_board)
        col_m1.metric("💎 Selecciones Activas", total_val_bets)
        
        doble_val_cnt = sum(1 for x in filtered_board if "DOBLE VALOR" in x.get('sello', ''))
        col_m2.metric("🔥 Doble Valor (Glo & Lig)", doble_val_cnt)
        
        avg_cr = (sum(x['cr'] for x in filtered_board) / total_val_bets) if total_val_bets > 0 else 0.0
        col_m3.metric("🎯 Cuota Real Promedio", f"@ {avg_cr:.2f}" if total_val_bets > 0 else "-")
        
        valid_evs = [x['ev_glob'] for x in filtered_board if x.get('ev_glob') is not None]
        if valid_evs:
            best_bet = filtered_board[0]
            col_m4.metric("🚀 Máximo EV (+EV Líder)", f"{best_bet['ev_glob']:+.1%}", f"CR @ {best_bet['cr']:.2f}")
        else:
            col_m4.metric("🚀 Máximo EV (+EV Líder)", "-", "Sin datos EV")

        st.caption("⚡ **Ordenación activa:** Selecciones ordenadas estrictamente de **mayor a menor Valor Esperado (+EV)**.")
        st.markdown("---")

        # Gráficos de distribución si hay múltiples selecciones
        if len(filtered_board) >= 2:
            with st.expander("📊 Gráficos de Distribución de Valor", expanded=False):
                c_ch1, c_ch2 = st.columns(2)
                cat_counts = pd.Series([x['mercado'] for x in filtered_board]).value_counts()
                c_ch1.markdown("**Distribución por Categoría de Mercado:**")
                c_ch1.bar_chart(cat_counts)
                
                match_counts = pd.Series([x['partido'] for x in filtered_board]).value_counts()
                c_ch2.markdown("**Distribución por Partido:**")
                c_ch2.bar_chart(match_counts)

        # -------------------------------------------------------------
        # 1. MODO TARJETAS VISUALES
        # -------------------------------------------------------------
        if view_mode == "🎴 Tarjetas Visuales":
            card_cols = st.columns(2)
            for idx, b in enumerate(filtered_board):
                target_col = card_cols[idx % 2]
                with target_col:
                    with st.container(border=True):
                        # Cabecera de la tarjeta: Ranking + Partido + Sello de valor
                        rank_num = idx + 1
                        rank_icon = "🥇" if rank_num == 1 else ("🥈" if rank_num == 2 else ("🥉" if rank_num == 3 else f"#{rank_num}"))
                        head_c1, head_c2 = st.columns([1.8, 1.2])
                        head_c1.markdown(f"**{rank_icon}** ⚽ **{b.get('partido', 'Partido')}**  \n`{b.get('tipo', 'Línea')}`")
                        sello_val = b.get('sello', '')
                        if "DOBLE VALOR" in sello_val:
                            badge_color = "🔥 **DOBLE VALOR (+EV)**"
                        elif "VALOR LIGA" in sello_val:
                            badge_color = "🟢 **VALOR LIGA (+EV)**"
                        elif "VALOR GLOBAL" in sello_val:
                            badge_color = "🟡 **VALOR GLOBAL (+EV)**"
                        else:
                            badge_color = "⚠️ **SIN VALOR**"
                        head_c2.markdown(badge_color)

                        # Título de la Selección y Categoría
                        st.markdown(f"#### {b.get('seleccion', '')}")
                        st.caption(f"📁 **Mercado:** {b.get('mercado', '')}")

                        # Métricas Cuantitativas
                        m_col1, m_col2, m_col3 = st.columns(3)
                        cr_val = b.get('cr', 1.0)
                        be_g = b.get('be_glob', 1.0)
                        edge_val = (cr_val - be_g) if be_g else 0.0
                        m_col1.metric("Cuota Real (CR)", f"@ {cr_val:.2f}", f"Edge: {edge_val:+.2f}")
                        
                        hr_g = b.get('hr_glob', 0.0)
                        m_col2.metric("Hit Rate Global", f"{hr_g:.1f}%", f"BE @ {be_g:.2f}")

                        ev_g = b.get('ev_glob')
                        ev_g_txt = f"{ev_g:+.1%}" if ev_g is not None else "-"
                        m_col3.metric("EV Global", ev_g_txt, f"W={b.get('w_glob', 0)}/{b.get('n_glob', 0)}")

                        # Barra de progreso visual para el Hit Rate
                        st.progress(min(1.0, max(0.0, hr_g / 100.0)), text=f"Acierto Global: {hr_g:.1f}% ({b.get('w_glob', 0)}/{b.get('n_glob', 0)} aciertos)")

                        # Detalle de Liga si existe
                        if b.get('n_liga', 0) > 0 and b.get('hr_liga') is not None:
                            ev_l = b.get('ev_liga')
                            ev_l_txt = f"{ev_l:+.1%}" if ev_l is not None else "-"
                            st.info(f"🏟️ **Datos Liga:** Hit Rate **{b.get('hr_liga'):.1f}%** (W={b.get('w_liga', 0)}/{b.get('n_liga', 0)} | BE @ {b.get('be_liga'):.2f} | EV Liga: **{ev_l_txt}**)")

                        # Botón de eliminación directa
                        act_c1, act_c2 = st.columns([3, 1])
                        if act_c2.button("🗑️ Eliminar", key=f"del_card_item_{idx}"):
                            current_board = [x for x in current_board if not (x.get('partido') == b.get('partido') and x.get('seleccion') == b.get('seleccion'))]
                            save_value_board(current_board)
                            st.toast(f"Selección eliminada: {b.get('seleccion')}")
                            st.rerun()

        # -------------------------------------------------------------
        # 2. MODO TABLA INTERACTIVA PRO (DATAFRAME)
        # -------------------------------------------------------------
        else:
            df_rows = []
            for idx, b in enumerate(filtered_board, 1):
                rank_str = f"🥇 #1" if idx == 1 else (f"🥈 #2" if idx == 2 else (f"🥉 #3" if idx == 3 else f"#{idx}"))
                df_rows.append({
                    'Ranking': rank_str,
                    'Partido': b.get('partido', 'General'),
                    'Selección': b.get('seleccion', ''),
                    'Tipo': b.get('tipo', ''),
                    'Mercado': b.get('mercado', ''),
                    'Cuota Real': float(b.get('cr', 1.0)),
                    'Hit Rate Global': float(b.get('hr_glob', 0.0)),
                    'Break-Even Global': float(b.get('be_glob', 1.0)) if b.get('be_glob') else None,
                    'EV Global': float(b.get('ev_glob', 0.0)) if b.get('ev_glob') is not None else None,
                    'Hit Rate Liga': float(b.get('hr_liga')) if b.get('hr_liga') is not None else None,
                    'Break-Even Liga': float(b.get('be_liga')) if b.get('be_liga') is not None else None,
                    'EV Liga': float(b.get('ev_liga')) if b.get('ev_liga') is not None else None,
                    'Sello Diagnóstico': b.get('sello', '')
                })

            st.dataframe(
                pd.DataFrame(df_rows),
                use_container_width=True,
                column_config={
                    "Ranking": st.column_config.TextColumn("Ranking EV"),
                    "Hit Rate Global": st.column_config.ProgressColumn(
                        "Hit Rate Global",
                        help="Porcentaje empírico de acierto en el historial completo",
                        format="%.1f%%",
                        min_value=0,
                        max_value=100
                    ),
                    "Hit Rate Liga": st.column_config.ProgressColumn(
                        "Hit Rate Liga",
                        help="Porcentaje empírico de acierto en la liga del partido",
                        format="%.1f%%",
                        min_value=0,
                        max_value=100
                    ),
                    "Cuota Real": st.column_config.NumberColumn(
                        "Cuota Real",
                        format="@ %.2f"
                    ),
                    "Break-Even Global": st.column_config.NumberColumn(
                        "Break-Even Global",
                        format="@ %.2f"
                    ),
                    "Break-Even Liga": st.column_config.NumberColumn(
                        "Break-Even Liga",
                        format="@ %.2f"
                    ),
                    "EV Global": st.column_config.NumberColumn(
                        "EV Global",
                        format="%+.2f"
                    ),
                    "EV Liga": st.column_config.NumberColumn(
                        "EV Liga",
                        format="%+.2f"
                    ),
                    "Sello Diagnóstico": st.column_config.TextColumn("Sello de Valor")
                },
                hide_index=True
            )

        # Vista segmentada por partido cuando se tiene la vista general
        if selected_match.startswith("Todos") and len(all_matches) > 1:
            st.markdown("#### 📂 Desglose Resumido por Partido")
            for m_name in all_matches:
                sub_m = [x for x in current_board if x.get('partido') == m_name]
                sub_m = sorted(
                    sub_m,
                    key=lambda x: (
                        x.get('ev_glob') if x.get('ev_glob') is not None else -999.0,
                        x.get('ev_liga') if x.get('ev_liga') is not None else -999.0,
                        x.get('cr', 0.0)
                    ),
                    reverse=True
                )
                with st.expander(f"⚽ **{m_name}** — ({len(sub_m)} selecciones con valor)", expanded=False):
                    sub_rows = []
                    for idx_sm, b in enumerate(sub_m, 1):
                        hr_g_str = f"{b.get('hr_glob', 0.0)}% ({b.get('w_glob', 0)}/{b.get('n_glob', 0)})" if b.get('hr_glob') else "-"
                        hr_l_str = f"{b.get('hr_liga')}% ({b.get('w_liga', 0)}/{b.get('n_liga', 0)})" if b.get('n_liga', 0) > 0 and b.get('hr_liga') is not None else "-"
                        sub_rows.append({
                            '#': f"#{idx_sm}",
                            'Selección': b.get('seleccion', ''),
                            'Tipo': b.get('tipo', ''),
                            'Mercado': b.get('mercado', ''),
                            'CR': f"@ {b.get('cr', 1.0):.2f}",
                            'HR Global': hr_g_str,
                            'CJ Global': f"@{b.get('be_glob', 1.0):.2f}",
                            'EV Global': f"{b.get('ev_glob'):+.2f}" if b.get('ev_glob') is not None else "-",
                            'HR Liga': hr_l_str,
                            'CJ Liga': f"@{b.get('be_liga'):.2f}" if b.get('be_liga') else "-",
                            'EV Liga': f"{b.get('ev_liga'):+.2f}" if b.get('ev_liga') is not None else "-",
                            'Sello': b.get('sello', '')
                        })
                    st.dataframe(pd.DataFrame(sub_rows), use_container_width=True)

        # Acciones de gestión
        with st.expander("⚙️ Opciones de Gestión de la Tabla de Valor"):
            if all_matches:
                del_m_col1, del_m_col2 = st.columns([3, 1])
                match_to_del = del_m_col1.selectbox("Selecciona un partido para eliminar todas sus apuestas:", all_matches)
                if del_m_col2.button("🗑️ Eliminar Partido Completo"):
                    new_board = [x for x in current_board if x.get('partido') != match_to_del]
                    save_value_board(new_board)
                    st.toast(f"Partido eliminado: {match_to_del}")
                    st.rerun()

            del_c1, del_c2 = st.columns([3, 1])
            sel_options = [f"[{x.get('partido', 'General')}] {x['seleccion']}" for x in current_board]
            sel_to_del_label = del_c1.selectbox("Selecciona una apuesta individual para eliminarla:", sel_options)
            if del_c2.button("🗑️ Eliminar Selección"):
                idx_del = sel_options.index(sel_to_del_label)
                del current_board[idx_del]
                save_value_board(current_board)
                st.toast("Selección eliminada.")
                st.rerun()

            if st.button("🚨 Vaciar Tabla de Valor Completa", type="secondary"):
                save_value_board([])
                st.toast("Tabla de valor vaciada")
                st.rerun()
    else:
        with st.container(border=True):
            st.markdown("### 💎 La Tabla Maestra de Valor está vacía")
            st.write(
                "Esta tabla centraliza todas las oportunidades con **Valor Esperado positivo ($+EV$)** de tus partidos analizados. "
                "Cuando pegues una hoja de pronósticos en **⏱️ Tiempo 1 (Ex-Ante)**, el motor evaluará cada línea y añadirá automáticamente aquí las mejores opciones."
            )
            c_emp1, c_emp2 = st.columns([2, 1])
            with c_emp1:
                st.caption("¿Quieres ver cómo luce la tabla visual con datos de prueba?")
            with c_emp2:
                if st.button("✨ Cargar Selecciones de Demostración (+EV)", use_container_width=True):
                    sample_demo_board = [
                        make_value_entry(
                            partido="Levante vs Atlético de Madrid",
                            seleccion="Más de 2.5 Goles Totales",
                            tipo="Línea Base con Valor",
                            mercado="Goles - Más de (Overs)",
                            cr=1.53,
                            hr_glob=80.0,
                            be_glob=1.25,
                            n_glob=15,
                            w_glob=12,
                            hr_liga=50.0,
                            be_liga=2.0,
                            n_liga=4,
                            w_liga=2
                        ),
                        make_value_entry(
                            partido="Levante vs Atlético de Madrid",
                            seleccion="Manu Sánchez — Más de 1.5 Entradas / Tackles",
                            tipo="Descalado X-1",
                            mercado="Player - Entradas",
                            cr=1.83,
                            hr_glob=93.8,
                            be_glob=1.07,
                            n_glob=16,
                            w_glob=15,
                            hr_liga=100.0,
                            be_liga=1.00,
                            n_liga=5,
                            w_liga=5
                        ),
                        make_value_entry(
                            partido="Chelsea vs Manchester United",
                            seleccion="Cole Palmer — Más de 1.5 Faltas recibidas",
                            tipo="Base X",
                            mercado="Player - Faltas Recibidas",
                            cr=1.80,
                            hr_glob=85.0,
                            be_glob=1.18,
                            n_glob=20,
                            w_glob=17,
                            hr_liga=90.0,
                            be_liga=1.11,
                            n_liga=10,
                            w_liga=9
                        ),
                        make_value_entry(
                            partido="Bologna vs Mainz",
                            seleccion="Más de 2.5 Goles Totales",
                            tipo="Descalado X-1",
                            mercado="Goles - Más de (Overs)",
                            cr=1.90,
                            hr_glob=86.7,
                            be_glob=1.15,
                            n_glob=15,
                            w_glob=13,
                            hr_liga=80.0,
                            be_liga=1.25,
                            n_liga=5,
                            w_liga=4
                        )
                    ]
                    save_value_board(sample_demo_board)
                    st.toast("Selecciones de demostración cargadas")
                    st.rerun()

    # Formulario manual para añadir cualquier apuesta
    st.markdown("---")
    with st.expander("➕ Añadir Manualmente Cualquier Selección a la Tabla de Valor"):
        st.write("Introduce cualquier selección para calcular su EV y guardarla en la Tabla de Valor:")
        man_c0, man_c1, man_c2 = st.columns([1, 1, 1])
        man_partido = man_c0.text_input("Partido:", value=selected_match if ('selected_match' in locals() and not selected_match.startswith("Todos")) else (all_matches[0] if all_matches else "Partido General"))
        man_sel_name = man_c1.text_input("Nombre de la Selección (ej: 'Más de 3.5 Tarjetas Amarillas Totales'):")
        man_cat = man_c2.selectbox(
            "Categoría de Mercado:",
            [
                "Partido - Tarjetas Totales",
                "Partido - Córners Totales (Overs)",
                "Partido - Tiros Totales (Overs)",
                "Partido - Tiros a Puerta Totales",
                "Goles - Más de (Overs)",
                "Goles - Ambos Marcan (BTTS)",
                "Resultado - 1X2 Directo",
                "Resultado - Doble Oportunidad",
                "Player - Tiros Totales",
                "Player - Tiros a Puerta (TAP)",
                "Player - Entradas",
                "Player - Faltas Cometidas",
                "Player - Faltas Recibidas",
                "Player - Tarjetas"
            ]
        )
        man_c3, man_c4, man_c5 = st.columns(3)
        man_tipo = man_c3.selectbox("Tipo de Línea:", ["Línea Base X", "Descalado X-1", "Descalado X-2", "Under X+1", "Under X+2", "Under X+3", "Personalizada"])
        man_cr = man_c4.number_input("Cuota Real en tu Casa:", min_value=1.01, max_value=50.0, value=1.50, step=0.01)
        man_cj_ref = man_c5.number_input("Cuota Justa de Referencia (opcional, defecto 1.50):", min_value=1.01, max_value=10.0, value=1.50, step=0.05)

        if st.button("➕ Calcular y Guardar en Tabla de Valor"):
            if man_sel_name.strip():
                # Evaluar empíricamente
                stats_g = engine.filter_records(category=man_cat, cj=man_cj_ref)
                st_glob = engine.compute_basic_stats(stats_g)
                # Liga
                t1_lg = st.session_state.get('t1_league', 'La Liga')
                stats_l = engine.filter_records(category=man_cat, cj=man_cj_ref, league=t1_lg)
                st_liga = engine.compute_basic_stats(stats_l)

                entry = make_value_entry(
                    partido=man_partido.strip(),
                    seleccion=man_sel_name.strip(),
                    tipo=man_tipo,
                    mercado=man_cat,
                    cr=man_cr,
                    hr_glob=st_glob['hr'],
                    be_glob=st_glob['be'],
                    n_glob=st_glob['n'],
                    w_glob=st_glob['w'],
                    hr_liga=st_liga['hr'] if st_liga['n'] > 0 else None,
                    be_liga=st_liga['be'] if st_liga['n'] > 0 else None,
                    n_liga=st_liga['n'],
                    w_liga=st_liga['w']
                )
                board = load_value_board()
                board = [x for x in board if not (x.get('partido') == entry['partido'] and x['seleccion'] == entry['seleccion'])]
                board.append(entry)
                save_value_board(board)
                st.toast(f"✅ Guardada [{man_partido}]: {entry['seleccion']} [@ {man_cr:.2f}]")
                st.rerun()

# -------------------------------------------------------------
# TAB 4: TIEMPO 2 (OPTIMIZACIÓN DE BALAS)
# -------------------------------------------------------------
with tab_t2:
    st.subheader("🎯 Tiempo 2: Optimización Combinatoria de 3 Balas")
    st.write("Genera las 3 Balas Definitivas con **0 solapamiento de selecciones** dentro del rango objetivo [@ 1.80 – @ 2.35].")

    current_board = load_value_board()
    use_board = False
    opt_board = current_board
    if current_board:
        all_matches_t2 = sorted(list(set(x.get('partido', 'Partido General') for x in current_board)))
        col_t2_1, col_t2_2 = st.columns([1, 1])
        use_board = col_t2_1.checkbox("Utilizar selecciones de la Tabla Maestra de Valor", value=True)
        sel_match_t2 = col_t2_2.selectbox("Partido a optimizar en Balas:", ["Todos los Partidos"] + all_matches_t2)
        if not sel_match_t2.startswith("Todos"):
            opt_board = [x for x in current_board if x.get('partido') == sel_match_t2]
        st.success(f"💎 Balas se construirán a partir de **{len(opt_board)} selecciones** ({sel_match_t2}).")

    desc_input = st.text_area(
        "Cuotas Adicionales (Shorthand o manual):",
        "julian 2 tiros 1.18, manu sanchez 2 entradas 1.28, julian alvarez recibe falta 1.36, over 1.5 goles 1.16, over 3.5 tarjetas 1.66, over 7.5 tap 1.28",
        height=80
    )

    col_min, col_max, col_opt_btn = st.columns([1, 1, 2])
    min_o = col_min.number_input("Cuota Mínima por Bala", value=1.80, step=0.05)
    max_o = col_max.number_input("Cuota Máxima por Bala", value=2.35, step=0.05)

    if col_opt_btn.button("🚀 Calcular 3 Balas Definitivas", type="primary"):
        legs = []
        if use_board and opt_board:
            for idx, item in enumerate(opt_board):
                pl = extract_player_name(item.get('seleccion', ''))
                leg_desc = f"[{item.get('partido', '')[:12]}] {item.get('seleccion', '')}" if (len(all_matches) > 1 and sel_match_t2.startswith("Todos")) else item.get('seleccion', '')
                legs.append(BulletLeg(
                    leg_id=f"L{idx+1}",
                    desc=leg_desc,
                    cr=item.get('cr', 1.0),
                    hr=item.get('hr_glob', 0.0),
                    be=item.get('be_glob', 1.0),
                    ev=item.get('ev_glob', 0.0) if item.get('ev_glob') is not None else 0.0,
                    category=item.get('mercado', ''),
                    player=pl
                ))
        else:
            # Pre-seed fallback candidates
            test_candidates = [
                ("Más de 2.5 Goles Totales", 1.53, 80.0, 1.25, 0.22, "Goles - Más de (Overs)", None),
                ("manu sanchez 2 entradas", 1.28, 89.0, 1.12, 0.14, "Player - Entradas", "Manu Sánchez"),
                ("Álex Baena — Más de 0.5 Entradas / Tackles", 1.36, 84.8, 1.18, 0.15, "Player - Entradas", "Álex Baena"),
                ("julian alvarez recibe falta", 1.36, 87.4, 1.14, 0.19, "Player - Faltas Recibidas", "Julián Álvarez"),
                ("Alejandro Grimaldo — Más de 0.5 Tiros a Puerta", 1.83, 57.9, 1.73, 0.06, "Player - Tiros a Puerta (TAP)", "Alejandro Grimaldo"),
                ("over 1.5 goles", 1.16, 83.3, 1.20, -0.03, "Goles - Más de (Overs)", None),
                ("Ifeanyi Ndukwe — Más de 0.5 Entradas / Tackles", 1.12, 84.8, 1.18, -0.05, "Player - Entradas", "Ifeanyi Ndukwe"),
                ("julian 2 tiros", 1.18, 85.9, 1.16, 0.01, "Player - Tiros Totales", "Julián Álvarez")
            ]
            for idx, (desc, cr, hr, be, ev, cat, pl) in enumerate(test_candidates):
                legs.append(BulletLeg(f"L{idx+1}", desc, cr, hr, be, ev, cat, pl))

        opt = BulletOptimizer(min_odds=min_o, max_odds=max_o, max_legs_per_bullet=2)
        cand_bullets = opt.build_candidate_bullets(legs)
        triplets = opt.optimize_triplets(cand_bullets, top_k=3)

        if triplets:
            for tr in triplets:
                st.markdown(f"### 🌟 {tr['estrategia']}")
                st.info(f"**EV Conjunto:** {tr['ev_total']:+.4f} | **Probabilidad >= 2 Aciertos:** {tr['prob_al_menos_2_aciertos']} | **Hit Rate Promedio:** {tr['hr_promedio']}")
                
                b_cols = st.columns(3)
                for i, b_name in enumerate(['bala_1', 'bala_2', 'bala_3']):
                    b = tr[b_name]
                    with b_cols[i]:
                        st.markdown(f"**Bala #{i+1} ({b['tipo']})**")
                        st.metric("Cuota Real", f"@ {b['cr']:.2f}", f"HR {b['hr']}%")
                        st.caption(f"Break-Even: @ {b['be']:.2f} | EV: {b['ev']:+.4f}")
                        for leg in b['legs']:
                            st.write(f"- **{leg['desc']}** [@ {leg['cr']:.2f}]")
                st.markdown("---")
        else:
            st.warning("No se encontraron tríos con 0 solapamiento en el rango exacto. Ajusta el rango de cuotas o agrega más selecciones a la Tabla Maestra.")

# -------------------------------------------------------------
# TAB 5: EXPLORADOR DE LÍNEAS
# -------------------------------------------------------------
with tab_explore:
    st.subheader("Explorador de Espectro Completo de Líneas (X+k)")
    st.write("Explora cualquier mercado sin sesgo para conocer el Hit Rate empírico en desplazamientos de X-6 a X+6 y Unders.")

    cat_choice = st.selectbox(
        "Selecciona la Categoría de Mercado:",
        [
            "Player - Tiros Totales",
            "Player - Tiros a Puerta (TAP)",
            "Player - Entradas",
            "Player - Faltas Cometidas",
            "Player - Faltas Recibidas",
            "Player - Tarjetas",
            "Partido - Tiros Totales (Overs)",
            "Partido - Tiros a Puerta Totales",
            "Partido - Córners Totales (Overs)",
            "Partido - Tarjetas Totales",
            "Equipo - Tiros Totales",
            "Equipo - Tiros a Puerta",
            "Equipo - Córners de un Equipo",
            "Goles - Más de (Overs)",
            "Goles - Ambos Marcan (BTTS)",
            "Resultado - Doble Oportunidad"
        ]
    )

    col_cj, col_k = st.columns(2)
    cj_filter = col_cj.selectbox("Franja Cuota Justa", ["Todas las Franjas", "CJ <= 1.40", "CJ 1.41 - 1.60", "CJ 1.61 - 1.80", "CJ > 1.80"])
    cj_val = 1.30 if "1.40" in cj_filter else (1.50 if "1.60" in cj_filter else (1.70 if "1.80" in cj_filter and ">" not in cj_filter else (1.90 if ">" in cj_filter else None)))

    spectrum = engine.compute_all_offsets_spectrum(category=cat_choice, cj=cj_val, k_min=-6, k_max=6)
    df_spec = pd.DataFrame([{
        'Línea / Desplazamiento': s['label'],
        'Muestra (N)': s['n'],
        'Aciertos (W)': s['w'],
        'Hit Rate (%)': f"{s['hr']}%",
        'Cuota Break-Even': f"@ {s['be']:.2f}"
    } for s in spectrum])
    
    st.dataframe(df_spec, use_container_width=True)

    st.subheader("Distribución Estadística de Márgenes")
    m_dist = engine.compute_margin_distribution(category=cat_choice, cj=cj_val)
    if m_dist['n'] > 0:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Muestra Márgenes", m_dist['n'])
        c2.metric("Margen Medio", f"{m_dist['mean']:+}")
        c3.metric("Desv. Estándar", m_dist['std'])
        c4.metric("Mediana", f"{m_dist['median']:+}")
        
        freq_df = pd.DataFrame(list(m_dist['frequencies'].items()), columns=['Margen', 'Frecuencia']).set_index('Margen')
        st.bar_chart(freq_df)

# -------------------------------------------------------------
# TAB 6: CIERRE DE PARTIDOS (HISTORIAL)
# -------------------------------------------------------------
with tab_fill:
    st.subheader("📝 Cierre y Resolución de Partidos Pendientes en Historial")
    st.write(
        "Herramienta integral para cerrar pronósticos jugados. "
        "Permite registrar veredictos (**SÍ / NO / ANULADA**), ajustar Cuotas Reales y Márgenes directamente "
        "en `historial_prompt.txt` con guardado transaccional y copia de seguridad automática."
    )

    all_matches_info = hist_updater.get_matches_info()
    pending_matches = [m for m in all_matches_info if m['pending_count'] > 0]
    total_pending_bets = sum(m['pending_count'] for m in pending_matches)

    # 1. Tarjetas KPI superiores
    c_kpi1, c_kpi2, c_kpi3, c_kpi4 = st.columns(4)
    c_kpi1.metric("Partidos Pendientes", len(pending_matches))
    c_kpi2.metric("Pronósticos por Resolver", total_pending_bets)
    c_kpi3.metric("Muestra Concluida", len(engine.settled_records))
    c_kpi4.metric("Hit Rate Global Actual", f"{engine.compute_basic_stats(engine.settled_records)['hr']}%")

    st.markdown("---")

    # 2. Selector de partido
    col_sel_p, col_toggle = st.columns([3, 1])
    show_all = col_toggle.checkbox("Mostrar también concluidos", value=False, help="Actívalo si deseas corregir o editar veredictos de partidos ya finalizados previamente.")

    eligible = all_matches_info if show_all else pending_matches
    if not eligible:
        st.success("🎉 **¡Excelente! No hay ningún pronóstico pendiente en el historial.** Todos los partidos jugados están 100% resueltos.")
    else:
        match_options = {
            f"#{m['match_id']:02d} — {m['match_name']} ({m['league']}) — ⏳ {m['pending_count']} pendientes / {m['total_lines']} totales": m
            for m in eligible
        }
        sel_label = col_sel_p.selectbox("Selecciona Partido a Resolver / Editar:", list(match_options.keys()), key="fill_sel_match_box")
        sel_m = match_options[sel_label]

        st.markdown(f"#### ⚽ #{sel_m['match_id']:02d}: {sel_m['match_name']} — Liga: `{sel_m['league']}`")
        st.caption(f"Total pronósticos: **{sel_m['total_lines']}** | Resueltos: **{sel_m['settled_count']}** | Pendientes: **{sel_m['pending_count']}**")

        tab_wizard, tab_sub_grid, tab_sub_text = st.tabs([
            "🧙‍♂️ Asistente Inteligente por Selección (Ingreso de Dato Real)",
            "⚡ Editor Rápido por Tabla (st.data_editor)",
            "📄 Pegar / Editar Bloque de Texto Crudo"
        ])

        with tab_wizard:
            mid = sel_m['match_id']
            st.info(
                "💡 **Asistente Inteligente**: Ingresa el dato estadístico real conseguido en el partido "
                "(ej. *3 goles*, *4 entradas*, *11 córners*). El motor calculará automáticamente si la selección "
                "fue acertada o no y su margen numérico exacto (+/- N). Para mercados directos (ej. *1X2*, *Doble Oportunidad*, *Ambos Marcan*), "
                "indica si se cumplió o si fue anulada."
            )

            # 1. Inicialización limpia de estados para este partido si no existían
            init_key = f"wiz_init_done_{mid}"
            if init_key not in st.session_state:
                for idx, r in enumerate(sel_m['records']):
                    info = analyze_selection_type(r['seleccion'], r['mercado'])
                    ver = r.get('veredicto')
                    mar = r.get('margen')
                    cr = r.get('cr')
                    if cr is not None and f"wiz_cr_{mid}_{idx}" not in st.session_state:
                        st.session_state[f"wiz_cr_{mid}_{idx}"] = float(cr)
                    if info['is_numerical']:
                        if ver in ['ANULADA', 'VOID', 'PUSH']:
                            st.session_state[f"wiz_anu_{mid}_{idx}"] = True
                        elif ver in ['SI', 'NO'] and mar is not None:
                            target = info['target_or_limit']
                            deduced_stat = max(0, target + mar)
                            st.session_state[f"wiz_stat_{mid}_{idx}"] = int(deduced_stat)
                    else:
                        if ver == 'SI':
                            st.session_state[f"wiz_bin_{mid}_{idx}"] = "🟢 SÍ (Acertada)"
                            st.session_state[f"wiz_mar_{mid}_{idx}"] = int(mar) if mar is not None else 0
                        elif ver == 'NO':
                            st.session_state[f"wiz_bin_{mid}_{idx}"] = "🔴 NO (Fallada)"
                            st.session_state[f"wiz_mar_{mid}_{idx}"] = int(mar) if mar is not None else -1
                        elif ver in ['ANULADA', 'VOID', 'PUSH']:
                            st.session_state[f"wiz_bin_{mid}_{idx}"] = "🟡 ANULADA"
                            st.session_state[f"wiz_mar_{mid}_{idx}"] = None
                        else:
                            st.session_state[f"wiz_bin_{mid}_{idx}"] = "[ ] Pendiente"
                            st.session_state[f"wiz_mar_{mid}_{idx}"] = None
                st.session_state[init_key] = True

            # Callbacks de Streamlit para mutaciones seguras previas a la instanciación de widgets
            def cb_apply_match_score(match_id, ht, at, records):
                hg = st.session_state.get(f"match_hgoals_{match_id}")
                ag = st.session_state.get(f"match_agoals_{match_id}")
                if hg is not None and ag is not None:
                    for l_idx, rec in enumerate(records):
                        res_sc = resolve_from_match_score(rec['seleccion'], rec['mercado'], ht, at, int(hg), int(ag))
                        if res_sc:
                            v_sc, m_sc, exp_sc = res_sc
                            inf_sc = analyze_selection_type(rec['seleccion'], rec['mercado'])
                            if inf_sc['is_numerical']:
                                st.session_state[f"wiz_stat_{match_id}_{l_idx}"] = int(hg + ag)
                                st.session_state[f"wiz_anu_{match_id}_{l_idx}"] = False
                            else:
                                st.session_state[f"wiz_bin_{match_id}_{l_idx}"] = "🟢 SÍ (Acertada)" if v_sc == 'SI' else ("🔴 NO (Fallada)" if v_sc == 'NO' else "🟡 ANULADA")
                                st.session_state[f"wiz_mar_{match_id}_{l_idx}"] = int(m_sc)
                                st.session_state[f"wiz_exp_{match_id}_{l_idx}"] = exp_sc

            def cb_apply_batch_player(match_id, col_idx, lines):
                b_val = st.session_state.get(f"batch_val_{match_id}_{col_idx}")
                if b_val is not None:
                    for l_idx, _, _ in lines:
                        st.session_state[f"wiz_stat_{match_id}_{l_idx}"] = int(b_val)
                        st.session_state[f"wiz_anu_{match_id}_{l_idx}"] = False

            def cb_clear_all_wiz(match_id, count):
                for idx_c in range(count):
                    st.session_state[f"wiz_stat_{match_id}_{idx_c}"] = None
                    st.session_state[f"wiz_anu_{match_id}_{idx_c}"] = False
                    st.session_state[f"wiz_bin_{match_id}_{idx_c}"] = "[ ] Pendiente"
                    st.session_state[f"wiz_mar_{match_id}_{idx_c}"] = 0
                    st.session_state[f"wiz_exp_{match_id}_{idx_c}"] = ""

            def cb_calc_single_score(match_id, idx_c, sel, mer, ht, at):
                hl = st.session_state.get(f"card_hgoals_{match_id}_{idx_c}")
                aw = st.session_state.get(f"card_agoals_{match_id}_{idx_c}")
                if hl is not None and aw is not None:
                    r_sc = resolve_from_match_score(sel, mer, ht, at, int(hl), int(aw))
                    if r_sc:
                        v_c, m_c, e_c = r_sc
                        st.session_state[f"wiz_bin_{match_id}_{idx_c}"] = "🟢 SÍ (Acertada)" if v_c == 'SI' else ("🔴 NO (Fallada)" if v_c == 'NO' else "🟡 ANULADA")
                        st.session_state[f"wiz_mar_{match_id}_{idx_c}"] = int(m_c)
                        st.session_state[f"wiz_exp_{match_id}_{idx_c}"] = e_c

            # Marcador Final del Encuentro (Cálculo Automático de Resultados y Goles)
            home_team, away_team = parse_match_teams(sel_m['match_name'])
            with st.container(border=True):
                st.markdown(f"##### ⚽ Marcador Final del Partido: **{home_team}** vs. **{away_team}**")
                st.caption("Ingresa el resultado final del partido para calcular automáticamente todas las selecciones de resultado (1X2, Doble Oportunidad, Hándicaps, Ambos Marcan y Total de Goles) junto con su margen exacto.")
                c_sc1, c_sc2, c_sc3, c_sc4 = st.columns([2, 2, 2, 2])
                with c_sc1:
                    h_goals = st.number_input(f"Goles {home_team}:", min_value=0, max_value=20, step=1, value=st.session_state.get(f"match_hgoals_{mid}"), key=f"match_hgoals_{mid}")
                with c_sc2:
                    a_goals = st.number_input(f"Goles {away_team}:", min_value=0, max_value=20, step=1, value=st.session_state.get(f"match_agoals_{mid}"), key=f"match_agoals_{mid}")
                with c_sc3:
                    st.write("")
                    st.write("")
                    st.button(
                        "⚡ Aplicar Marcador al Partido",
                        type="secondary",
                        use_container_width=True,
                        key=f"btn_apply_score_{mid}",
                        on_click=cb_apply_match_score,
                        args=(mid, home_team, away_team, sel_m['records'])
                    )
                with c_sc4:
                    st.write("")
                    st.write("")
                    if st.session_state.get(f"match_hgoals_{mid}") is not None and st.session_state.get(f"match_agoals_{mid}") is not None:
                        st.success(f"Marcador fijado: **{st.session_state.get(f'match_hgoals_{mid}')} - {st.session_state.get(f'match_agoals_{mid}')}**")

            # 2. Relleno Rápido Simultáneo por Sujeto / Métrica (Expander)
            subject_groups = {}
            for idx, r in enumerate(sel_m['records']):
                info = analyze_selection_type(r['seleccion'], r['mercado'])
                if info['is_numerical']:
                    s_label = info['subject'] if info['subject'] else "Partido Completo"
                    u_label = info['unit']
                    grp_key = (s_label, u_label)
                    if grp_key not in subject_groups:
                        subject_groups[grp_key] = []
                    subject_groups[grp_key].append((idx, r, info))

            multi_groups = {k: v for k, v in subject_groups.items() if len(v) >= 2}
            if multi_groups:
                with st.expander("⚡ Relleno Rápido Simultáneo por Jugador / Métrica (Ahorra tiempo si una misma estadística aplica a varias líneas)", expanded=False):
                    st.caption("Si un jugador o estadística tiene varias líneas alternativas (ej. Base X y Descalados X-1), escribe aquí el dato real una sola vez para resolver todas sus líneas a la vez.")
                    b_cols = st.columns(min(len(multi_groups), 3))
                    for col_i, ((grp_subj, grp_unit), grp_lines) in enumerate(multi_groups.items()):
                        curr_col = b_cols[col_i % len(b_cols)]
                        with curr_col:
                            st.markdown(f"**{grp_subj}** (`{grp_unit}` — {len(grp_lines)} líneas)")
                            b_val = st.number_input(f"Dato real {grp_unit}:", min_value=0, max_value=100, step=1, value=None, key=f"batch_val_{mid}_{col_i}")
                            st.button(
                                f"⚡ Aplicar a las {len(grp_lines)} líneas",
                                key=f"btn_batch_{mid}_{col_i}",
                                use_container_width=True,
                                on_click=cb_apply_batch_player,
                                args=(mid, col_i, grp_lines)
                            )

            # 3. Resumen en vivo de estado y botón guardar superior
            curr_si = 0
            curr_no = 0
            curr_anu = 0
            curr_pend = 0
            for idx, r in enumerate(sel_m['records']):
                info = analyze_selection_type(r['seleccion'], r['mercado'])
                if info['is_numerical']:
                    if st.session_state.get(f"wiz_anu_{mid}_{idx}", False):
                        curr_anu += 1
                    elif st.session_state.get(f"wiz_stat_{mid}_{idx}") is not None:
                        s_val = st.session_state.get(f"wiz_stat_{mid}_{idx}")
                        v, _, _ = auto_resolve_selection(r['seleccion'], r['mercado'], s_val)
                        if v == 'SI':
                            curr_si += 1
                        elif v == 'NO':
                            curr_no += 1
                    else:
                        curr_pend += 1
                else:
                    b_choice = st.session_state.get(f"wiz_bin_{mid}_{idx}", "[ ] Pendiente")
                    if "SÍ" in b_choice or "SI" in b_choice:
                        curr_si += 1
                    elif "NO" in b_choice:
                        curr_no += 1
                    elif "ANULADA" in b_choice:
                        curr_anu += 1
                    else:
                        curr_pend += 1

            tot_decided = curr_si + curr_no
            proj_hr_wiz = round((curr_si / tot_decided * 100), 1) if tot_decided > 0 else 0.0

            c_head1, c_head2 = st.columns([3, 1])
            with c_head1:
                st.markdown(
                    f"**Progreso:** 🟢 **{curr_si} SÍ** &nbsp;|&nbsp; 🔴 **{curr_no} NO** &nbsp;|&nbsp; "
                    f"🟡 **{curr_anu} Anuladas** &nbsp;|&nbsp; ⏳ **{curr_pend} Pendientes** "
                    f"&nbsp;—&nbsp; Hit Rate Proyectado: **{proj_hr_wiz}%**"
                )
            with c_head2:
                btn_top_save = st.button("💾 Guardar Resultados", type="primary", use_container_width=True, key=f"btn_save_top_{mid}")

            # 4. Filtro de visualización
            f_col1, f_col2 = st.columns([3, 1])
            filter_mode = f_col1.radio(
                "Filtrar lista de selecciones:",
                ["Todas las selecciones", "Solo Pendientes", "Solo Estadísticas Numéricas", "Solo Mercados Directos"],
                horizontal=True,
                key=f"wiz_filter_mode_{mid}"
            )
            f_col2.button(
                "🧹 Limpiar Todo",
                key=f"btn_clear_wiz_{mid}",
                on_click=cb_clear_all_wiz,
                args=(mid, len(sel_m['records'])),
                help="Reinicia todos los campos de este partido al estado pendiente."
            )

            # 5. Guardado de datos
            def save_wizard_data():
                upds = {}
                for idx, r in enumerate(sel_m['records']):
                    inf = analyze_selection_type(r['seleccion'], r['mercado'])
                    cr_in = st.session_state.get(f"wiz_cr_{mid}_{idx}")
                    cr_save = float(cr_in) if cr_in is not None and cr_in > 0 else r.get('cr')
                    
                    if inf['is_numerical']:
                        is_an = st.session_state.get(f"wiz_anu_{mid}_{idx}", False)
                        s_in = st.session_state.get(f"wiz_stat_{mid}_{idx}")
                        if is_an:
                            upds[idx] = {'veredicto': 'ANULADA', 'margen': None, 'cr': cr_save}
                        elif s_in is not None:
                            v, m, _ = auto_resolve_selection(r['seleccion'], r['mercado'], s_in)
                            upds[idx] = {'veredicto': v, 'margen': m, 'cr': cr_save}
                        else:
                            upds[idx] = {'veredicto': r.get('veredicto', ''), 'margen': r.get('margen'), 'cr': cr_save}
                    else:
                        b_val = st.session_state.get(f"wiz_bin_{mid}_{idx}", "[ ] Pendiente")
                        mar_direct = st.session_state.get(f"wiz_mar_{mid}_{idx}")
                        if "SÍ" in b_val or "SI" in b_val:
                            final_mar = int(mar_direct) if mar_direct is not None else 0
                            upds[idx] = {'veredicto': 'SI', 'margen': final_mar, 'cr': cr_save}
                        elif "NO" in b_val:
                            final_mar = int(mar_direct) if mar_direct is not None else -1
                            upds[idx] = {'veredicto': 'NO', 'margen': final_mar, 'cr': cr_save}
                        elif "ANULADA" in b_val:
                            upds[idx] = {'veredicto': 'ANULADA', 'margen': None, 'cr': cr_save}
                        else:
                            upds[idx] = {'veredicto': r.get('veredicto', ''), 'margen': r.get('margen'), 'cr': cr_save}
                
                try:
                    hist_updater.update_match_records(mid, upds, backup=True)
                    st.cache_resource.clear()
                    for k in list(st.session_state.keys()):
                        if k.startswith(f"wiz_") or k.startswith("fill_editor_df_") or k.startswith("editor_table_") or k.startswith("fill_loaded_mid_"):
                            del st.session_state[k]
                    st.success(f"✅ ¡Resultados de '{sel_m['match_name']}' guardados exitosamente en historial_prompt.txt!")
                    st.toast(f"✅ Historial actualizado: {sel_m['match_name']}")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error al guardar veredictos: {ex}")

            if btn_top_save:
                save_wizard_data()

            displayed_count = 0
            for idx, r in enumerate(sel_m['records']):
                info = analyze_selection_type(r['seleccion'], r['mercado'])
                is_num = info['is_numerical']
                
                is_cur_pend = False
                if is_num:
                    is_cur_pend = (not st.session_state.get(f"wiz_anu_{mid}_{idx}", False) and st.session_state.get(f"wiz_stat_{mid}_{idx}") is None)
                else:
                    is_cur_pend = (st.session_state.get(f"wiz_bin_{mid}_{idx}", "[ ] Pendiente") == "[ ] Pendiente")

                if filter_mode == "Solo Pendientes" and not is_cur_pend:
                    continue
                if filter_mode == "Solo Estadísticas Numéricas" and not is_num:
                    continue
                if filter_mode == "Solo Mercados Directos" and is_num:
                    continue

                displayed_count += 1
                with st.container(border=True):
                    row_h1, row_h2 = st.columns([3, 1])
                    with row_h1:
                        st.markdown(f"##### #{idx+1:02d} | `{r['mercado']}` — **{r['seleccion']}**")
                        cj_txt = f"@ {r['cj']:.2f}" if r.get('cj') else "-"
                        st.caption(f"Cuota Mínima / Justa: **{cj_txt}** &nbsp;|&nbsp; Regla: `{info['cond_text']}`")
                    with row_h2:
                        cr_input = st.number_input(
                            "Cuota Real (opcional):",
                            min_value=1.01,
                            max_value=50.0,
                            step=0.01,
                            format="%.2f",
                            value=float(r['cr']) if r.get('cr') is not None else None,
                            key=f"wiz_cr_{mid}_{idx}"
                        )

                    c_input, c_feedback = st.columns([3, 2])

                    if is_num:
                        with c_input:
                            st.markdown(f"❓ **{info['question']}**")
                            sub_c1, sub_c2 = st.columns([2, 1])
                            with sub_c1:
                                stat_entered = st.number_input(
                                    f"Dato real obtenido ({info['unit']}):",
                                    min_value=0,
                                    max_value=100,
                                    step=1,
                                    value=st.session_state.get(f"wiz_stat_{mid}_{idx}"),
                                    key=f"wiz_stat_{mid}_{idx}"
                                )
                            with sub_c2:
                                st.write("")
                                st.checkbox(
                                    "🟡 Anulada (no jugó)",
                                    value=st.session_state.get(f"wiz_anu_{mid}_{idx}", False),
                                    key=f"wiz_anu_{mid}_{idx}",
                                    help="Márcalo si el jugador no llegó a disputar minutos o el mercado fue cancelado."
                                )

                        with c_feedback:
                            is_anu_checked = st.session_state.get(f"wiz_anu_{mid}_{idx}", False)
                            if is_anu_checked:
                                st.warning("🟡 **ANULADA (PUSH / VOID)**\n\nMargen: `[ ]` (No computa para Hit Rate)")
                            elif stat_entered is not None:
                                v_res, m_res, exp_res = auto_resolve_selection(r['seleccion'], r['mercado'], stat_entered)
                                if v_res == 'SI':
                                    st.success(f"**✅ ACERTADA (SÍ)** &nbsp;|&nbsp; Margen: **{m_res:+d}**\n\n{exp_res}")
                                else:
                                    st.error(f"**❌ FALLADA (NO)** &nbsp;|&nbsp; Margen: **{m_res:+d}**\n\n{exp_res}")
                            else:
                                st.info("⏳ **Ingresa el número real obtenido** para calcular automáticamente veredicto y margen.")

                    else:
                        with c_input:
                            st.markdown(f"❓ **{info['question']}**")
                            sub_c1, sub_c2 = st.columns([3, 2])
                            with sub_c1:
                                bin_choice = st.radio(
                                    "Veredicto:",
                                    options=["[ ] Pendiente", "🟢 SÍ (Acertada)", "🔴 NO (Fallada)", "🟡 ANULADA"],
                                    horizontal=True,
                                    key=f"wiz_bin_{mid}_{idx}"
                                )
                            with sub_c2:
                                cur_mar_val = st.session_state.get(f"wiz_mar_{mid}_{idx}")
                                if cur_mar_val is None:
                                    if "SÍ" in bin_choice or "SI" in bin_choice:
                                        cur_mar_val = 0
                                    elif "NO" in bin_choice:
                                        cur_mar_val = -1
                                    else:
                                        cur_mar_val = 0
                                mar_entered = st.number_input(
                                    "Margen exacto (+/-):",
                                    step=1,
                                    value=int(cur_mar_val),
                                    key=f"wiz_mar_{mid}_{idx}",
                                    help="Margen numérico con el que se resolvió el pronóstico. Ej. +1 si ganó por 1 gol, 0 en empate cubierto, -2 si perdió por 2 goles."
                                )

                            if info.get('is_result_market'):
                                with st.expander("⚽ O calcular margen a partir del marcador de este partido", expanded=False):
                                    c_sc_row1, c_sc_row2, c_sc_row3 = st.columns([2, 2, 2])
                                    def_h = st.session_state.get(f"match_hgoals_{mid}")
                                    def_a = st.session_state.get(f"match_agoals_{mid}")
                                    h_local_sc = c_sc_row1.number_input(f"Goles {home_team}:", min_value=0, max_value=20, step=1, value=def_h, key=f"card_hgoals_{mid}_{idx}")
                                    a_away_sc = c_sc_row2.number_input(f"Goles {away_team}:", min_value=0, max_value=20, step=1, value=def_a, key=f"card_agoals_{mid}_{idx}")
                                    c_sc_row3.write("")
                                    c_sc_row3.write("")
                                    c_sc_row3.button(
                                        "⚡ Calcular",
                                        key=f"btn_calc_card_sc_{mid}_{idx}",
                                        on_click=cb_calc_single_score,
                                        args=(mid, idx, r['seleccion'], r['mercado'], home_team, away_team),
                                        use_container_width=True
                                    )

                        with c_feedback:
                            exp_saved = st.session_state.get(f"wiz_exp_{mid}_{idx}")
                            eff_mar = st.session_state.get(f"wiz_mar_{mid}_{idx}")
                            if eff_mar is None:
                                if "SÍ" in bin_choice or "SI" in bin_choice:
                                    eff_mar = 0
                                elif "NO" in bin_choice:
                                    eff_mar = -1

                            if "SÍ" in bin_choice or "SI" in bin_choice:
                                mar_str = f"{eff_mar:+d}" if eff_mar is not None else "0"
                                desc_txt = f"\n\n_{exp_saved}_" if exp_saved else "\n\nPronóstico cumplido."
                                st.success(f"**✅ ACERTADA (SÍ)** &nbsp;|&nbsp; Margen: **{mar_str}**{desc_txt}")
                            elif "NO" in bin_choice:
                                mar_str = f"{eff_mar:+d}" if eff_mar is not None else "-1"
                                desc_txt = f"\n\n_{exp_saved}_" if exp_saved else "\n\nPronóstico no cumplido."
                                st.error(f"**❌ FALLADA (NO)** &nbsp;|&nbsp; Margen: **{mar_str}**{desc_txt}")
                            elif "ANULADA" in bin_choice:
                                st.warning("🟡 **ANULADA (PUSH / VOID)**\n\nMargen: `[ ]` (No computa)")
                            else:
                                st.info("⏳ **Pendiente de selección o ingreso de margen / resultado.**")

            if displayed_count == 0:
                st.info("No hay selecciones que coincidan con el filtro seleccionado.")

            st.markdown("---")
            c_bot1, c_bot2 = st.columns([2, 1])
            with c_bot1:
                st.caption("Al guardar, el archivo `historial_prompt.txt` se actualiza de forma transaccional creando un backup `.bak` previo.")
            with c_bot2:
                if st.button(f"💾 Guardar Resultados de #{mid:02d} en historial_prompt.txt", type="primary", use_container_width=True, key=f"btn_save_bot_{mid}"):
                    save_wizard_data()

        with tab_sub_grid:
            match_data_key = f"fill_editor_df_{sel_m['match_id']}"
            if match_data_key not in st.session_state or st.session_state.get(f"fill_loaded_mid_{sel_m['match_id']}") != sel_m['match_id']:
                rows = []
                for idx, r in enumerate(sel_m['records']):
                    ver = r.get('veredicto')
                    ver_val = ver if ver in ['SI', 'NO', 'ANULADA'] else '[ ] Pendiente'
                    mar_val = r.get('margen')
                    cr_val = r.get('cr')
                    rows.append({
                        '#': idx + 1,
                        'Mercado': r.get('mercado', ''),
                        'Selección': r.get('seleccion', ''),
                        'Cuota Justa': f"@ {r['cj']:.2f}" if r.get('cj') else "-",
                        'Cuota Real': float(cr_val) if cr_val is not None else None,
                        'Veredicto': ver_val,
                        'Margen': int(mar_val) if mar_val is not None else None
                    })
                st.session_state[match_data_key] = pd.DataFrame(rows)
                st.session_state[f"fill_loaded_mid_{sel_m['match_id']}"] = sel_m['match_id']

            # Barra de Acciones Rápidas (One-Click)
            c_b1, c_b2, c_b3, c_b4 = st.columns(4)
            if c_b1.button("🟢 Marcar Pendientes como SÍ", use_container_width=True, key=f"btn_all_si_{sel_m['match_id']}"):
                df_c = st.session_state[match_data_key].copy()
                for i in range(len(df_c)):
                    if df_c.at[i, 'Veredicto'] == '[ ] Pendiente':
                        df_c.at[i, 'Veredicto'] = 'SI'
                        if pd.isna(df_c.at[i, 'Margen']):
                            df_c.at[i, 'Margen'] = 0
                st.session_state[match_data_key] = df_c
                st.rerun()

            if c_b2.button("🔴 Marcar Pendientes como NO", use_container_width=True, key=f"btn_all_no_{sel_m['match_id']}"):
                df_c = st.session_state[match_data_key].copy()
                for i in range(len(df_c)):
                    if df_c.at[i, 'Veredicto'] == '[ ] Pendiente':
                        df_c.at[i, 'Veredicto'] = 'NO'
                        if pd.isna(df_c.at[i, 'Margen']):
                            df_c.at[i, 'Margen'] = -1
                st.session_state[match_data_key] = df_c
                st.rerun()

            if c_b3.button("⚡ Auto-Completar Márgenes", use_container_width=True, key=f"btn_auto_m_{sel_m['match_id']}", help="Asigna Margen = 0 a los SÍ y Margen = -1 a los NO si no tienen margen definido."):
                df_c = st.session_state[match_data_key].copy()
                for i in range(len(df_c)):
                    v = df_c.at[i, 'Veredicto']
                    if pd.isna(df_c.at[i, 'Margen']):
                        if v == 'SI':
                            df_c.at[i, 'Margen'] = 0
                        elif v == 'NO':
                            df_c.at[i, 'Margen'] = -1
                st.session_state[match_data_key] = df_c
                st.rerun()

            if c_b4.button("🧹 Revertir Todos a Pendiente", use_container_width=True, key=f"btn_reset_{sel_m['match_id']}"):
                df_c = st.session_state[match_data_key].copy()
                df_c['Veredicto'] = '[ ] Pendiente'
                df_c['Margen'] = None
                st.session_state[match_data_key] = df_c
                st.rerun()

            col_cfg = {
                '#': st.column_config.NumberColumn('#', disabled=True, width='small'),
                'Mercado': st.column_config.TextColumn('Mercado', disabled=True, width='medium'),
                'Selección': st.column_config.TextColumn('Selección', disabled=True, width='large'),
                'Cuota Justa': st.column_config.TextColumn('Cuota Justa', disabled=True, width='small'),
                'Cuota Real': st.column_config.NumberColumn('Cuota Real', min_value=1.01, max_value=50.0, step=0.01, format="%.2f", width='small'),
                'Veredicto': st.column_config.SelectboxColumn('Veredicto', options=['[ ] Pendiente', 'SI', 'NO', 'ANULADA'], required=True, width='medium'),
                'Margen': st.column_config.NumberColumn('Margen (+/-)', step=1, format="%d", width='small')
            }

            edited_df = st.data_editor(
                st.session_state[match_data_key],
                column_config=col_cfg,
                disabled=['#', 'Mercado', 'Selección', 'Cuota Justa'],
                use_container_width=True,
                key=f"editor_table_{sel_m['match_id']}",
                num_rows="fixed"
            )

            # Resumen en vivo de cómo queda el partido
            si_cnt = sum(1 for v in edited_df['Veredicto'] if v == 'SI')
            no_cnt = sum(1 for v in edited_df['Veredicto'] if v == 'NO')
            anu_cnt = sum(1 for v in edited_df['Veredicto'] if v == 'ANULADA')
            pend_cnt = sum(1 for v in edited_df['Veredicto'] if v == '[ ] Pendiente')
            tot_concl = si_cnt + no_cnt
            proj_hr = round((si_cnt / tot_concl * 100), 1) if tot_concl > 0 else 0.0

            st.caption(f"📊 Vista Previa: **{si_cnt} SÍ** | **{no_cnt} NO** | **{anu_cnt} Anuladas** | **{pend_cnt} Pendientes** (Hit Rate proyectado: **{proj_hr}%**)")

            c_save1, c_save2 = st.columns([2, 1])
            if c_save1.button(f"💾 Guardar Veredictos de '{sel_m['match_name']}' en historial_prompt.txt", type="primary", use_container_width=True, key=f"btn_save_grid_{sel_m['match_id']}"):
                updates_dict = {}
                for idx, row in edited_df.iterrows():
                    v = row['Veredicto']
                    m = row['Margen']
                    cr = row['Cuota Real']
                    updates_dict[idx] = {
                        'veredicto': v if v != '[ ] Pendiente' else '',
                        'margen': m if not pd.isna(m) else None,
                        'cr': cr if not pd.isna(cr) else None
                    }
                try:
                    hist_updater.update_match_records(sel_m['match_id'], updates_dict, backup=True)
                    st.cache_resource.clear()
                    for k in list(st.session_state.keys()):
                        if k.startswith('fill_editor_df_') or k.startswith('editor_table_') or k.startswith('fill_loaded_mid_'):
                            del st.session_state[k]
                    st.success(f"✅ ¡Resultados de '{sel_m['match_name']}' guardados exitosamente!")
                    st.toast(f"✅ Historial actualizado: {sel_m['match_name']}")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error al guardar: {ex}")

        with tab_sub_text:
            st.caption("Modifica directamente las líneas o pega el bloque de texto con los resultados ya resueltos para este partido.")
            raw_text_input = st.text_area(
                f"Bloque de texto de #{sel_m['match_id']:02d} ({sel_m['match_name']}):",
                value=sel_m['raw_chunk'],
                height=350,
                key=f"raw_text_area_{sel_m['match_id']}"
            )
            if st.button(f"💾 Guardar Bloque de Texto en historial_prompt.txt", key=f"btn_save_raw_{sel_m['match_id']}"):
                try:
                    hist_updater.update_match_raw_chunk(sel_m['match_id'], raw_text_input, backup=True)
                    st.cache_resource.clear()
                    for k in list(st.session_state.keys()):
                        if k.startswith('fill_editor_df_') or k.startswith('editor_table_') or k.startswith('fill_loaded_mid_'):
                            del st.session_state[k]
                    st.success(f"✅ Bloque de texto de '{sel_m['match_name']}' actualizado exitosamente en historial_prompt.txt.")
                    st.toast(f"✅ Historial actualizado: {sel_m['match_name']}")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error al guardar texto: {ex}")
