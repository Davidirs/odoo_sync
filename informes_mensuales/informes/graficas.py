"""Gráficas del informe con los colores ESMT (PNG para insertar en Word)."""
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

NARANJA, AZUL, NARANJA_CLARO, GRIS, ROJO, TEXTO = "#EA580C", "#013C4D", "#FDBA74", "#94A3B8", "#DC2626", "#333333"
MESES_CORTOS = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": "#CBD5E1", "axes.labelcolor": TEXTO, "xtick.color": TEXTO,
    "ytick.color": TEXTO, "axes.spines.top": False, "axes.spines.right": False,
})


def _guardar(fig, ruta):
    fig.tight_layout()
    fig.savefig(ruta, dpi=200)
    plt.close(fig)
    return ruta


def _etiquetas(ax, barras, fmt="{:.0f}"):
    for b in barras:
        alto = b.get_height()
        if alto:
            ax.annotate(fmt.format(alto), (b.get_x() + b.get_width() / 2, alto), ha="center", va="bottom",
                        fontsize=9, color=TEXTO, xytext=(0, 2), textcoords="offset points")


def barras(categorias, valores, ruta, color=NARANJA):
    fig, ax = plt.subplots(figsize=(6.3, 2.6))
    # Etiquetas de varias palabras van en dos líneas, pero nunca se corta una palabra.
    etiquetas = [textwrap.fill(c, 12, break_long_words=False, break_on_hyphens=False) for c in categorias]
    b = ax.bar(etiquetas, valores, color=color, width=0.5)
    _etiquetas(ax, b)
    ax.set_ylim(0, max(valores + [1]) * 1.2)
    ax.yaxis.get_major_locator().set_params(integer=True)
    ax.grid(axis="y", color="#E2E8F0", linewidth=0.6)
    ax.set_axisbelow(True)
    plt.setp(ax.get_xticklabels(), fontsize=9)
    return _guardar(fig, ruta)


def mes_a_mes(meses, tipos, ruta):
    colores = [NARANJA, AZUL, NARANJA_CLARO, GRIS, "#0EA5E9", "#A3A3A3"]
    fig, ax = plt.subplots(figsize=(6.3, 2.8))
    ancho = 0.8 / max(1, len(tipos))
    xs = range(len(meses))
    for i, tipo in enumerate(tipos):
        b = ax.bar([x + (i - (len(tipos) - 1) / 2) * ancho for x in xs], [m.get(tipo, 0) for m in meses],
                   ancho, label=tipo, color=colores[i % len(colores)])
        _etiquetas(ax, b)
    ax.set_xticks(list(xs), [MESES_CORTOS[m["mes"]] for m in meses])
    ax.yaxis.get_major_locator().set_params(integer=True)
    ax.grid(axis="y", color="#E2E8F0", linewidth=0.6)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, ncol=len(tipos), loc="upper left", fontsize=9)
    ax.set_ylim(0, max([m.get(t, 0) for m in meses for t in tipos] + [1]) * 1.3)
    return _guardar(fig, ruta)


def capacidad(items, ruta):
    """items: [(nombre, porcentaje)]; barra horizontal por recurso con la línea del 100 %."""
    items = [(n, p) for n, p in items if p is not None]
    if not items:
        return None
    fig, ax = plt.subplots(figsize=(6.3, 0.42 * len(items) + 0.8))
    nombres = [n for n, _ in items][::-1]
    pcts = [p for _, p in items][::-1]
    colores = [ROJO if p > 100 else (NARANJA if p >= 85 else AZUL) for p in pcts]
    ax.barh(nombres, [min(p, 150) for p in pcts], color=colores, height=0.55)
    ax.axvline(100, color=GRIS, linestyle="--", linewidth=1)
    for y, p in enumerate(pcts):
        etiqueta = "sin contratar" if p == float("inf") else f"{p:.0f}%"
        ax.text(min(p, 150) + 2, y, etiqueta, va="center", fontsize=9, color=TEXTO)
    ax.set_xlim(0, 165)
    ax.set_xlabel("% de uso sobre lo disponible (contratado, incluido o fair use)", fontsize=8)
    plt.setp(ax.get_yticklabels(), fontsize=8.5)
    ax.grid(axis="x", color="#E2E8F0", linewidth=0.6)
    ax.set_axisbelow(True)
    return _guardar(fig, ruta)
