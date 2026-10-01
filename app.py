import streamlit as st
import pandas as pd
import pdfplumber
import re
import io
import zipfile
from pypdf import PdfWriter

# Configurar el límite gratuito de la app
LIMITE_GRATUITO = 15

if 'albaranes_procesados' not in st.session_state:
    st.session_state.albaranes_procesados = 0

st.title("🤖 Procesador de Albaranes: PDFs Separados por Proveedor")

# --- BARRA LATERAL ---
st.sidebar.header("Configuración")
st.sidebar.info(f"Has usado {st.session_state.albaranes_procesados} de {LIMITE_GRATUITO} albaranes este mes.")

st.sidebar.markdown("---")
st.sidebar.info("ℹ️ Cada proveedor tendrá su propia carpeta y un único PDF que unirá **únicamente** sus respectivos albaranes.")

if st.session_state.albaranes_procesados >= LIMITE_GRATUITO:
    st.error("Has alcanzado el límite de tu plan gratuito (15 albaranes).")
    st.warning("Para continuar con albaranes ilimitados, pásate al **Plan Pro** por 19€/mes.")
else:
    archivos_subidos = st.file_uploader("Sube tus archivos PDF de albaranes aquí", type=["pdf"], accept_multiple_files=True)
    
    if archivos_subidos:
        if st.button("🚀 Generar PDFs independientes por Proveedor"):
            writers_por_proveedor = {}
            datos_por_proveedor = {}
            
            barra_progreso = st.progress(0)
            total_archivos = len(archivos_subidos)
            
            logs_container = st.expander("🔍 Ver detalles de separación por proveedor", expanded=True)
            
            for idx, archivo_subido in enumerate(archivos_subidos):
                texto_completo = ""
                nombre_original = archivo_subido.name
                
                # 1. Extraer texto plano con pdfplumber
                with pdfplumber.open(archivo_subido) as pdf:
                    for pagina in pdf.pages:
                        t = pagina.extract_text(layout=False)
                        if t:
                            texto_completo += t + "\n"
                
                # Detección inteligente mejorada del proveedor
                proveedor = ""
                nif_prov = "Desconocido"
                con_iva = 0.0
                
                # Buscar palabras clave comunes de proveedores en el texto o usar el nombre del archivo si falla
                lineas = [l.strip() for l in texto_completo.split('\n') if l.strip()]
                
                # Intentar buscar la primera línea relevante que no sea numérica ni fechas
                for linea in lineas[:8]:
                    linea_limpia = linea.strip()
                    if len(linea_limpia) > 3 and not re.search(r'\d{2}/\d{2}/\d{4}', linea_limpia) and not linea_limpia.lower().startswith(('albaran', 'factura', 'fecha', 'pag:', 'cliente')):
                        proveedor = linea_limpia[:25]
                        break
                
                # Si no se encuentra en el texto, intentamos sacarlo del nombre del archivo subido
                if not proveedor or len(proveedor) < 3:
                    nombre_sin_ext = re.sub(r'\.pdf$', '', nombre_original, flags=re.IGNORECASE)
                    partes = re.split(r'[_-\s]+', nombre_sin_ext)
                    proveedor = partes[0] if partes else "Proveedor_Generico"

                # Buscar NIF/CIF
                match_nif = re.search(r'([A-Z]\d{7,8}[A-Z0-9]|\d{8}[A-Z])', texto_completo, re.IGNORECASE)
                if match_nif:
                    nif_prov = match_nif.group(1).upper()

                # Buscar importes totales
                importes = re.findall(r'(?:total|importe|a pagar|eur|\€)\D*([\d.,]+)', texto_completo, re.IGNORECASE)
                if importes:
                    try:
                        val_str = importes[-1].replace('.', '').replace(',', '.')
                        con_iva = float(val_str)
                    except:
                        pass
                
                sin_iva = round(con_iva / 1.21, 2)

                # Limpieza estricta de caracteres para nombres de carpetas
                proveedor_limpio = re.sub(r'[<>:"/\\|?*]', '', proveedor).strip().title()
                if not proveedor_limpio or proveedor_limpio.lower() in ["desconocido", "none", "null", "proveedor_generico", "albaran"]:
                    proveedor_limpio = f"Proveedor_{idx+1}"

                with logs_container:
                    st.write(f"📁 Archivo: `{nombre_original}` ➡️️ Asignado al proveedor: **{proveedor_limpio}**")

                # 2. Inicializar el escritor PDF para este proveedor específico si no existe
                if proveedor_limpio not in writers_por_proveedor:
                    writers_por_proveedor[proveedor_limpio] = PdfWriter()
                    datos_por_proveedor[proveedor_limpio] = {
                        "proveedor": proveedor_limpio,
                        "nif": nif_prov,
                        "total_albaranes": 0,
                        "suma_sin_iva": 0.0,
                        "suma_con_iva": 0.0
                    }

                # 3. Añadir este albarán UNICAMENTE al PDF de su proveedor correspondiente
                archivo_subido.seek(0)
                writers_por_proveedor[proveedor_limpio].append(archivo_subido)
                
                # Acumular datos para el CSV
                datos_por_proveedor[proveedor_limpio]["total_albaranes"] += 1
                datos_por_proveedor[proveedor_limpio]["suma_sin_iva"] += sin_iva
                datos_por_proveedor[proveedor_limpio]["suma_con_iva"] += con_iva
                
                st.session_state.albaranes_procesados += 1
                barra_progreso.progress((idx + 1) / total_archivos)

            # Construir filas del CSV final
            filas_csv = []
            for prov, datos in datos_por_proveedor.items():
                filas_csv.append({
                    "Proveedor": datos["proveedor"],
                    "NIF": datos["nif"],
                    "Total Albaranes": datos["total_albaranes"],
                    "Suma Sin IVA (€)": round(datos["suma_sin_iva"], 2),
                    "Suma Con IVA (€)": round(datos["suma_con_iva"], 2)
                })

            df = pd.DataFrame(filas_csv)
            csv_data = df.to_csv(index=False).encode('utf-8')
            
            # 4. Crear el ZIP con carpetas independientes y un PDF por cada proveedor
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                # Guardar el CSV general
                zip_file.writestr("resumen_general_albaranes.csv", csv_data)
                
                # Guardar un PDF único e independiente por cada proveedor
                for prov, writer in writers_por_proveedor.items():
                    pdf_output = io.BytesIO()
                    writer.write(pdf_output)
                    pdf_output.seek(0)
                    
                    nombre_archivo_en_zip = f"{prov}/albaranes_{prov}.pdf"
                    zip_file.writestr(nombre_archivo_en_zip, pdf_output.read())
            
            zip_buffer.seek(0)

            st.success("¡Proceso completado! Cada proveedor tiene ahora su propio PDF unificado de forma independiente.")
            
            st.download_button(
                label="📦 Descargar ZIP con PDFs Separados por Proveedor",
                data=zip_buffer,
                file_name="albaranes_separados_por_proveedor.zip",
                mime="application/zip"
            )
