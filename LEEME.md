# Publicar la calculadora en Streamlit · paso a paso (desde cero)

La app descarga **datos reales en el servidor** (Python): IPC del INDEC, S&P 500 (precio y retorno total), oro, bitcoin y dólar oficial/MEP/blue con compra y venta. Si una fuente falla, esa serie queda vacía y se avisa; nunca se inventa un valor.

## Archivos (los 6 van en la raíz del repositorio)
| Archivo | Para qué |
|---|---|
| `app.py` | La app de Streamlit |
| `nucleo.py` | Descarga y cálculos |
| `plantilla.html` | La calculadora (diseño y pestañas) |
| `data_ipc.csv` | Respaldo del IPC |
| `requirements.txt` | Librerías: streamlit, pandas, requests, yfinance |
| `.streamlit/config.toml` | Tema oscuro (carpeta `.streamlit`, archivo `config.toml`) |

## Parte A · Probarla en tu computadora (opcional, 3 minutos)
1. Descomprimí `streamlit_app.zip` en una carpeta.
2. Abrí una terminal en esa carpeta y ejecutá: `pip install -r requirements.txt`
3. Ejecutá: `streamlit run app.py` → se abre en `http://localhost:8501`.
4. En la barra lateral (flecha `>` arriba a la izquierda) abrí **Fuentes y fechas de los datos**: ahí ves qué se descargó y hasta qué fecha.

## Parte B · Publicarla (Streamlit Community Cloud, gratis)
1. **Cuenta de GitHub**: entrá a github.com (creá una cuenta si no tenés).
2. **Repositorio nuevo**: botón verde *New* → nombre `calculadora-inflacion` → *Public* → *Create repository*.
3. **Subir los archivos**: en el repositorio, *Add file → Upload files* → arrastrá `app.py`, `nucleo.py`, `plantilla.html`, `data_ipc.csv`, `requirements.txt`.
4. **Subir la carpeta de tema**: *Add file → Create new file* → en el nombre escribí `.streamlit/config.toml` (al escribir `/` se crea la carpeta) → pegá el contenido de `config.toml` → abajo, en *Commit changes*, escribí un mensaje (por ejemplo `tema`) → *Commit changes*. **El mensaje no puede estar vacío.**
5. Para los archivos del paso 3, también escribí un mensaje de commit (`primera version`) y confirmá con *Commit changes*.
6. **Desplegar**: entrá a share.streamlit.io → *Sign in with GitHub* → *Create app* → *Deploy a public app from GitHub*.
7. Completá: **Repository** `tu-usuario/calculadora-inflacion` · **Branch** `main` · **Main file path** `app.py` → *Deploy*.
8. Esperá 2–4 minutos (instala las librerías). Al terminar queda una URL del tipo `https://tu-app.streamlit.app`.

## Parte C · Compartirla sin el marco superior
Agregá `?embed=true` al final de la URL: `https://tu-app.streamlit.app/?embed=true`.
Nadie puede editar tu app: solo quien tiene permiso de escritura en tu repositorio.

## Actualizar datos
- Los datos de mercado se vuelven a descargar solos cada 30 minutos y el IPC cada 6 horas.
- Para forzarlo: barra lateral → **Actualizar datos**.
- Si cambiás un archivo en GitHub, la app se actualiza sola; si no, en la app: menú ⋮ → *Reboot app*.

## Si algo falla
| Síntoma | Qué hacer |
|---|---|
| `ModuleNotFoundError: yfinance` | Falta `requirements.txt` en la raíz o está mal escrito. |
| «No se pudieron descargar las cotizaciones» | Yahoo o ArgentinaDatos no respondieron. Esperá unos minutos y apretá **Actualizar datos**. Mirá el panel *Fuentes y fechas*. |
| Una serie dice «Sin datos» | Esa fuente falló; no se reemplaza. Reintentá más tarde. |
| Las pestañas no cambian | Estás usando una versión vieja de `plantilla.html`: subí la nueva y hacé *Reboot app*. |
| No me deja *Commit changes* | Escribí un mensaje de commit (no puede estar vacío). |

## Qué significan las fechas
Cada dato es el **último día hábil del mes** con su **fecha efectiva** (se ve en la tabla de trazabilidad de Inversiones). Si no hay cotización exacta en la fecha pedida, se usa la anterior más cercana y se avisa.
