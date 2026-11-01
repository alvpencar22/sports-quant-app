import os
import sys

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from cli import cmd_status, cmd_explore, cmd_t1, cmd_t2, cmd_audit, get_engine, DATA_DIR, MATCHES_DIR
from quant_engine.parser import parse_historial_file
from types import SimpleNamespace

def print_menu():
    print("\n" + "=" * 70)
    print(" ⚽ SPORTS QUANT APP — SISTEMA CUANTITATIVO DE APUESTAS")
    print("=" * 70)
    print(" [1] 📊 Ver Estado del Sistema y Estadísticas de Ligas / Mercados")
    print(" [2] 🔍 Explorar Líneas Arbitrarias X+k (de X-6 a X+6 y Unders)")
    print(" [3] ⏱️ Analizar Hoja Pre-Partido (Tiempo 1: Ex-Ante)")
    print(" [4] 🎯 Optimizar 3 Balas Definitivas con Descalados (Tiempo 2)")
    print(" [5] 🏁 Auditar Resultados Post-Partido y Actualizar Historial")
    print(" [6] 🔄 Re-indexar y Re-parsear historial_prompt.txt")
    print(" [0] 🚪 Salir")
    print("=" * 70)

def main():
    while True:
        print_menu()
        choice = input("\nSelecciona una opción (0-6): ").strip()
        
        if choice == '0':
            print("\n¡Hasta pronto! Que los números y el EV positivo te acompañen.\n")
            break
        elif choice == '1':
            cmd_status(None)
        elif choice == '2':
            cat = input("Introduce la categoría (ej: 'Player - Tiros Totales', 'Partido - Tiros Totales (Overs)', 'Goles - Más de (Overs)'): ").strip()
            if not cat:
                print("❌ Categoría requerida.")
                continue
            cj_in = input("Cuota Justa de referencia (Enter para todas, ej: 1.50): ").strip()
            cj = float(cj_in) if cj_in else None
            lg_in = input("Liga (Enter para global, ej: 'La Liga', 'Serie A'): ").strip()
            league = lg_in if lg_in else None
            args = SimpleNamespace(category=cat, cj=cj, league=league, k_min=-6, k_max=6)
            cmd_explore(args)
        elif choice == '3':
            sheet_input = input("Ruta al archivo .txt o escribe/pega el texto de la hoja: ").strip()
            if not sheet_input:
                sheet_input = os.path.join(MATCHES_DIR, 'sheet_atletico_prematch.txt')
                print(f"Usando archivo de prueba por defecto: {sheet_input}")
            lg_in = input("Liga del partido (Enter para autodetectar): ").strip()
            league = lg_in if lg_in else None
            args = SimpleNamespace(sheet=sheet_input, league=league)
            cmd_t1(args)
        elif choice == '4':
            desc_input = input("Introduce cuotas de descalados (ej: 'julian 2 tiros 1.18, manu sanchez 2 entradas 1.28' o Enter para usar candidatos de T1): ").strip()
            descalados = desc_input if desc_input else None
            args = SimpleNamespace(
                t1=os.path.join(MATCHES_DIR, 'staged_t1_evaluated.json'),
                descalados=descalados,
                min_odds=1.80,
                max_odds=2.35
            )
            cmd_t2(args)
        elif choice == '5':
            res_input = input("Ruta al archivo .txt con los resultados oficiales (o Enter para auditar balas staged): ").strip()
            results = res_input if res_input else None
            args = SimpleNamespace(
                bullets=os.path.join(MATCHES_DIR, 'staged_bullets.json'),
                results=results
            )
            cmd_audit(args)
        elif choice == '6':
            print("🔄 Re-indexando archivo historial_prompt.txt...")
            hist_path = os.path.join(DATA_DIR, 'historial_prompt.txt')
            can_path = os.path.join(DATA_DIR, 'categorized_dataset.json')
            records = parse_historial_file(hist_path, can_path)
            print(f"✅ Sincronizados exitosamente {len(records)} registros históricos en memoria y caché.")
        else:
            print("❌ Opción no válida. Inténtalo de nuevo.")

if __name__ == '__main__':
    main()
