# -*- coding: utf-8 -*-
"""
===============================================================================
 NÚCLEO · Calculadora de inflación y activos de Argentina (2016 - actualidad)
 Materia: Programación para Economistas
===============================================================================
Funciones compartidas por el script, el notebook de Colab y la app de Streamlit:

  IPC (INDEC)  : descargar_ipc_csv -> limpiar_ipc -> empalmar_2016
                 -> calcular_variaciones -> registros_ipc
  Mercado      : descargar_mercado (Yahoo, ArgentinaDatos, DolarApi) -> DATOS_ACTIVOS
  Salida       : generar_html (arma el archivo autónomo)
  Cálculos     : inflacion_entre / simular_inversion (la misma lógica que usa la web)
"""

import datetime as dt
import io
import json
import re
import time

import pandas as pd
import requests

# ------------------------------------------------------------------------------
# CONFIGURACIÓN
# ------------------------------------------------------------------------------
SERIE_ID = "145.3_INGNACNAL_DICI_M_15"   # IPC Nacional, nivel general, base dic-2016 = 100
URL_CSV = (
    "https://apis.datos.gob.ar/series/api/series/"
    f"?ids={SERIE_ID}&format=csv&limit=1000"
)
HEADERS = {
    # Sin User-Agent, el servidor puede responder 403 Forbidden.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/csv;q=0.9,*/*;q=0.8",
}
URL_CHARTJS = "https://cdn.jsdelivr.net/npm/chart.js"

# IPCBA (Ciudad de Buenos Aires, base jul-2011/jun-2012 = 100), nivel general.
# Fuente: IDECBA, informes de resultados mensuales 2016. Se usa para empalmar
# ene-nov 2016 porque el IPC Nacional del INDEC arranca en dic-2016.
IPCBA_2016 = {
    "2016-01": 282.91, "2016-02": 294.14, "2016-03": 303.90, "2016-04": 323.79,
    "2016-05": 340.09, "2016-06": 351.05, "2016-07": 358.62, "2016-08": 355.90,
    "2016-09": 360.68, "2016-10": 371.14, "2016-11": 378.49, "2016-12": 383.19,
}
VAR_MENSUAL_ENE_2016 = 4.1   # variación publicada de enero 2016 (no hay dic-2015 en la tabla)

# Símbolos de Yahoo Finance (librería yfinance). Todos se descargan DIARIOS y se reducen al último día hábil de cada mes.
#   S&P 500 (precio) ........ ^GSPC      índice de precio, sin dividendos
#   S&P 500 (retorno total) . ^SP500TR   índice con dividendos reinvertidos (serie independiente)
#   Oro ..................... GC=F       contrato de futuros de oro (COMEX). NO es el fixing LBMA ni el spot.
#   Bitcoin ................. BTC-USD    cierre diario (UTC) en dólares
ACTIVOS_YF = {
    "sp500": "^GSPC",
    "sp500tr": "^SP500TR",
    "oro": "GC=F",
    "btc": "BTC-USD",
}
NOMBRES_ACTIVOS = {"sp500": "S&P 500 (precio)", "sp500tr": "S&P 500 (retorno total)", "oro": "Oro (futuros GC=F)", "btc": "Bitcoin"}
# Dólar en pesos: casa en ArgentinaDatos (histórico, compra y venta) y DolarApi (cotización actual).
CASAS_DOLAR = {"oficial": "oficial", "mep": "bolsa", "blue": "blue"}
URL_DOLAR_HIST = "https://api.argentinadatos.com/v1/cotizaciones/dolares/{casa}"
URL_DOLAR_SPOT = "https://dolarapi.com/v1/dolares/{casa}"
URL_BINANCE = "https://api.binance.com/api/v3/klines"
INICIO_ACTIVOS = "2015-12-01"

MARCADOR_IPC = "/*__DATOS_IPC__*/[]"
MARCADOR_ACTIVOS = "/*__DATOS_ACTIVOS__*/null"


def _impresor(verbose):
    return print if verbose else (lambda *a, **k: None)


def titulo(texto, verbose=True):
    _impresor(verbose)("\n" + "=" * 78 + f"\n {texto}\n" + "=" * 78)


# ------------------------------------------------------------------------------
# IPC · PASO 1 · IMPORTACIÓN (requests)
# ------------------------------------------------------------------------------
def descargar_ipc_csv(csv_respaldo=None, url=URL_CSV, reintentos=3, espera=2.0, verbose=True):
    """Descarga el CSV oficial. Devuelve (texto_csv, origen)."""
    p = _impresor(verbose)
    ultimo_error = None
    for intento in range(1, reintentos + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()                      # lanza error si 403/404/500
            resp.encoding = "utf-8"
            if "ipc_ng_nacional" not in resp.text:
                raise ValueError("La respuesta no contiene la columna ipc_ng_nacional")
            return resp.text, "datos.gob.ar (descarga en vivo)"
        except (requests.RequestException, ValueError) as e:
            ultimo_error = e
            p(f"  intento {intento}/{reintentos} falló: {str(e)[:160]}")
            if intento < reintentos:
                time.sleep(espera * intento)
    if csv_respaldo is None:
        raise RuntimeError(f"No se pudo descargar el IPC: {ultimo_error}")
    p("  ⚠ No se pudo descargar. Se usa la copia de respaldo de la serie.")
    return csv_respaldo, "copia de respaldo incluida en el programa"


# ------------------------------------------------------------------------------
# IPC · PASO 2 · LIMPIEZA (pandas)
# ------------------------------------------------------------------------------
def limpiar_ipc(texto_csv, verbose=True):
    p = _impresor(verbose)
    crudo = pd.read_csv(io.StringIO(texto_csv))
    p("Columnas originales:", list(crudo.columns))
    p("Filas descargadas  :", len(crudo))

    df = (
        crudo.rename(columns={"indice_tiempo": "fecha", "ipc_ng_nacional": "ipc"})
        .assign(
            fecha=lambda d: pd.to_datetime(d["fecha"], errors="coerce"),
            ipc=lambda d: pd.to_numeric(d["ipc"], errors="coerce"),
        )
        .dropna(subset=["fecha", "ipc"])          # elimina filas inválidas o vacías
        .drop_duplicates(subset="fecha")          # un valor por mes
        .sort_values("fecha")
        .set_index("fecha")
    )
    df = df[df["ipc"] > 0]

    # Continuidad: la serie debe tener un dato por cada mes, sin huecos.
    completo = df.asfreq("MS")
    faltantes = completo[completo["ipc"].isna()].index
    assert len(faltantes) == 0, f"Hay meses faltantes en la serie: {list(faltantes)}"
    assert df.index[0] == pd.Timestamp("2016-12-01"), "La serie INDEC debería arrancar en dic-2016"
    assert abs(df.iloc[0]["ipc"] - 100.0) < 1e-9, "Base dic-2016 debería ser 100"
    p(f"Serie INDEC limpia : {df.index[0]:%Y-%m} → {df.index[-1]:%Y-%m} ({len(df)} meses, sin huecos)")
    return df


# ------------------------------------------------------------------------------
# IPC · PASO 3 · EMPALME ene-nov 2016 con IPCBA
# ------------------------------------------------------------------------------
def empalmar_2016(df, verbose=True):
    p = _impresor(verbose)
    ipcba = pd.Series(IPCBA_2016)
    ipcba.index = pd.to_datetime(ipcba.index + "-01")
    base = ipcba.loc["2016-12-01"]                                     # IPCBA de dic-2016 = 383,19
    empalme = (ipcba.loc[:"2016-11-01"] / base * 100).rename("ipc")    # reescala a dic-2016 = 100
    p(f"IPCBA dic-2016 (factor de reescalado) = {base}")

    serie = pd.concat([empalme, df["ipc"]]).sort_index()
    serie = serie[~serie.index.duplicated(keep="last")]
    tabla = serie.to_frame("ipc")
    tabla["fuente"] = ["IPCBA" if f < pd.Timestamp("2016-12-01") else "INDEC" for f in tabla.index]
    tabla["ipcba"] = ipcba.reindex(tabla.index)                        # solo existe para 2016
    return tabla


# ------------------------------------------------------------------------------
# IPC · PASO 4 · VARIACIONES Y ESTADÍSTICA DESCRIPTIVA
# ------------------------------------------------------------------------------
def calcular_variaciones(tabla):
    tabla["mensual"] = tabla["ipc"].pct_change(1) * 100        # variación mensual (%)
    tabla["interanual"] = tabla["ipc"].pct_change(12) * 100    # variación interanual (%)
    tabla.loc[pd.Timestamp("2016-01-01"), "mensual"] = VAR_MENSUAL_ENE_2016
    return tabla


def estadisticas_ipc(tabla, verbose=True):
    p = _impresor(verbose)
    p(tabla[["ipc", "mensual", "interanual", "fuente"]].tail(6).round(2).to_string())
    p("\nDescriptivos de la inflación mensual (%):")
    p(tabla["mensual"].describe().round(2).to_string())
    p("\nCinco meses con mayor inflación mensual:")
    p(tabla["mensual"].nlargest(5).round(2).to_string())

    dic = tabla.loc[tabla.index.month == 12, "ipc"]
    anual = (dic.pct_change() * 100).dropna().round(1)
    anual.index = anual.index.year
    p("\nInflación anual diciembre-diciembre (%):")
    p(anual.to_string())

    factor_total = tabla["ipc"].iloc[-1] / tabla["ipc"].iloc[0]
    p(
        f"\nAcumulada {tabla.index[0]:%b-%Y} → {tabla.index[-1]:%b-%Y}: "
        f"{(factor_total - 1) * 100:,.1f}%  (factor x{factor_total:,.1f})"
    )
    # Chequeo de la composición: el índice debe coincidir con el producto de (1 + π).
    comp = (1 + tabla["mensual"].iloc[1:] / 100).prod()
    assert abs(comp - factor_total) / factor_total < 0.01, "La composición de tasas no cierra con el índice"
    p("✔ Verificación: Π(1+π_mensual) coincide con IPC_final / IPC_inicial")


def limpio(x, dec=4):
    return None if pd.isna(x) else round(float(x), dec)


def registros_ipc(tabla):
    """Lista de diccionarios para la constante DATOS_IPC del HTML."""
    return [
        {
            "periodo": fecha.strftime("%Y-%m"),
            "ipc": limpio(f["ipc"]),
            "mensual": limpio(f["mensual"]),
            "interanual": limpio(f["interanual"]),
            "fuente": f["fuente"],
            "ipcba": limpio(f["ipcba"], 2),
        }
        for fecha, f in tabla.iterrows()
    ]


def armar_ipc(csv_respaldo=None, verbose=True):
    """Ejecuta los pasos 1 a 4. Devuelve (tabla, registros, origen)."""
    titulo("IPC · Paso 1: descarga del IPC Nacional (INDEC) vía datos.gob.ar", verbose)
    texto, origen = descargar_ipc_csv(csv_respaldo, verbose=verbose)
    _impresor(verbose)(f"Origen de los datos: {origen}")
    titulo("IPC · Paso 2: limpieza y validación con pandas", verbose)
    df = limpiar_ipc(texto, verbose)
    titulo("IPC · Paso 3: empalme con IPCBA (ene-nov 2016)", verbose)
    tabla = empalmar_2016(df, verbose)
    titulo("IPC · Paso 4: variaciones (pct_change) y estadística descriptiva", verbose)
    tabla = calcular_variaciones(tabla)
    estadisticas_ipc(tabla, verbose)
    return tabla, registros_ipc(tabla), origen


# ------------------------------------------------------------------------------
# ACTIVOS Y DÓLAR · descarga real, diaria, reducida a fin de mes con fecha efectiva
# ------------------------------------------------------------------------------
def _fin_de_mes(serie_fecha_valor):
    """[(fecha 'YYYY-MM-DD', valor)] -> {'YYYY-MM': {'v': valor, 'f': fecha}} con la última observación de cada mes."""
    out = {}
    for f, v in serie_fecha_valor:
        if v is None or pd.isna(v) or float(v) <= 0:
            continue                                   # nunca se inventa ni se completa un dato faltante
        per = f[:7]
        if per not in out or f >= out[per]["f"]:
            out[per] = {"v": round(float(v), 4), "f": f}
    return dict(sorted(out.items()))


def descargar_yahoo(simbolo, inicio=INICIO_ACTIVOS):
    """Cierres diarios SIN ajustar (auto_adjust=False) de un símbolo de Yahoo Finance -> fin de mes."""
    import yfinance as yf
    h = yf.Ticker(simbolo).history(start=inicio, interval="1d", auto_adjust=False, actions=False)
    if h is None or len(h) == 0 or "Close" not in h:
        raise ValueError("Yahoo Finance no devolvió datos")
    c = h["Close"].dropna()
    idx = pd.DatetimeIndex(c.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return _fin_de_mes(list(zip([d.strftime("%Y-%m-%d") for d in idx], c.astype(float))))


def descargar_btc_binance():
    """Respaldo de Bitcoin: velas mensuales BTCUSDT de Binance (USDT, no USD). Se informa como tal."""
    r = requests.get(URL_BINANCE, params={"symbol": "BTCUSDT", "interval": "1M", "startTime": 1451606400000, "limit": 1000},
                     headers=HEADERS, timeout=30)
    r.raise_for_status()
    filas = []
    for k in r.json():
        cierre = dt.datetime.fromtimestamp(k[6] / 1000, dt.timezone.utc).date()
        filas.append((min(cierre, dt.date.today()).isoformat(), float(k[4])))
    return _fin_de_mes(filas)


def descargar_dolar_hist(tipo):
    """Cotizaciones diarias (compra y venta) de ArgentinaDatos -> fin de mes: {'YYYY-MM': {v: venta, c: compra, f: fecha}}."""
    r = requests.get(URL_DOLAR_HIST.format(casa=CASAS_DOLAR[tipo]), headers=HEADERS, timeout=40)
    r.raise_for_status()
    out = {}
    for x in r.json():
        f, v, c = str(x.get("fecha", ""))[:10], x.get("venta"), x.get("compra")
        if not f or f < "2016-01-01" or v is None or float(v) <= 0:
            continue
        per = f[:7]
        if per not in out or f >= out[per]["f"]:
            out[per] = {"v": float(v), "c": float(c) if c not in (None, 0) else None, "f": f}
    if not out:
        raise ValueError("ArgentinaDatos no devolvió cotizaciones")
    return dict(sorted(out.items()))


def descargar_dolar_spot(tipo):
    r = requests.get(URL_DOLAR_SPOT.format(casa=CASAS_DOLAR[tipo]), headers=HEADERS, timeout=20)
    r.raise_for_status()
    j = r.json()
    if not j.get("venta"):
        raise ValueError("DolarApi sin cotización")
    return {"v": float(j["venta"]), "c": float(j["compra"]) if j.get("compra") else None, "f": j.get("fechaActualizacion")}


def _con_reintentos(fn, etiqueta, fallas, reintentos, espera, p):
    for intento in range(1, reintentos + 1):
        try:
            res = fn()
            fallas.pop(etiqueta, None)
            return res
        except Exception as e:                                   # red, límite de la API, símbolo inválido...
            fallas[etiqueta] = str(e)[:160]
            p(f"  intento {intento}/{reintentos} para {etiqueta} falló: {fallas[etiqueta]}")
            if intento < reintentos:
                time.sleep(espera * intento)
    return None


def descargar_mercado(reintentos=3, espera=3.0, verbose=True):
    """
    Descarga TODO el mercado desde el servidor (Python) y devuelve (datos, fallas).
    `datos` es exactamente lo que espera DATOS_ACTIVOS en el HTML:
      px[activo][YYYY-MM] = {v: cierre, f: fecha efectiva}
      dol[tipo][YYYY-MM]  = {v: venta, c: compra, f: fecha efectiva}
      spot[tipo]          = cotización actual
    Lo que no se pueda descargar queda vacío y se informa en `fallas`: no se reemplaza por otro valor.
    """
    p = _impresor(verbose)
    px, dol, spot, fallas = {}, {}, {}, {}
    fuente_btc = "Yahoo Finance (BTC-USD)"
    for clave, simbolo in ACTIVOS_YF.items():
        serie = _con_reintentos(lambda s=simbolo: descargar_yahoo(s), simbolo, fallas, reintentos, espera, p)
        if serie is None and clave == "btc":
            serie = _con_reintentos(descargar_btc_binance, "BTCUSDT (Binance)", fallas, reintentos, espera, p)
            if serie:
                fuente_btc = "Binance (BTCUSDT, en USDT; respaldo porque Yahoo no respondió)"
        if serie:
            px[clave] = serie
            ks = list(serie)
            p(f"  ✔ {simbolo:<9} {len(serie):>4} meses  ({ks[0]} → {ks[-1]}, último dato {serie[ks[-1]]['f']})")
    for tipo in CASAS_DOLAR:
        serie = _con_reintentos(lambda t=tipo: descargar_dolar_hist(t), f"dólar {tipo}", fallas, reintentos, espera, p)
        if serie:
            dol[tipo] = serie
            ks = list(serie)
            p(f"  ✔ dólar {tipo:<8} {len(serie):>4} meses  ({ks[0]} → {ks[-1]}, último dato {serie[ks[-1]]['f']})")
        sp = _con_reintentos(lambda t=tipo: descargar_dolar_spot(t), f"dólar {tipo} (actual)", fallas, 2, 1.0, p)
        if sp:
            spot[tipo] = sp
    if not px and not dol:
        raise RuntimeError("No se pudo descargar ningún dato de mercado: " + json.dumps(fallas, ensure_ascii=False))
    datos = {
        "fuente": "Yahoo Finance (yfinance) · ArgentinaDatos · DolarApi",
        "descargado": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "tickers": ACTIVOS_YF, "fuenteBTC": fuente_btc,
        "px": px, "dol": dol, "spot": spot,
    }
    return datos, fallas


def mercado_a_df(datos):
    """Tabla mensual para análisis en Python: sp500, sp500tr, oro, btc y dólar oficial (venta y compra)."""
    cols = {k: {per: o["v"] for per, o in serie.items()} for k, serie in (datos.get("px") or {}).items()}
    of = (datos.get("dol") or {}).get("oficial", {})
    cols["ars_venta"] = {per: o["v"] for per, o in of.items()}
    cols["ars_compra"] = {per: o["c"] for per, o in of.items() if o.get("c")}
    df = pd.DataFrame(cols).sort_index()
    df.index.name = "periodo"
    return df


def activos_para_html(verbose=True):
    """Descarga y devuelve (datos_dict, df, fallas). Lanza error si no hay ningún dato."""
    titulo("MERCADO · descarga real (Yahoo Finance, ArgentinaDatos, DolarApi)", verbose)
    datos, fallas = descargar_mercado(verbose=verbose)
    return datos, mercado_a_df(datos), fallas


def guardar_activos_json(datos, ruta):
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)


def cargar_activos_json(ruta):
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            datos = json.load(f)
        return datos if (datos.get("px") or datos.get("dol")) else None
    except (OSError, ValueError):
        return None


def resumen_activos(df, verbose=True):
    """Rendimiento acumulado, anualizado y volatilidad en dólares, con las fechas efectivas del primer y último dato."""
    filas = []
    for k, nombre in NOMBRES_ACTIVOS.items():
        if k not in df:
            continue
        s = df[k].dropna()
        if len(s) < 2:
            continue
        anios = (len(s) - 1) / 12
        r = s.pct_change().dropna()
        filas.append({
            "Activo": nombre, "Desde": s.index[0], "Hasta": s.index[-1],
            "Rend. acumulado (%)": (s.iloc[-1] / s.iloc[0] - 1) * 100,
            "Rend. anualizado (%)": ((s.iloc[-1] / s.iloc[0]) ** (1 / anios) - 1) * 100,
            "Volatilidad anual (%)": r.std() * (12 ** 0.5) * 100,
        })
    out = pd.DataFrame(filas).set_index("Activo").round(1)
    _impresor(verbose)(out.to_string())
    return out


# ------------------------------------------------------------------------------
# CÁLCULOS EN PYTHON (misma lógica que la pestaña web)
# ------------------------------------------------------------------------------
def inflacion_entre(tabla, monto, origen, destino):
    """origen/destino como 'YYYY-MM'. Devuelve un dict con los 4 resultados de la calculadora."""
    io_, id_ = tabla.loc[pd.Timestamp(origen + "-01"), "ipc"], tabla.loc[pd.Timestamp(destino + "-01"), "ipc"]
    factor = id_ / io_
    return {
        "valor_actualizado": monto * factor,
        "multiplicador": factor,
        "inflacion_acumulada_pct": (factor - 1) * 100,
        "diferencia_nominal": monto * factor - monto,
        "perdida_poder_adquisitivo_pct": (1 - io_ / id_) * 100,
    }


def simular_inversion(df, tabla, monto, origen, destino, modo="ars"):
    """
    Cuánto valdría `monto` invertido en cada activo entre dos meses 'YYYY-MM' (cierres de fin de mes).
      modo='usd': V = monto × P_destino / P_origen
      modo='ars': unidades = monto / venta_origen / P_origen   (el banco te VENDE dólares)
                  V = unidades × P_destino × compra_destino    (el banco te COMPRA dólares)
    """
    o, d = df.loc[origen], df.loc[destino]
    if modo == "ars":
        venta_o, compra_d = o.get("ars_venta"), d.get("ars_compra")
        if pd.isna(venta_o) or pd.isna(compra_d):
            raise ValueError("Falta la cotización vendedora de origen o la compradora de destino")
    filas = []
    for k, nombre in NOMBRES_ACTIVOS.items():
        if k not in df or pd.isna(o[k]) or pd.isna(d[k]):
            continue
        final = monto * d[k] / o[k] if modo == "usd" else monto / venta_o / o[k] * d[k] * compra_d
        filas.append({"Activo": nombre, "Valor final": final, "Rendimiento (%)": (final / monto - 1) * 100})
    out = pd.DataFrame(filas).set_index("Activo")
    if modo == "ars":
        nec = inflacion_entre(tabla, monto, origen, destino)["valor_actualizado"]
        out["Real vs. inflación (%)"] = (out["Valor final"] / nec - 1) * 100
        out.loc["Equivalente por inflación (IPC)"] = [nec, (nec / monto - 1) * 100, 0.0]
    return out.sort_values("Rendimiento (%)", ascending=False).round(2)


# ------------------------------------------------------------------------------
# SALIDA · HTML AUTÓNOMO
# ------------------------------------------------------------------------------
def _json_para_html(obj):
    # Evita que una secuencia "</script" dentro de los datos cierre la etiqueta.
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def generar_html(plantilla, registros_ipc_, activos=None, inline_chartjs=True, verbose=True):
    """Devuelve el HTML completo (texto). `activos` es el dict de registros_activos o None."""
    p = _impresor(verbose)
    assert plantilla.count(MARCADOR_IPC) == 1, "Marcador de datos IPC no encontrado en la plantilla"
    assert plantilla.count(MARCADOR_ACTIVOS) == 1, "Marcador de datos de activos no encontrado en la plantilla"
    registros_json = "[\n" + ",\n".join("  " + _json_para_html(r) for r in registros_ipc_) + "\n]"
    html = plantilla.replace(MARCADOR_IPC, registros_json)
    html = html.replace(MARCADOR_ACTIVOS, _json_para_html(activos) if activos else "null")

    if inline_chartjs:
        try:
            r = requests.get(URL_CHARTJS, headers=HEADERS, timeout=30)
            r.raise_for_status()
            js = r.text.replace("</script", "<\\/script")
            patron = r'<script src="https://cdn\.jsdelivr\.net/npm/chart\.js".*?</script>'
            html, n = re.subn(patron, lambda m: "<script>" + js + "</script>", html, count=1, flags=re.S)
            p("Chart.js incrustado en el HTML (funciona sin conexión)." if n else "No se encontró la etiqueta de Chart.js.")
        except requests.RequestException as e:
            p(f"⚠ No se pudo incrustar Chart.js ({str(e)[:80]}); el HTML usará el CDN.")
    else:
        p("Chart.js por CDN.")
    return html
