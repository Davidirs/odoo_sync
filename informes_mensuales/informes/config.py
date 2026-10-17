"""Configuración: credenciales (.env), clientes (clientes.yaml) y utilidades de periodo."""
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent

MESES = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

EMPRESA = {"nombre": "Grupo ESMT", "preparado_por": "Support Team"}
# Modelo por defecto de cada proveedor de redacción (IA_MODEL lo sustituye).
MODELOS_IA = {"anthropic": "claude-opus-5-5", "deepseek": "deepseek-v4-pro"}


@dataclass
class Cliente:
    codigo: str
    nombre: str
    odoo_team_id: int
    genesys_org: str = ""
    region_genesys: str = ""
    logo: str = ""
    activo: bool = True
    # Empresas (commercial_partner en Odoo) cuyos tickets no van en este informe,
    # para helpdesks que comparten varias entidades del mismo grupo.
    excluir_empresas: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    @property
    def logo_path(self):
        return (RAIZ / self.logo) if self.logo else None

    @classmethod
    def desde_dict(cls, c):
        conocidos = set(cls.__dataclass_fields__) - {"extra"}
        return cls(**{k: v for k, v in c.items() if k in conocidos},
                   extra={k: v for k, v in c.items() if k not in conocidos})


@dataclass
class Config:
    odoo_url: str
    odoo_db: str
    odoo_user: str
    odoo_password: str
    lm_api_url: str
    lm_user: str
    lm_password: str
    ia_provider: str
    ia_model: str
    salida_dir: Path
    empresa: dict
    clientes: list
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"

    @property
    def lm_configurado(self):
        return bool(self.lm_api_url and self.lm_user and self.lm_password)

    @property
    def ia_configurada(self):
        # Anthropic: las credenciales las resuelve el SDK (ANTHROPIC_API_KEY o perfil de `ant auth login`).
        if self.ia_provider == "deepseek":
            return bool(self.deepseek_api_key)
        return self.ia_provider == "anthropic"

    def cliente(self, codigo):
        for c in self.clientes:
            if c.codigo.lower() == codigo.lower():
                return c
        raise SystemExit(f"Cliente '{codigo}' no está en clientes.yaml")


def config_desde_entorno(clientes=(), empresa=None, salida_dir=None, ia_provider=None):
    """Config a partir de las variables de entorno ya cargadas.

    La usan el CLI (con clientes.yaml) y las apps que integran el generador (con sus propios clientes).
    """
    salida = Path(salida_dir or os.getenv("SALIDA_DIR") or "./salida")
    if not salida.is_absolute():
        salida = RAIZ / salida
    proveedor = (ia_provider or os.getenv("IA_PROVIDER") or "").lower()
    return Config(
        odoo_url=(os.getenv("ODOO_URL") or "").rstrip("/"),
        odoo_db=os.getenv("ODOO_DB") or "",
        odoo_user=os.getenv("ODOO_USER") or "",
        odoo_password=os.getenv("ODOO_PASSWORD") or "",
        lm_api_url=(os.getenv("LM_API_URL") or "").rstrip("/"),
        lm_user=os.getenv("LM_USER") or "",
        lm_password=os.getenv("LM_PASSWORD") or "",
        ia_provider=proveedor,
        ia_model=os.getenv("IA_MODEL") or MODELOS_IA.get(proveedor, ""),
        salida_dir=salida,
        empresa={**EMPRESA, **(empresa or {})},
        clientes=list(clientes),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY") or "",
        deepseek_base_url=(os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/"),
    )


def leer_clientes_yaml(ruta=RAIZ / "clientes.yaml"):
    datos = yaml.safe_load(Path(ruta).read_text(encoding="utf-8"))
    return [Cliente.desde_dict(c) for c in datos.get("clientes", [])], datos.get("empresa", {})


def cargar_config():
    load_dotenv(RAIZ / ".env")
    clientes, empresa = leer_clientes_yaml()
    return config_desde_entorno(clientes, empresa)


def carpeta_informe(cfg, anio, mes, cliente):
    return cfg.salida_dir / f"{anio:04d}-{mes:02d}" / cliente.codigo


def nombre_archivo(anio, mes, cliente):
    return f"INFORME MENSUAL {MESES[mes].upper()} {cliente.codigo}.docx"
