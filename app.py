import streamlit as st
import pandas as pd
import pdfplumber
import re
import json
import io
import zipfile
from pypdf import PdfWriter
from google import genai
from google.genai import types

# Configurar el límite gratuito de la app
LIMITE_GRATUITO = 15

# Inicializar contador en sesión
if 'albaranes_procesados' not in st.session_state:
    st.session_state.albaranes_procesados = 0

st.title("🤖 Procesador Inteligente de Albaranes con IA")

# --- BARRA LATERAL: CONFIGURACIÓN Y API GRATUITA ---
st.sidebar.header("Configuración")
st.sidebar.info(f"Has usado {st.session_state.albaranes_procesados} de {LIMITE_GRATUITO} albaranes gratuitos este mes.")

st.sidebar.markdown("---")
st.sidebar.subheader("🔑 Clave de API de Gemini (Gratis)")
st.sidebar.markdown(
    "Para usar la IA gratis:\n"
    "1. Entra en [Google AI Studio](https://aistudio.google.com/)\n"
    "2. Inicia sesión con tu cuenta de Google.\n"
    "3. Haz clic en **Get API key** y cópiala.\n"
    "4. Pégala aquí abajo:"
)

# Campo para introducir la API Key (puedes guardarla también en Streamlit Secrets)
api_key = st.sidebar.text_input("API Key de Gemini", type="password")

st.sidebar.markdown("---")
# Comprobar límite gratuito de la app
if st.session_state.albaranes_procesados >= LIMITE_GRATUITO:
    st.error("Has alcanzado el límite de tu plan gratuito (15 albaranes).")
    st.warning("Para continuar con albaranes ilimitados, pásate al **Plan Pro** por 19€/mes (Bizum).")
else:
    # Subida de múltiples archivos PDF
    archivos_subidos = st.file_uploader("Sube tus archivos PDF de albaranes aquí", type=["pdf"], accept_multiple_files=True)
    
    if archivos_subidos:
        if not api_key:
            st.warning("⚠️ Por favor, introduce tu clave de API gratuita de Gemini en la barra lateral para poder procesar los albaranes con Inteligencia Artificial.")
        elif st.button("🚀 Procesar Albaranes con IA"):
            # Inicializar cliente de la API de Google GenAI
            client = genai.Client(api_key=api_key)
            
            datos_globales = []
            writers_por_proveedor = {}
            conteo_albaranes_por_grupo = {}
            suma_importes_por_grupo = {}
            
            barra_progreso = st.progress(0)
            total_archivos = len(archivos_subidos)
            
            for idx, archivo_subido in enumerate(archivos_subidos):
                texto_completo = ""
                
                # 1. Extraer texto plano con pdfplumber
                with pdfplumber.open(archivo_subido) as pdf:
                    for pagina in pdf.pages:
                        t = pagina.extract_text(layout=False)
                        if t:
                            texto_completo += t + "\n"
                
                # 2. Enviar el texto a la IA con un prompt estructurado
                prompt = f"""
                Analiza el siguiente texto extraído de un albarán comercial y extrae la información en formato JSON estricto (sin markdown adicional, solo el objeto JSON):
                {{
                  "proveedor": "Nombre de la empresa emisora o proveedor (si no lo encuentras, pon 'Desconocido')",
                  "nif_proveedor": "NIF o CIF del proveedor (si no lo hay, pon 'Desconocido')",
                  "fecha": "Fecha del albarán en formato DD/MM/YYYY (si no lo hay, pon 'Desconocida')",
                  "importe_total": 0.00
                }}

                Texto del albarán:
                {texto_completo}
                """
                
                try:
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.1
                        ),
                    )
                    
                    resultado_json = json.loads(response.text)
                    proveedor = resultado_json.get("proveedor", "Desconocido").strip()
                    nif_prov = resultado_json.get("nif_proveedor", "Desconocido").strip()
                    fecha_doc = resultado_json.get("fecha", "Desconocida").strip()
                    total_importe = float(resultado_json.get("importe_total", 0.0))
                    
                except Exception as e:
                    # Respaldo de seguridad si ocurre algún error de conexión puntual
                    proveedor = "Desconocido"
                    nif_prov = "Desconocido"
                    fecha_doc = "Desconocida"
                    total_importe = 0.0

                # 3. Lógica de agrupación en cascada: Proveedor -> si no, NIF -> si no, Fecha
                criterio_agrupacion = proveedor
                if proveedor == "Desconocido" or not proveedor:
                    if nif_prov != "Desconocido":
                        criterio_agrupacion = f"NIF_{nif_prov}"
                    else:
                        criterio_agrupacion = f"Fecha_{fecha_doc}"

                # Limpiar caracteres prohibidos en nombres de carpetas
                criterio_agrupacion = re.sub(r'[<>:"/\\|?*]', '', criterio_agrupacion).strip()

                # Acumular para el CSV resumen
                if criterio_agrupacion not in conteo_albaranes_por_grupo:
                    conteo_albaranes_por_grupo[criterio_agrupacion] = 0
                    suma_importes_por_grupo[criterio_agrupacion] = 0.0
                
                conteo_albaranes_por_grupo[criterio_agrupacion] += 1
                suma_importes_por_grupo[criterio_agrupacion] += total_importe

                # 4. Fusionar PDFs físicos por proveedor
                if criterio_agrupacion not in writers_por_proveedor:
                    writers_por_proveedor[criterio_agrupacion] = PdfWriter()
                
                archivo_subido.seek(0)
                writers_por_proveedor[criterio_agrupacion].append(archivo_subido)
                
                st.session_state.albaranes_procesados += 1
                barra_progreso.progress((idx + 1) / total_archivos)

            # Rellenar datos para el DataFrame global
            for grupo in conteo_albaranes_por_grupo:
                datos_globales.append({
                    "Agrupado Por": grupo,
                    "Total Albaranes": conteo_albaranes_por_grupo[grupo],
                    "Suma Total (€)": round(suma_importes_por_grupo[grupo], 2)
                })

            df = pd.DataFrame(datos_globales)
            csv_data = df.to_csv(index=False).encode('utf-8')
            
            # 5. Crear el archivo ZIP con carpetas organizadas y PDFs unidos
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                zip_file.writestr("resumen_general_albaranes.csv", csv_data)
                
                for grupo, writer in writers_por_proveedor.items():
                    pdf_output = io.BytesIO()
                    writer.write(pdf_output)
                    pdf_output.seek(0)
                    nombre_archivo_pdf = f"{grupo}/albaranes_unidos_{grupo}.pdf"
                    zip_file.writestr(nombre_archivo_pdf, pdf_output.read())
            
            zip_buffer.seek(0)

            st.success("¡Proceso completado con Inteligencia Artificial con éxito!")
            
            # Botón de descarga del paquete ZIP
            st.download_button(
                label="📦 Descargar ZIP Inteligente (Carpetas + PDFs Unidos + CSV)",
                data=zip_buffer,
                file_name="albaranes_inteligentes_organizados.zip",
                mime="application/zip"
            )
