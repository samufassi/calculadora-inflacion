# -*- coding: utf-8 -*-
"""
Calculadora de inflación, canasta e inversiones · Argentina (2016 - hoy)
App de Streamlit. Ejecutar localmente con:   streamlit run app.py

Archivos que necesita en la misma carpeta:
  nucleo.py · plantilla.html · data_ipc.csv · requirements.txt
Opcional:
  datos_activos.json  (copia de las cotizaciones reales; se usa solo si la descarga falla y se avisa en pantalla)
"""
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

import nucleo

BASE = Path(__file__).parent
CSV_RESPALDO = (BASE / "data_ipc.csv").read_text(encoding="utf-8")
PLANTILLA = (BASE / "plantilla.html").read_text(encoding="utf-8")
ACTIVOS_JSON = BASE / "datos_activos.json"
CACHE_HORAS = 1          # IPC
CACHE_MERCADO_MIN = 30   # activos y dólar

st.set_page_config(
    page_title="Inflación Argentina · Calculadora",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown(
    """
    <style>
      #MainMenu, footer, header, [data-testid="stHeader"], [data-testid="stToolbar"],
      [data-testid="stDecoration"], [data-testid="stStatusWidget"], .stAppDeployButton,
      [data-testid="stAppDeployButton"], [data-testid="stFooter"] {display: none !important; visibility: hidden !important;}
      .stApp {background: #080B12 !important;}
      [data-testid="stAppViewContainer"], [data-testid="stMain"] {padding-top: 0 !important;}
      .block-container, [data-testid="stMainBlockContainer"] {padding: 0 !important; max-width: 100% !important;}
      [data-testid="stVerticalBlock"] {gap: 0 !important;}
      iframe {border: 0 !important; border-radius: 0; display: block;}
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- datos (con caché)
@st.cache_data(ttl=CACHE_HORAS * 3600, show_spinner="Descargando el IPC del INDEC…")
def ipc_en_vivo():
    _, registros, origen = nucleo.armar_ipc(CSV_RESPALDO, verbose=False)
    return registros, origen


@st.cache_data(ttl=CACHE_MERCADO_MIN * 60, show_spinner="Descargando cotizaciones reales (Yahoo Finance, ArgentinaDatos, DolarApi)…")
def mercado_en_vivo():
    # Si no se descarga nada lanza una excepción, y Streamlit no guarda en caché los errores.
    return nucleo.descargar_mercado(verbose=False)


def obtener_mercado():
    """Devuelve (datos | None, fallas, estado). Descarga en el servidor; si todo falla usa datos_activos.json y lo avisa."""
    try:
        datos, fallas = mercado_en_vivo()
        return datos, fallas, "en vivo (descargado por el servidor)"
    except Exception as e:  # red, límite de Yahoo, etc.
        copia = nucleo.cargar_activos_json(ACTIVOS_JSON)
        if copia:
            return copia, {"descarga": str(e)[:160]}, f"COPIA GUARDADA del {str(copia.get('descargado', '?'))[:10]} (la descarga falló)"
        return None, {"descarga": str(e)[:160]}, "sin datos"


@st.cache_data(show_spinner=False)
def construir_html(registros, activos, inline_chartjs):
    return nucleo.generar_html(PLANTILLA, registros, activos, inline_chartjs=inline_chartjs, verbose=False)


def diagnostico(datos, fallas):
    """Filas (fuente, meses, primer mes, último mes, fecha efectiva del último dato) para el panel de fuentes."""
    filas = []
    if datos:
        for k, serie in (datos.get("px") or {}).items():
            ks = sorted(serie)
            filas.append({"Serie": nucleo.NOMBRES_ACTIVOS.get(k, k), "Fuente": datos.get("fuenteBTC") if k == "btc" else "Yahoo Finance " + nucleo.ACTIVOS_YF.get(k, ""),
                          "Meses": len(ks), "Desde": ks[0], "Hasta": ks[-1], "Último dato": serie[ks[-1]]["f"]})
        for k, serie in (datos.get("dol") or {}).items():
            ks = sorted(serie)
            filas.append({"Serie": "Dólar " + k, "Fuente": "ArgentinaDatos", "Meses": len(ks), "Desde": ks[0], "Hasta": ks[-1], "Último dato": serie[ks[-1]]["f"]})
    return filas


registros, origen_ipc = ipc_en_vivo()
activos, fallas, estado_activos = obtener_mercado()

# --------------------------------------------------------------------------- barra lateral
with st.sidebar:
    st.header("Opciones")
    alto = st.slider("Alto de la calculadora (px)", 700, 2200, 1250, step=50)
    if st.button("🔄 Actualizar datos"):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"**IPC:** {origen_ipc}")
    st.caption(f"**Mercado:** {estado_activos}")
    with st.expander("Fuentes y fechas de los datos"):
        filas = diagnostico(activos, fallas)
        if filas:
            st.dataframe(filas, hide_index=True, use_container_width=True)
        if fallas:
            st.warning("Series que no se pudieron descargar (no se reemplazan por otros valores):")
            st.json(fallas)
        st.caption("Gráficos y resultados usan el último dato disponible hasta la fecha pedida; la fecha efectiva se muestra en la tabla de trazabilidad de la pestaña Inversiones.")
    st.download_button(
        "⬇ Descargar HTML autónomo",
        data=construir_html(registros, activos, True),
        file_name="calculadora_inflacion.html",
        mime="text/html",
    )

if activos is None:
    st.warning(
        "No se pudieron descargar las cotizaciones (Yahoo Finance / ArgentinaDatos), así que la pestaña "
        "Inversiones no tiene datos por ahora: no se muestran valores inventados. Probá con «Actualizar datos» en unos minutos."
    )

components.html(construir_html(registros, activos, False), height=alto, scrolling=True)

