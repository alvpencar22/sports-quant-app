import argparse
import sys
import os
import json
from typing import List, Dict, Any

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Ensure local imports work cleanly
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from quant_engine.parser import parse_historial_file, parse_single_line, parse_descalados_shorthand
from quant_engine.categories import categorize_item, get_line_level_type, extract_line_value, extract_player_name
from quant_engine.math_engine import QuantEngine, CJ_INTERVALS, get_cj_interval
from quant_engine.optimizer import BulletOptimizer, BulletLeg
from quant_engine.auditor import MatchAuditor

DATA_DIR = os.path.join(BASE_DIR, 'data')
HIST_PATH = os.path.join(DATA_DIR, 'historial_prompt.txt')
DATASET_PATH = os.path.join(DATA_DIR, 'categorized_dataset.json')
MATCHES_DIR = os.path.join(DATA_DIR, 'matches')

def get_engine() -> QuantEngine:
    if os.path.exists(HIST_PATH):
        records = parse_historial_file(HIST_PATH, DATASET_PATH)
    elif os.path.exists(DATASET_PATH):
        with open(DATASET_PATH, 'r', encoding='utf-8') as f:
            records = json.load(f)
    else:
        records = []
    return QuantEngine(records)

def cmd_status(args):
    print("\n" + "=" * 75)
    print(" 📊 SPORTS QUANT APP — ESTADO DEL SISTEMA CUANTITATIVO")
    print("=" * 75)

    engine = get_engine()
    total_raw = len(engine.raw_records)
    settled = len(engine.settled_records)
    matches = set(r.get('match_id') for r in engine.raw_records if r.get('match_id'))
    min_m = min(matches) if matches else 0
    max_m = max(matches) if matches else 0

    print(f"📁 Archivo Historial: {HIST_PATH}")
    print(f"📈 Total Registros Históricos: {total_raw} | Partidos: {len(matches)} (Rango #{min_m} - #{max_m})")
    print(f"✅ Registros Concluidos (SI/NO): {settled}")

    # Desglose por Ligas
    print("\n--- 🏆 DESGLOSE EMPÍRICO POR LIGAS ---")
    print(f"{'Liga':22} | {'Muestra (N)':12} | {'Aciertos (W)':12} | {'Hit Rate (%)':12} | {'Break-Even':10}")
    print("-" * 75)
    leagues = sorted(list(set(r.get('league', 'Otras Ligas') for r in engine.settled_records)))
    for lg in leagues:
        sub = [r for r in engine.settled_records if r.get('league') == lg]
        stats = engine.compute_basic_stats(sub)
        print(f"{lg:22} | {stats['n']:12} | {stats['w']:12} | {stats['hr']:10.1f}% | @ {stats['be']:.2f}")

    # Desglose por Franjas CJ
    print("\n--- 🎯 DESGLOSE POR FRANJA DE CUOTA JUSTA (CJ) ---")
    print(f"{'Franja CJ':25} | {'N':6} | {'W':6} | {'Hit Rate (%)':12} | {'Break-Even':10}")
    print("-" * 75)
    for code, label, cond in CJ_INTERVALS:
        sub = [r for r in engine.settled_records if r.get('cj') is not None and cond(r['cj'])]
        stats = engine.compute_basic_stats(sub)
        print(f"{code:25} | {stats['n']:6} | {stats['w']:6} | {stats['hr']:10.1f}% | @ {stats['be']:.2f}")

    # Top Categorías con mayor volumen
    print("\n--- ⚽ VOLUMEN POR CATEGORÍAS PRINCIPALES ---")
    cats = set(r.get('cat') for r in engine.settled_records if r.get('cat'))
    cat_stats = []
    for c in cats:
        sub = [r for r in engine.settled_records if r.get('cat') == c]
        if len(sub) >= 10:
            st = engine.compute_basic_stats(sub)
            cat_stats.append((c, st['n'], st['w'], st['hr'], st['be']))
    cat_stats.sort(key=lambda x: x[1], reverse=True)

    print(f"{'Categoría':35} | {'N':6} | {'W':6} | {'Hit Rate':10} | {'Break-Even':10}")
    print("-" * 75)
    for c, n, w, hr, be in cat_stats[:10]:
        print(f"{c:35} | {n:6} | {w:6} | {hr:8.1f}% | @ {be:.2f}")
    print("=" * 75 + "\n")

def cmd_explore(args):
    """Explora desplazamientos arbitrarios X+k (de X-6 a X+6 y Unders) para una categoría."""
    engine = get_engine()
    cat = args.category
    cj = args.cj
    league = args.league
    k_min = args.k_min
    k_max = args.k_max

    print("\n" + "=" * 80)
    print(f" 🔍 ANÁLISIS DE ESPECTRO COMPLETO DE LÍNEAS (X+k y Unders)")
    print(f" Categoría: '{cat}' | Franja CJ: {f'@ {cj:.2f}' if cj else 'Todas'} | Liga: {league or 'Global'}")
    print("=" * 80)

    # Espectro Overs
    print(f"{'Línea / Desplazamiento':25} | {'N Muestra':10} | {'W (Hits)':10} | {'Hit Rate (%)':12} | {'Break-Even':10}")
    print("-" * 80)
    for k in range(k_min, k_max + 1):
        st = engine.compute_line_offset_stats(category=cat, cj=cj, league=league, k=k, is_under=False)
        print(f"{st['label']:25} | {st['n']:10} | {st['w']:10} | {st['hr']:10.1f}% | @ {st['be']:.2f}")

    print("\n--- 🔄 INVERSIONES A UNDERS (Menos de) ---")
    print(f"{'Línea Under':25} | {'N Muestra':10} | {'W (Hits)':10} | {'Hit Rate (%)':12} | {'Break-Even':10}")
    print("-" * 80)
    for k in range(-2, 4):
        st = engine.compute_line_offset_stats(category=cat, cj=cj, league=league, k=k, is_under=True)
        print(f"{st['label']:25} | {st['n']:10} | {st['w']:10} | {st['hr']:10.1f}% | @ {st['be']:.2f}")

    # Distribución de márgenes
    m_dist = engine.compute_margin_distribution(category=cat, cj=cj, league=league)
    if m_dist['n'] > 0:
        print("\n--- 📊 DISTRIBUCIÓN ESTADÍSTICA DE MÁRGENES ---")
        print(f"N={m_dist['n']} | Media={m_dist['mean']:+} | Desv. Estándar={m_dist['std']} | Mediana={m_dist['median']:+} | Rango=[{m_dist['min']:+}, {m_dist['max']:+}]")
        print(f"Percentil 25%={m_dist['p25']:+} | Percentil 75%={m_dist['p75']:+}")
        print("Frecuencias de Margen:", m_dist['frequencies'])
    print("=" * 80 + "\n")

def cmd_t1(args):
    """Tiempo 1: Estudio cuantitativo complejo y ex-ante de la hoja pre-partido."""
    engine = get_engine()
    file_path = args.sheet
    league = args.league

    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    else:
        content = file_path

    lines = [l.strip() for l in content.split('\n') if l.strip() and 'Mercado:' in l]
    if not lines:
        print("❌ Error: No se encontraron líneas válidas con 'Mercado:'")
        return

    print("\n" + "=" * 145)
    print(f" ⏱️ TIEMPO 1: ESTUDIO CUANTITATIVO COMPLETO Y EX-ANTE ({len(lines)} SELECCIONES)")
    print(f" Liga del Partido: {league or 'Autodetectada / Global'}")
    print("=" * 145)

    deep_evaluated = []
    for l in lines:
        rec = parse_single_line(l)
        if not rec:
            continue
        eval_deep = engine.evaluate_selection_deep(
            mercado=rec['mercado'],
            seleccion=rec['seleccion'],
            cj=rec['cj'],
            cr=rec['cr'],
            league=league
        )
        eval_deep['raw'] = l
        deep_evaluated.append(eval_deep)

    # Ordenar por EV descendente (o HR si no hay CR)
    deep_evaluated.sort(
        key=lambda x: (
            x['base']['ev_liga'] if x['base']['ev_liga'] is not None 
            else (x['base']['ev_glob'] if x['base']['ev_glob'] is not None else -999),
            x['base']['hr_glob']
        ),
        reverse=True
    )

    # -------------------------------------------------------------
    # TABLA 1: MATRIZ MAESTRA COMPARATIVA — LÍNEA BASE X
    # -------------------------------------------------------------
    print("\n--- 📋 TABLA 1: MATRIZ COMPARATIVA — LÍNEA BASE X (GLOBAL VS LIGA) ---")
    hdr = f"{'Selección':30} | {'Cat':18} | {'CJ':4} | {'CR':4} | {'N_glo':5} | {'W_glo':5} | {'HR_glo':7} | {'BE_glo':7} | {'N_lig':5} | {'W_lig':5} | {'HR_lig':7} | {'BE_lig':7} | {'EV_glo':7} | {'EV_lig':7}"
    print(hdr)
    print("-" * 145)

    all_t2_recommendations = []

    for it in deep_evaluated:
        b = it['base']
        cj_s = f"{it['cj']:.2f}" if it['cj'] is not None else "N/A"
        cr_s = f"{it['cr']:.2f}" if it['cr'] is not None else "N/A"
        
        hr_g_s = f"{b['hr_glob']:5.1f}%"
        be_g_s = f"@{b['be_glob']:.2f}"
        
        hr_l_s = f"{b['hr_liga']:5.1f}%" if b['n_liga'] > 0 else " N/A "
        be_l_s = f"@{b['be_liga']:.2f}" if b['n_liga'] > 0 else " N/A "
        
        ev_g_s = f"{b['ev_glob']:+.2f}" if b['ev_glob'] is not None else " N/A "
        ev_l_s = f"{b['ev_liga']:+.2f}" if b['ev_liga'] is not None else " N/A "

        # Tag
        best_ev = b['ev_liga'] if b['ev_liga'] is not None else b['ev_glob']
        tag = "🔥" if best_ev and best_ev > 0 else ("⚠️" if best_ev and best_ev < -0.1 else "  ")

        sel_t = it['seleccion'][:30]
        cat_t = it['cat'][:18]

        row = f"{tag}{sel_t:28} | {cat_t:18} | {cj_s:4} | {cr_s:4} | {b['n_glob']:5} | {b['w_glob']:5} | {hr_g_s:7} | {be_g_s:7} | {b['n_liga']:5} | {b['w_liga']:5} | {hr_l_s:7} | {be_l_s:7} | {ev_g_s:7} | {ev_l_s:7}"
        print(row)

        # Collect T2 recommendations
        if it['t2_recommendations']:
            for r in it['t2_recommendations']:
                all_t2_recommendations.append((it['seleccion'], r))

    # -------------------------------------------------------------
    # TABLA 2: ESTUDIO DE LÍNEAS ALTERNATIVAS (DESCALADOS Y UNDERS)
    # -------------------------------------------------------------
    print("\n" + "=" * 145)
    print(" 🔍 TABLA 2: ESTUDIO COMPLETO DE LÍNEAS ALTERNATIVAS (DESCALADOS X-1..X-3 Y ESPECTRO COMPLETO DE UNDERS X..X+3)")
    print(" Muestra el nombre real de cada línea de apuesta, con su probabilidad de acierto global vs liga:")
    print("=" * 145)

    hdr_sub = f"{'Selección Base':26} | {'Tipo':15} | {'Línea Concreta de Apuesta':42} | {'N_glo':5} | {'W_glo':5} | {'HR_glo':7} | {'BE_glo':7} | {'N_lig':5} | {'W_lig':5} | {'HR_lig':7} | {'BE_lig':7}"
    print(hdr_sub)
    print("-" * 145)

    for it in deep_evaluated:
        sel_short = it['seleccion'][:26]
        
        # Build list of lines to show: Base + Descalados (X-1, X-2, X-3) + Unders (X, X+1, X+2, X+3)
        all_alt_lines = []
        # Base
        b = it['base']
        all_alt_lines.append(("Línea Base X", b['label'], b['n_glob'], b['w_glob'], b['hr_glob'], b['be_glob'], b['n_liga'], b['w_liga'], b['hr_liga'], b['be_liga']))
        
        # Descalados
        for d in it.get('descalados_spectrum', []):
            all_alt_lines.append((d['tag'], d['label'], d['n_glob'], d['w_glob'], d['hr_glob'], d['be_glob'], d['n_liga'], d['w_liga'], d['hr_liga'], d['be_liga']))
            
        # Unders
        for u in it.get('unders_spectrum', []):
            all_alt_lines.append((u['tag'], u['label'], u['n_glob'], u['w_glob'], u['hr_glob'], u['be_glob'], u['n_liga'], u['w_liga'], u['hr_liga'], u['be_liga']))

        for idx_l, (t_tag, l_name, n_g, w_g, hr_g, be_g, n_l, w_l, hr_l, be_l) in enumerate(all_alt_lines):
            prefix_sel = f"📌 {sel_short}" if idx_l == 0 else " " * 26
            name_trunc = l_name[:42]

            hr_g_s = f"{hr_g:5.1f}%"
            be_g_s = f"@{be_g:.2f}"
            hr_l_s = f"{hr_l:5.1f}%" if n_l > 0 else " N/A "
            be_l_s = f"@{be_l:.2f}" if n_l > 0 else " N/A "

            # Highlighting indicator
            hi_tag = "🌟" if hr_g >= 80.0 or (n_l >= 3 and hr_l >= 80.0) else "  "

            print(f"{prefix_sel:26} | {hi_tag}{t_tag:13} | {name_trunc:42} | {n_g:5} | {w_g:5} | {hr_g_s:7} | {be_g_s:7} | {n_l:5} | {w_l:5} | {hr_l_s:7} | {be_l_s:7}")
        print("-" * 145)

    # -------------------------------------------------------------
    # SECCIÓN 3: RADAR DE CUOTAS A MIRAR PARA TIEMPO 2
    # -------------------------------------------------------------
    print("\n" + "#" * 145)
    print(" 🎯 QUÉ CUOTAS DEBERÍAS MIRAR EN LAS CASAS PARA TIEMPO 2 (RADAR DE DESCALADOS Y UNDERS)")
    print(" Revisa estas líneas alternativas en tu casa de apuestas para ver si pagan igual o por encima de la Cuota Mínima:")
    print("#" * 145)

    if all_t2_recommendations:
        for idx_r, (orig_sel, rec) in enumerate(all_t2_recommendations, start=1):
            tag_type = "⭐" if "Suelo" in rec['tipo'] or "X-1" in rec['tipo'] else ("🔄" if "Under" in rec['tipo'] else "💡")
            print(f"\n{tag_type} Sugerencia #{idx_r} [{rec['tipo']}] para: '{orig_sel}'")
            print(f"   ➤ Línea a buscar:           {rec['linea_sugerida']}")
            
            hr_g_str = f"{rec['hr_glob']:5.1f}% (Aciertos: {rec['w_glob']}/{rec['n_glob']} | Cuota Justa: @{rec['be_glob']:.2f})"
            if rec.get('hr_liga') is not None and rec.get('n_liga', 0) > 0:
                hr_l_str = f"{rec['hr_liga']:5.1f}% (Aciertos: {rec['w_liga']}/{rec['n_liga']} | Cuota Justa: @{rec['be_liga']:.2f})"
            else:
                hr_l_str = "N/A (Sin muestra de liga)"
                
            print(f"   ➤ Hit Rate GLOBAL:          {hr_g_str}")
            print(f"   ➤ Hit Rate LIGA:            {hr_l_str}")
            print(f"   ➤ Cuota Mínima (Break-Even): @ {rec['cuota_minima_exigida']:.2f}")
            print(f"   ➤ Cuota Objetivo en Casa:   >= @ {rec['cuota_objetivo']:.2f}")
            print(f"   ➤ Explicación Matemática:   {rec['razon']}")
    else:
        print("No se generaron sugerencias automáticas. Todas las líneas base operan en sus niveles habituales.")

    print("\n" + "=" * 145)

    # Guardar evaluación estructurada para Tiempo 2
    out_path = os.path.join(MATCHES_DIR, 'staged_t1_evaluated.json')
    # Guardar tanto el formato simple como el deep para retrocompatibilidad
    legacy_evaluated = []
    for it in deep_evaluated:
        b = it['base']
        legacy_evaluated.append({
            'mercado': it['mercado'],
            'seleccion': it['seleccion'],
            'cat': it['cat'],
            'line_level': it['line_level'],
            'cj': it['cj'],
            'cj_franja': it['cj_franja'],
            'cr': it['cr'],
            'n': b['n_glob'],
            'w': b['w_glob'],
            'hr': b['hr_glob'],
            'be': b['be_glob'],
            'ev': b['ev_glob'],
            'league_stats': {
                'league': league,
                'n': b['n_liga'],
                'w': b['w_liga'],
                'hr': b['hr_liga'],
                'be': b['be_liga'],
                'ev': b['ev_liga']
            } if b['n_liga'] > 0 else None,
            'descalado_x1': it['descalado_x1'],
            'descalado_x2': it['descalado_x2'],
            'under': it['under'],
            't2_recommendations': it['t2_recommendations'],
            'deep': it
        })

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(legacy_evaluated, f, indent=2, ensure_ascii=False)

    # Actualizar automáticamente la Tabla Maestra de Selecciones con Valor (Pre-Partido +EV)
    value_board_path = os.path.join(MATCHES_DIR, 'match_value_board.json')
    board_entries = []
    if os.path.exists(value_board_path):
        try:
            with open(value_board_path, 'r', encoding='utf-8') as f_b:
                board_entries = json.load(f_b)
        except Exception:
            board_entries = []

    for it in deep_evaluated:
        b = it['base']
        cr = it.get('cr')
        if cr and ((b.get('ev_glob') and b['ev_glob'] > 0) or (b.get('ev_liga') and b['ev_liga'] > 0)):
            ev_g = b.get('ev_glob')
            ev_l = b.get('ev_liga')
            if ev_g is not None and ev_l is not None and ev_g > 0 and ev_l > 0:
                sello = "🔥 DOBLE VALOR (+EV Glo & Lig)"
            elif ev_l is not None and ev_l > 0:
                sello = "🟢 VALOR LIGA (+EV Lig)"
            elif ev_g is not None and ev_g > 0:
                sello = "🟡 VALOR GLOBAL (+EV Glo)"
            else:
                sello = "⚠️ SIN VALOR (CR < BE)"

            entry = {
                'seleccion': it['seleccion'],
                'tipo': 'Base X Pre-Partido',
                'mercado': it['cat'],
                'cr': cr,
                'hr_glob': b['hr_glob'],
                'be_glob': b['be_glob'],
                'n_glob': b['n_glob'],
                'w_glob': b['w_glob'],
                'ev_glob': ev_g,
                'hr_liga': b['hr_liga'] if b['n_liga'] > 0 else None,
                'be_liga': b['be_liga'] if b['n_liga'] > 0 else None,
                'n_liga': b['n_liga'],
                'w_liga': b['w_liga'],
                'ev_liga': ev_l,
                'sello': sello
            }
            if not any(x['seleccion'] == entry['seleccion'] for x in board_entries):
                board_entries.append(entry)

    with open(value_board_path, 'w', encoding='utf-8') as f_b:
        json.dump(board_entries, f_b, indent=2, ensure_ascii=False)

    print(f"💾 Estudio guardado exitosamente en: {out_path}")
    print(f"💎 Tabla Maestra de Valor actualizada ({len(board_entries)} selecciones) en: {value_board_path}")
    print("Listo para recibir Cuotas Reales de Tiempo 2 o ejecutar 'python cli.py t2'")
    print("=" * 125 + "\n")

def cmd_t2(args):
    """Tiempo 2: Optimiza y encuentra las 3 Balas Definitivas (0 solapamiento)."""
    t1_path = args.t1 or os.path.join(MATCHES_DIR, 'staged_t1_evaluated.json')
    if not os.path.exists(t1_path):
        print(f"❌ Error: No se encontró el archivo de Tiempo 1 en {t1_path}. Ejecuta 'python cli.py t1' primero.")
        return

    with open(t1_path, 'r', encoding='utf-8') as f:
        t1_items = json.load(f)

    # Ingestar descalados adicionales si se proporcionan
    descalados = []
    if args.descalados:
        if os.path.exists(args.descalados):
            with open(args.descalados, 'r', encoding='utf-8') as f:
                desc_text = f.read()
        else:
            desc_text = args.descalados
        parsed_desc = parse_descalados_shorthand(desc_text)
        print(f"Ingestados {len(parsed_desc)} descalados/líneas alternativas de Tiempo 2.")

    # Construir lista de BulletLeg candidatos
    legs = []
    engine = get_engine()

    for idx, it in enumerate(t1_items):
        cr = it.get('cr')
        if cr and cr > 1.0:
            player = extract_player_name(it['seleccion'])
            leg = BulletLeg(
                leg_id=f"L{idx+1}",
                desc=it['seleccion'],
                cr=cr,
                hr=it['hr'],
                be=it['be'],
                ev=it['ev'] if it['ev'] is not None else (cr * it['hr'] / 100.0 - 1.0),
                category=it['cat'],
                player=player
            )
            legs.append(leg)

    # Añadir descalados si se evaluaron
    if args.descalados:
        for idx, d in enumerate(parsed_desc, start=len(legs)+1):
            desc_text = d['descripcion']
            cr = d['cr']
            # Evaluar hit rate de descalado empírico
            cat = categorize_item("", desc_text)
            player = extract_player_name(desc_text)
            
            # Detectar offset k o suelo
            if '2 tiros' in desc_text.lower() or '2 entradas' in desc_text.lower() or '2 faltas' in desc_text.lower():
                stat = engine.compute_line_offset_stats(category=cat, k=-1, cr=cr)
            elif 'suelo' in desc_text.lower() or '1+' in desc_text.lower() or '0.5' in desc_text.lower():
                stat = engine.compute_line_offset_stats(category=cat, k=-2, cr=cr)
            elif 'over 1.5' in desc_text.lower():
                stat = engine.compute_line_offset_stats(category='Goles - Más de (Overs)', k=-1, cr=cr)
            else:
                stat = engine.compute_line_offset_stats(category=cat, k=-1, cr=cr)

            leg = BulletLeg(
                leg_id=f"D{idx}",
                desc=desc_text,
                cr=cr,
                hr=stat['hr'],
                be=stat['be'],
                ev=stat['ev'] if stat['ev'] is not None else (cr * stat['hr'] / 100.0 - 1.0),
                category=cat,
                player=player
            )
            legs.append(leg)

    print("\n" + "=" * 95)
    print(f" 🎯 TIEMPO 2: OPTIMIZACIÓN COMBINATORIA DE BALAS DEFINITIVAS")
    print(f" Total Candidatos: {len(legs)} selecciones evaluadas")
    print(f" Rango de Cuota Objetivo: [@ {args.min_odds:.2f} – @ {args.max_odds:.2f}] | Máx 2 Legs por Bala | 0 Solapamiento")
    print("=" * 95)

    optimizer = BulletOptimizer(
        min_odds=args.min_odds,
        max_odds=args.max_odds,
        max_legs_per_bullet=2
    )

    candidate_bullets = optimizer.build_candidate_bullets(legs)
    print(f"💡 Balas candidatas generadas (Simples + Dobles en rango): {len(candidate_bullets)}")

    triplets = optimizer.optimize_triplets(candidate_bullets, top_k=3)

    if not triplets:
        print("⚠️ No se encontraron tríos con 0 solapamiento en el rango exacto. Prueba ampliando el rango de cuotas.")
        return

    for tr in triplets:
        print("\n" + "#" * 95)
        print(f" 🌟 {tr['estrategia'].upper()}")
        print(f" 📈 EV Conjunto: {tr['ev_total']:+.4f} | Probabilidad >= 2 Aciertos: {tr['prob_al_menos_2_aciertos']} | HR Promedio: {tr['hr_promedio']}")
        print("#" * 95)

        for b_name in ['bala_1', 'bala_2', 'bala_3']:
            b = tr[b_name]
            label_b = b_name.replace('_', ' ').title()
            print(f"\n   ➤ {label_b} ({b['tipo']}): Cuota Real @ {b['cr']:.2f} | HR: {b['hr']}% | Break-Even: @ {b['be']:.2f} | EV: {b['ev']:+.4f}")
            for leg in b['legs']:
                print(f"      • {leg['desc']} [@ {leg['cr']:.2f} | HR: {leg['hr']}% | BE: @ {leg['be']:.2f}]")

    # Guardar tríos recomendados
    out_path = os.path.join(MATCHES_DIR, 'staged_bullets.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(triplets, f, indent=2, ensure_ascii=False)
    print("\n" + "=" * 95)
    print(f"💾 Tríos de Balas guardados exitosamente en: {out_path}\n")

def cmd_audit(args):
    """Audita los resultados de un partido y sincroniza el historial."""
    auditor = MatchAuditor(DATA_DIR)
    bullets_path = args.bullets or os.path.join(MATCHES_DIR, 'staged_bullets.json')
    if not os.path.exists(bullets_path):
        print(f"❌ Error: No se encontró el archivo de balas en {bullets_path}")
        return

    with open(bullets_path, 'r', encoding='utf-8') as f:
        staged = json.load(f)

    # Seleccionar la estrategia jugada (por defecto Opción A u Opción B)
    chosen_strategy = staged[0]
    bullets_to_audit = [chosen_strategy['bala_1'], chosen_strategy['bala_2'], chosen_strategy['bala_3']]

    print("\n" + "=" * 80)
    print(f" 🏁 AUDITORÍA POST-PARTIDO Y LIQUIDACIÓN DE BALAS")
    print(f" Estrategia Auditada: {chosen_strategy.get('estrategia')}")
    print("=" * 80)

    # Si se proporciona archivo de resultados
    settlements = {}
    if args.results and os.path.exists(args.results):
        with open(args.results, 'r', encoding='utf-8') as f:
            for line in f:
                rec = parse_single_line(line)
                if rec and rec['veredicto']:
                    settlements[rec['seleccion']] = rec['veredicto']

    res = auditor.audit_bullets(bullets_to_audit, settlements)
    print(f"💰 Unidades Apostadas: {res['unidades_apostadas']}")
    print(f"💵 Unidades Retornadas: {res['unidades_retornadas']}")
    print(f"📈 Beneficio Neto: {res['beneficio_neto']:+} Unidades")
    print(f"🎯 Yield / ROI: {res['yield_pct']}")
    print("-" * 80)
    for b in res['balas']:
        tag = "✅" if b['estado'] == 'GANADA' else ("❌" if b['estado'] == 'PERDIDA' else "⏳")
        print(f"{tag} {b['bala_id']}: Cuota @ {b['cr']} | Estado: {b['estado']} | Beneficio: {b['beneficio']:+} u.")
        for l in b['legs']:
            print(f"    - {l['desc']}: [{l['resultado']}]")
    print("=" * 80 + "\n")

def main():
    parser = argparse.ArgumentParser(
        description="Sports Quant App - Sistema Cuantitativo y Optimización de Balas",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponibles")

    # Command: status
    subparsers.add_parser("status", help="Muestra el estado general del dataset, ligas y métricas.")

    # Command: explore
    p_exp = subparsers.add_parser("explore", help="Explora desplazamientos arbitrarios X+k y Unders de un mercado.")
    p_exp.add_argument("category", type=str, help="Nombre de la categoría (ej: 'Player - Tiros Totales')")
    p_exp.add_argument("--cj", type=float, default=None, help="Cuota Justa de referencia (ej: 1.50)")
    p_exp.add_argument("--league", type=str, default=None, help="Filtro opcional de liga (ej: 'La Liga')")
    p_exp.add_argument("--k_min", type=int, default=-6, help="Mínimo desplazamiento k (defecto -6)")
    p_exp.add_argument("--k_max", type=int, default=6, help="Máximo desplazamiento k (defecto +6)")

    # Command: t1
    p_t1 = subparsers.add_parser("t1", help="Tiempo 1: Analiza una hoja completa pre-partido.")
    p_t1.add_argument("sheet", type=str, help="Ruta al archivo de texto con las líneas pre-partido.")
    p_t1.add_argument("--league", type=str, default=None, help="Liga del partido.")

    # Command: t2
    p_t2 = subparsers.add_parser("t2", help="Tiempo 2: Optimiza y construye las 3 Balas Definitivas.")
    p_t2.add_argument("--t1", type=str, default=None, help="Archivo JSON de Tiempo 1 (opcional).")
    p_t2.add_argument("--descalados", type=str, default=None, help="Texto o archivo con cuotas de descalados.")
    p_t2.add_argument("--min_odds", type=float, default=1.80, help="Cuota mínima por bala (defecto 1.80).")
    p_t2.add_argument("--max_odds", type=float, default=2.35, help="Cuota máxima por bala (defecto 2.35).")

    # Command: audit
    p_aud = subparsers.add_parser("audit", help="Audita resultados post-partido y actualiza el historial.")
    p_aud.add_argument("--bullets", type=str, default=None, help="Archivo JSON de balas jugadas.")
    p_aud.add_argument("--results", type=str, default=None, help="Archivo de texto con los resultados oficiales.")

    args = parser.parse_args()

    if args.command == "status":
        cmd_status(args)
    elif args.command == "explore":
        cmd_explore(args)
    elif args.command == "t1":
        cmd_t1(args)
    elif args.command == "t2":
        cmd_t2(args)
    elif args.command == "audit":
        cmd_audit(args)
    else:
        # Default behavior: show status and help
        cmd_status(args)
        parser.print_help()

if __name__ == '__main__':
    main()
