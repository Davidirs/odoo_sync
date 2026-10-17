"""Genera los borradores de informe mensual en salida/AAAA-MM/<CLIENTE>/.

Uso:
  .venv/bin/python generar.py --mes 2026-09 --cliente STEREN
  .venv/bin/python generar.py --mes 2026-09 --todos
  .venv/bin/python generar.py --mes 2026-09 --cliente STEREN --etapas docx,pdf   # re-renderizar tras editar textos.json

Etapas (por defecto todas, en orden):
  datos   Odoo + License Manager + status.mypurecloud.com → datos.json
  textos  textos.json con la IA de IA_PROVIDER (anthropic o deepseek); sin IA deja ENCARGO_REDACCION.md para Claude Code
  docx    Word + validaciones → revision.md y _REVISION_GENERAL.md del mes
  pdf     PDF con LibreOffice e índice actualizado (necesita LibreOffice instalado)
"""
import argparse
import sys
import traceback

from informes.config import cargar_config
from informes.generador import ETAPAS, cortes, generar


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mes", required=True, help="AAAA-MM del informe (mes de los tickets)")
    grupo = ap.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--cliente", help="código en clientes.yaml")
    grupo.add_argument("--todos", action="store_true", help="todos los clientes activos")
    ap.add_argument("--etapas", default=",".join(ETAPAS))
    ap.add_argument("--corte", help="fecha de corte AAAA-MM-DD (por defecto, ahora)")
    ap.add_argument("--rehacer-textos", action="store_true", help="vuelve a redactar aunque exista textos.json")
    ap.add_argument("--sin-historico", action="store_true", help="omite el histórico anual de licenciamiento")
    ap.add_argument("--sin-licenciamiento", action="store_true", help="no consulta License Manager ni incluye la sección")
    args = ap.parse_args()

    cfg = cargar_config()
    anio, mes = map(int, args.mes.split("-"))
    corte, corte_local = cortes(args.corte)
    etapas = [e.strip() for e in args.etapas.split(",")]
    clientes = [c for c in cfg.clientes if c.activo] if args.todos else [cfg.cliente(args.cliente)]

    fallos = 0
    for cliente in clientes:
        print(f"\n== {cliente.codigo}")
        try:
            r = generar(cfg, cliente, anio, mes, etapas, corte, corte_local, args.rehacer_textos,
                        historico=not args.sin_historico, licenciamiento=not args.sin_licenciamiento)
            datos = r["datos"]
            print(f"   carpeta: {r['carpeta']}")
            if "datos" in etapas:
                lic = ("omitido" if datos.get("licenciamiento_omitido") else
                       "ok" if datos["licenciamiento"] else "NO: " + datos["errores"].get("licenciamiento", ""))
                print(f"   datos: {datos['soporte']['total']} tickets · licenciamiento {lic} · "
                      f"estado {'ok' if datos['estado'] else 'NO'}")
            if r["textos_origen"]:
                print(f"   textos: {r['textos_origen']}")
            if "docx" in etapas:
                print(f"   docx: {r['semaforo']} {r['archivo']} ({r['errores']} errores, {r['avisos']} avisos)")
            if "pdf" in etapas:
                print(f"   pdf: {r.get('pdf') or 'NO: ' + str(r.get('pdf_error'))}")
        except Exception:
            fallos += 1
            print(f"   ERROR generando {cliente.codigo}:\n{traceback.format_exc()}")
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
