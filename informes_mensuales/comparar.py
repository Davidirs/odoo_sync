"""Compara un informe hecho a mano con el borrador generado (datos.json + textos.json).

Uso:
  .venv/bin/python comparar.py "/ruta/INFORME MENSUAL SEPTIEMBRE STEREN.docx" salida/2026-09/STEREN
Escribe comparacion.md en la carpeta del borrador.
"""
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
RESPALDO = ("conforme a lo acordado con el cliente", "completando la atención y validación correspondiente")


def _texto(nodo):
    return "".join(t.text or "" for t in nodo.iter(W + "t")).strip()


def leer_manual(ruta):
    cuerpo = ET.fromstring(zipfile.ZipFile(ruta).read("word/document.xml")).find(W + "body")
    tablas, parrafos = [], []
    for el in cuerpo:
        if el.tag == W + "tbl":
            filas = [[" ".join(_texto(p) for p in c.iter(W + "p")).strip() for c in tr.iter(W + "tc")] for tr in el.iter(W + "tr")]
            tablas.append(filas)
        elif el.tag == W + "p":
            estilo = el.find(f"{W}pPr/{W}pStyle")
            parrafos.append((estilo.get(W + "val") if estilo is not None else "", _texto(el)))
    return tablas, parrafos


def tabla(tablas, *encabezado):
    for t in tablas:
        if t and [c.lower() for c in t[0][:len(encabezado)]] == [e.lower() for e in encabezado]:
            return t
    return None


def _n(s):
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def comparar(manual, carpeta):
    datos = json.loads((carpeta / "datos.json").read_text(encoding="utf-8"))
    textos_p = carpeta / "textos.json"
    textos = json.loads(textos_p.read_text(encoding="utf-8")) if textos_p.exists() else {}
    s = datos["soporte"]
    tablas, parrafos = leer_manual(manual)
    filas = []  # (sección, métrica, manual, generado, nota)

    def fila(seccion, metrica, m, g, nota=""):
        filas.append((seccion, metrica, m, g, nota))

    # Volumen por tipo
    t = tabla(tablas, "Tipo de caso", "Cantidad")
    if t:
        man = {r[0]: r[1] for r in t[1:]}
        gen = {x["tipo"]: x["cantidad"] for x in s["por_tipo"]}
        for k in sorted(set(man) | set(gen) - {"Total"}):
            if k == "Total":
                continue
            fila("Volumen", f"Casos tipo {k}", man.get(k, "—"), gen.get(k, 0))
        fila("Volumen", "Total de casos", man.get("Total", "—"), s["total"])

    # Tiempo promedio y días por ticket
    t = tabla(tablas, "ID", "Asunto", "Creado el")
    if t:
        prom = next((r[-1] for r in t if "promedio" in " ".join(r).lower()), "—")
        fila("Tiempo", "Días promedio", prom, s["promedio_dias_cierre"],
             "Manual: incluye abiertos contando hasta la última actualización. Generado: solo cerrados.")
        dias = {int(r[0]): r[-1] for r in t[1:] if r[0].isdigit()}
        difs = [f"#{x['id']}: {dias.get(x['id'])}→{x['dias']}{'*' if x['en_curso'] else ''}"
                for x in s["tickets"] if str(dias.get(x["id"])) != str(x["dias"])]
        fila("Tiempo", "Tickets con días distintos", len(difs), "", "; ".join(difs) or "—")

    # Horas y estados por ticket
    t = tabla(tablas, "ID", "Asunto", "Estado", "Horas")
    if t:
        total = next((r[-1] for r in t if "total" in " ".join(r).lower()), "—")
        fila("Horas", "Total de horas", total, f"{s['horas_total']:.2f}")
        man = {int(r[0]): (r[2], _n(r[3])) for r in t[1:] if r[0].isdigit()}
        horas = [f"#{x['id']}: {man[x['id']][1]}→{x['horas']}" for x in s["tickets"] if x["id"] in man and man[x["id"]][1] != x["horas"]]
        estados = [f"#{x['id']}: {man[x['id']][0]}→{x['etapa']}" for x in s["tickets"] if x["id"] in man and man[x["id"]][0] != x["etapa"]]
        fila("Horas", "Tickets con horas distintas", len(horas), "", "; ".join(horas) or "—")
        fila("Estados", "Tickets con estado distinto", len(estados), "", "; ".join(estados) or "—")

    t = tabla(tablas, "Estado", "Cantidad")
    if t:
        man = {r[0]: r[1] for r in t[1:]}
        gen = {x["etapa"]: x["cantidad"] for x in s["por_etapa"]}
        for k in [x["etapa"] for x in s["por_etapa"]]:
            if str(man.get(k, "0")) != str(gen[k]):
                fila("Estados", f"Estado {k}", man.get(k, "—"), gen[k])
    texto_estado = next((p for _, p in parrafos if "todos los casos se encuentran actualmente cerrados" in p.lower()), None)
    if texto_estado and s["abiertos"]:
        fila("Estados", "Frase «todos los casos cerrados»", "Sí", "No", f"Falso en el manual: {s['abiertos']} casos siguen abiertos.")

    # Serie mes a mes
    t = tabla(tablas, "Mes", "Incidente", "Requerimiento")
    if t:
        enc = t[0]
        gen = {m["mes"]: m for m in s["serie_anual"]["meses"]}
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        difs = []
        for r in t[1:]:
            if r[0].lower() not in meses:
                continue
            nmes = meses.index(r[0].lower()) + 1
            man_total = sum(_n(x) or 0 for x in r[1:])
            g = gen.get(nmes, {})
            gen_total = sum(v for k, v in g.items() if k != "mes")
            man_detalle = ", ".join(f"{enc[i]} {r[i]}" for i in range(1, len(r)) if r[i] not in ("0", ""))
            gen_detalle = ", ".join(f"{k} {v}" for k, v in g.items() if k != "mes" and v)
            if man_total != gen_total or man_detalle.replace("Cambios", "Cambio") != gen_detalle:
                difs.append(f"{r[0]}: [{man_detalle or '0'}] → [{gen_detalle or '0'}]")
        fila("Mes a mes", "Meses con clasificación distinta", len(difs), "", "; ".join(difs) or "—")

    # Resúmenes de tickets
    resumenes = [p for e, p in parrafos if e == ""]
    respaldo = sum(1 for p in resumenes if any(f in p for f in RESPALDO))
    resueltos_en_curso = []
    for x in s["tickets"]:
        idx = next((i for i, (e, p) in enumerate(parrafos) if e.startswith("Heading2") and f"(#{x['id']})" in p), None)
        if idx is not None and x["en_curso"] and idx + 1 < len(parrafos) and re.search(r"resolvi|resuelto", parrafos[idx + 1][1], re.I):
            resueltos_en_curso.append(str(x["id"]))
    gen_res = {int(t["id"]): t["resumen"] for t in (textos.get("soporte") or {}).get("tickets", [])}
    fila("Redacción", "Resúmenes con texto genérico de respaldo", respaldo,
         sum(1 for r in gen_res.values() if any(f in r for f in RESPALDO)))
    fila("Redacción", "Tickets en curso descritos como resueltos", len(resueltos_en_curso), 0, ", ".join(resueltos_en_curso) or "—")
    tel = re.compile(r"(?<![\d#])\d[\d\s-]{8,}\d")
    fila("Redacción", "Resúmenes con teléfonos o campos internos",
         sum(1 for p in resumenes if tel.search(p) or "ticket_type_id" in p),
         sum(1 for r in gen_res.values() if tel.search(r) or "ticket_type_id" in r))

    # Licenciamiento (líneas "1.- Nombre: X contratadas, Y en uso")
    lic = datos.get("licenciamiento")
    lineas = [p for _, p in parrafos if re.match(r"\d+\.-\s", p)]
    man_lic = {}
    for p in lineas:
        m = re.match(r"\d+\.-\s*([^:]+):\s*([\d,\.]+) contratadas, ([\d,\.]+) en uso", p)
        if m:
            man_lic[m.group(1).strip()] = (_n(m.group(2)), _n(m.group(3)))
    if lic:
        k = lic["kpis"]
        gen_lic = {l["nombre"]: (l["contratadas"], l["en_uso"]) for l in k["licencias"]}
        for r in k["recursos"]:
            gen_lic[r["nombre"]] = (r["comprometido"], r["en_uso"])
        gen_lic["Genesys Cloud IVR Basic Per Minute Charge"] = (k["ivr"]["asignado"], k["ivr"]["usado"])
        gen_lic["Genesys Cloud BYOC Cloud"] = (k["byoc"].get("prepagado", 0.0), k["byoc"]["usado"])
        for nombre, (c, u) in man_lic.items():
            g = gen_lic.get(nombre)
            fila("Licenciamiento", nombre, f"{c:,.1f} / {u:,.1f}", f"{g[0]:,.1f} / {g[1]:,.1f}" if g else "—", "contratadas / en uso")
        b = k["byoc"]
        fila("Licenciamiento", "BYOC Cloud: ¿sobreuso?",
             "Sí (según el texto IA)" if any("BYOC" in p and "sobreuso" in p for _, p in parrafos) else "No",
             "Sí" if b["excedente"] else f"No ({b['pct']}% del fair use)")
        fila("Licenciamiento", "Periodo", "", f"{k['periodo']['inicio'][:10]} a {k['periodo']['fin'][:10]}")
    else:
        fila("Licenciamiento", "Datos", f"{len(man_lic)} KPIs en el manual", "sin datos (License Manager no configurado)")

    lineas_md = [f"# Comparación: manual vs. generado — {datos['cliente']['nombre']} {datos['periodo_txt']}", "",
                 f"Manual: `{Path(manual).name}` · Generado con datos al {datos['fecha_corte']}", "",
                 "| Sección | Métrica | Manual | Generado | Nota |", "|---|---|---|---|---|"]
    lineas_md += [f"| {a} | {b} | {c} | {d} | {e} |" for a, b, c, d, e in filas]
    (carpeta / "comparacion.md").write_text("\n".join(lineas_md) + "\n", encoding="utf-8")
    return filas


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    for f in comparar(sys.argv[1], Path(sys.argv[2])):
        print(" | ".join(str(x) for x in f))
