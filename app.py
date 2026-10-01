import streamlit as st
import pandas as pd
import pdfplumber
import re
import json
import io
import zipfile
import time
from pypdf import PdfWriter
from google import genai
from google.genai import types

# Configurar el límite gratuito de la app
LIMITE_GRATUITO = 15

if 'albaranes_procesados' not in st.session_state:
    st.session_state.albaranes_procesados = 0

st.title("🤖 Procesador Definitivo de Albaranes con IA")

# --- BARRA LATERAL ---
st.sidebar.header("Configuración")
st.sidebar.info(f"Has usado {st.session_state.albaranes_procesados} de {LIMITE_GRATUITO} albaranes gratuitos este mes.")

st.sidebar.markdown("---")
st.sidebar.subheader("🔑 Clave de API de Gemini (Gratis)")
api_key = st.sidebar.text_input("API Key de Gemini", type="password")

st.sidebar.markdown("---")

if st.session_state.albaranes_procesados >= LIMITE_GRATUITO:
    st.error("Has alcanzado el límite de tu plan gratuito (15 albaranes).")
    st.warning("Para continuar con albaranes ilimitados, pásate al **Plan Pro** por 19€/mes.")
else:
    archivos_subidos = st.file_uploader("Sube tus archivos PDF de albaranes aquí", type=["pdf"], accept_multiple_files=True)
    
    if archivos_subidos:
        if not api_key:
            st.warning("⚠️ Por favor, introduce tu clave de API gratuita de Gemini en la barra lateral.")
        elif st.button("🚀 Procesar Definitivo por Proveedor"):
            client = genai.Client(api_key=api_key)
            
            writers_por_grupo = {}
            datos_por_grupo = {}
            
            barra_progreso = st.progress(0)
            total_archivos = len(archivos_subidos)
            
            logs_container = st.expander("🔍 Ver detalles de extracción por cada albarán", expanded=False)
            
            for idx, archivo_subido in enumerate(archivos_subidos):
                texto_completo = ""
                nombre_original = archivo_subido.name
                
                # 1. Extraer texto plano con pdfplumber
                with pdfplumber.open(archivo_subido) as pdf:
                    for pagina in pdf.pages:
                        t = pagina.extract_text(layout=False)
                        if t:
                            texto_completo += t + "\n"
                
                if not texto_completo.strip():
                    texto_completo = "Texto no legible directamente."

                prompt = f"""
                Eres un asistente contable experto. Analiza el texto de este albarán y extrae los siguientes datos en formato JSON puro:
                - proveedor: Nombre exacto de la empresa emisora o proveedor de arriba del todo (ej. Mercadona, Fritos S.L.). Si no lo encuentras, usa 'Proveedor_Generico'.
                - nif: NIF o CIF del proveedor. Si no hay, pon 'Desconocido'.
                - fecha: Fecha del documento en formato DD/MM/YYYY. Si no hay, pon 'Desconocida'.
                - importe_sin_iva: Número decimal (float) con la base imponible o total sin IVA (ej: 120.50). Si no hay, pon 0.0.
                - importe_con_iva: Número decimal (float) con el total final a pagar con IVA incluido (ej: 145.80). Si no hay, pon 0.0.

                Texto del albarán:
                {texto_completo}
                """
                
                proveedor = "Proveedor_Generico"
                nif_prov = "Desconocido"
                fecha_doc = "Desconocida"
                sin_iva = 0.0
                con_iva = 0.0
                
                max_intentos = 4
                
                for intento in range(max_intentos):
                    try:
                        # Usamos gemini-3.8-flash que es el modelo requerido por la API actual
                        response = client.models.generate_content(
                            model='gemini-3.8-flash',
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json",
                                temperature=0.0
                            ),
                        )
                        
                        resultado_json = json.loads(response.text)
                        proveedor = str(resultado_json.get("proveedor", "Proveedor_Generico")).strip()
                        nif_prov = str(resultado_json.get("nif", "Desconocido")).strip()
                        fecha_doc = str(resultado_json.get("fecha", "Desconocida")).strip()
                        sin_iva = float(resultado_json.get("importe_sin_iva", 0.0) or 0.0)
                        con_iva = float(resultado_json.get("importe_con_iva", 0.0) or 0.0)
                        
                        with logs_container:
                            st.write(f"✅ **{nombre_original}** -> Proveedor: `{proveedor}` | Con IVA: `{con_iva}€`")
                        break
                        
                    except Exception as e:
                        if intento < max_intentos - 1:
                            time.sleep(3 * (intento + 1))
                        else:
                            with logs_container:
                                st.write(f"⚠️ Error en {nombre_original}: {e}")

                # Limpieza estricta de caracteres para nombres de carpetas
                criterio_agrupacion = re.sub(r'[<>:"/\\|?*]', '', proveedor).strip()
                if not criterio_agrupacion or criterio_agrupacion.lower() in ["desconocido", "none", "null", "proveedor_generico"]:
                    criterio_agrupacion = "Otros_Proveedores"

                # 3. Inicializar grupo de proveedor si no existe
                if criterio_agrupacion not in writers_por_grupo:
                    writers_por_grupo[criterio_agrupacion] = PdfWriter()
                    datos_por_grupo[criterio_agrupacion] = {
                        "proveedor": criterio_agrupacion,
                        "nif": nif_prov,
                        "total_albaranes": 0,
                        "suma_sin_iva": 0.0,
                        "suma_con_iva": 0.0
                    }

                # 4. Añadir el PDF al objeto PdfWriter correspondiente a ESTE proveedor
                archivo_subido.seek(0)
                writers_por_grupo[criterio_agrupacion].append(archivo_subido)
                
                # Acumular importes
                datos_por_grupo[criterio_agrupacion]["total_albaranes"] += 1
                datos_por_grupo[criterio_agrupacion]["suma_sin_iva"] += sin_iva
                datos_por_grupo[criterio_agrupacion]["suma_con_iva"] += con_iva
                
                st.session_state.albaranes_procesados += 1
                barra_progreso.progress((idx + 1) / total_archivos)
                
                time.sleep(1)

            # Construir filas del CSV final por proveedor
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
            
            # 5. Crear el ZIP con una carpeta por proveedor y su PDF unificado dentro
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                zip_file.writestr("resumen_general_albaranes.csv", csv_data)
                
                for grupo, writer in writers_por_grupo.items():
                    pdf_output = io.BytesIO()
                    writer.write(pdf_output)
                    pdf_output.seek(0)
                    
                    nombre_pdf_en_zip = f"{grupo}/albaranes_unidos_{grupo}.pdf"
                    zip_file.writestr(nombre_pdf_en_zip, pdf_output.read())
            
            zip_buffer.seek(0)

            st.success("¡Éxito total! Proveedores separados, PDFs unidos individualmente por cada empresa y CSV calculado.")
            
            st.download_button(
                label="📦 Descargar ZIP Definitivo Organizado",
                data=zip_buffer,
                file_name="albaranes_definitivos_por_proveedor.zip",
                mime="application/zip"
            )
