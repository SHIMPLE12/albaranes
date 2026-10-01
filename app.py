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

st.title("🤖 Procesador y Gestor Inteligente de Albaranes")

# --- BARRA LATERAL: CONFIGURACIÓN Y API GRATUITA ---
st.sidebar.header("Configuración")
st.sidebar.info(f"Has usado {st.session_state.albaranes_procesados} de {LIMITE_GRATUITO} albaranes gratuitos este mes.")

st.sidebar.markdown("---")
st.sidebar.subheader("🔑 Clave de API de Gemini (Gratis)")
st.sidebar.markdown(
    "1. Entra en [Google AI Studio](https://aistudio.google.com/)\n"
    "2. Copia tu clave gratuita.\n"
    "3. Pégala aquí abajo:"
)
api_key = st.sidebar.text_input("API Key de Gemini", type="password")

st.sidebar.markdown("---")

if st.session_state.albaranes_procesados >= LIMITE_GRATUITO:
    st.error("Has alcanzado el límite de tu plan gratuito (15 albaranes).")
    st.warning("Para continuar con albaranes ilimitados, pásate al **Plan Pro** por 19€/mes (Bizum).")
else:
    archivos_subidos = st.file_uploader("Sube tus archivos PDF de albaranes aquí", type=["pdf"], accept_multiple_files=True)
    
    if archivos_subidos:
        if not api_key:
            st.warning("⚠️ Por favor, introduce tu clave de API gratuita de Gemini en la barra lateral para continuar.")
        elif st.button("🚀 Procesar y Organizar por Proveedor"):
            client = genai.Client(api_key=api_key)
            
            writers_por_grupo = {}
            datos_por_grupo = {}
            
            barra_progreso = st.progress(0)
            total_archivos = len(archivos_subidos)
            
            for idx, archivo_subido in enumerate(archivos_subidos):
                texto_completo = ""
                
                with pdfplumber.open(archivo_subido) as pdf:
                    for pagina in pdf.pages:
                        t = pagina.extract_text(layout=False)
                        if t:
                            texto_completo += t + "\n"
                
                # Prompt estricto pidiendo exclusivamente el objeto JSON
                prompt = f"""
                Analiza el texto de este albarán y devuelve UNICAMENTE un objeto JSON válido (sin formato markdown, ni bloques de código tipo ```json, solo las llaves {{ }}):
                {{
                  "proveedor": "Nombre exacto de la empresa emisora o proveedor de arriba del todo (si no lo hay, pon 'Desconocido')",
                  "nif": "NIF o CIF del proveedor (si no lo hay, pon 'Desconocido')",
                  "fecha": "Fecha del albarán en formato DD/MM/YYYY (si no lo hay, pon 'Desconocida')",
                  "importe_sin_iva": 0.00,
                  "importe_con_iva": 0.00
                }}

                Texto del albarán:
                {texto_completo}
                """
                
                proveedor = "Desconocido"
                nif_prov = "Desconocido"
                fecha_doc = "Desconocida"
                sin_iva = 0.0
                con_iva = 0.0
                
                try:
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.1
                        ),
                    )
                    
                    texto_respuesta = response.text.strip()
                    # Limpiar posibles marcas de markdown si la IA las añade por error
                    texto_limpio = re.sub(r'^```json\s*', '', texto_respuesta)
                    texto_limpio = re.sub(r'^```\s*', '', texto_limpio)
                    texto_limpio = re.sub(r'\s*```$', '', texto_limpio)
                    
                    resultado_json = json.loads(texto_limpio)
                    proveedor = str(resultado_json.get("proveedor", "Desconocido")).strip()
                    nif_prov = str(resultado_json.get("nif", "Desconocido")).strip()
                    fecha_doc = str(resultado_json.get("fecha", "Desconocida")).strip()
                    sin_iva = float(resultado_json.get("importe_sin_iva", 0.0) or 0.0)
                    con_iva = float(resultado_json.get("importe_con_iva", 0.0) or 0.0)
                    
                except Exception as e:
                    pass

                # Criterio de agrupación inteligente en cascada
                criterio_agrupacion = proveedor
                if not proveedor or proveedor.lower() == "desconocido":
                    if nif_prov and nif_prov.lower() != "desconocido":
                        criterio_agrupacion = f"NIF_{nif_prov}"
                    else:
                        criterio_agrupacion = f"Fecha_{fecha_doc}"

                # Limpiar caracteres prohibidos para carpetas de Windows/Linux
                criterio_agrupacion = re.sub(r'[<>:"/\\|?*]', '', criterio_agrupacion).strip()
                if not criterio_agrupacion:
                    criterio_agrupacion = "Otros_Proveedores"

                # Inicializar grupo
                if criterio_agrupacion not in writers_por_grupo:
                    writers_por_grupo[criterio_agrupacion] = PdfWriter()
                    datos_por_grupo[criterio_agrupacion] = {
                        "proveedor": criterio_agrupacion,
                        "nif": nif_prov,
                        "total_albaranes": 0,
                        "suma_sin_iva": 0.0,
                        "suma_con_iva": 0.0
                    }

                # Añadir PDF físico al escritor del proveedor correspondiente
                archivo_subido.seek(0)
                writers_por_grupo[criterio_agrupacion].append(archivo_subido)
                
                # Actualizar contadores y sumas
                datos_por_grupo[criterio_agrupacion]["total_albaranes"] += 1
                datos_por_grupo[criterio_agrupacion]["suma_sin_iva"] += sin_iva
                datos_por_grupo[criterio_agrupacion]["suma_con_iva"] += con_iva
                
                st.session_state.albaranes_procesados += 1
                barra_progreso.progress((idx + 1) / total_archivos)

            # Construir filas del CSV
            filas_csv = []
            for grupo, datos in datos_por_grupo.items():
                filas_csv.append({
                    "Proveedor / Grupo": datos["proveedor"],
                    "NIF": datos["nif"],
                    "Total Albaranes": datos["total_albaranes"],
                    "Suma Sin IVA (€)": round(datos["suma_sin_iva"], 2),
                    "Suma Con IVA (€)": round(datos["suma_con_iva"], 2)
                })

            df = pd.DataFrame(filas_csv)
            csv_data = df.to_csv(index=False).encode('utf-8')
            
            # Crear archivo ZIP ordenado por carpetas y PDFs unidos por proveedor
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                zip_file.writestr("resumen_general_albaranes.csv", csv_data)
                
                for grupo, writer in writers_por_grupo.items():
                    pdf_output = io.BytesIO()
                    writer.write(pdf_output)
                    pdf_output.seek(0)
                    
                    nombre_pdf = f"{grupo}/albaranes_unidos_{grupo}.pdf"
                    zip_file.writestr(nombre_pdf, pdf_output.read())
            
            zip_buffer.seek(0)

            st.success("¡Proceso completado! Proveedores separados y PDFs unidos correctamente.")
            
            st.download_button(
                label="📦 Descargar Paquete ZIP Organizado",
                data=zip_buffer,
                file_name="albaranes_por_proveedor_con_iva.zip",
                mime="application/zip"
            )
