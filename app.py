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

st.title("🤖 Lector Estricto de Albaranes por Proveedor")

# --- BARRA LATERAL ---
st.sidebar.header("Configuración")
st.sidebar.info(f"Has usado {st.session_state.albaranes_procesados} de {LIMITE_GRATUITO} albaranes este mes.")

st.sidebar.markdown("---")
st.sidebar.info("ℹ️ Este script analiza estrictamente el texto superior de cada PDF para identificar de forma rigurosa el nombre del proveedor.")

if st.session_state.albaranes_procesados >= LIMITE_GRATUITO:
    st.error("Has alcanzado el límite de tu plan gratuito (15 albaranes).")
    st.warning("Para continuar con albaranes ilimitados, pásate al **Plan Pro** por 19€/mes.")
else:
    archivos_subidos = st.file_uploader("Sube tus archivos PDF de albaranes aquí", type=["pdf"], accept_multiple_files=True)
    
    if archivos_subidos:
        if st.button("🚀 Procesar y Agrupar Estrictamente por Proveedor"):
            writers_por_proveedor = {}
            datos_por_proveedor = {}
            
            barra_progreso = st.progress(0)
            total_archivos = len(archivos_subidos)
            
            logs_container = st.expander("🔍 Ver lectura estricta por cada albarán", expanded=True)
            
            for idx, archivo_subido in enumerate(archivos_subidos):
                lineas_utiles = []
                nombre_original = archivo_subido.name
                
                # 1. Extraer estrictamente las primeras líneas de la primera página (Cabecera del proveedor)
                with pdfplumber.open(archivo_subido) as pdf:
                    if pdf.pages:
                        # Extraer texto de la primera página con diseño
                        texto_pagina = pdf.pages[0].extract_text(layout=True)
                        if texto_pagina:
                            lineas_utiles = [l.strip() for l in texto_pagina.split('\n') if l.strip()]

                # Búsqueda estricta del proveedor en las primeras 5 líneas del albarán
                proveedor = ""
                palabras_excluidas = ["albarán", "albaran", "factura", "fecha", "pagina", "página", "cliente", "nif", "cif", "dirección", "tlf", "telefono"]
                
                for linea in lineas_utiles[:6]:
                    linea_lower = linea.lower()
                    # Ignorar líneas que sean numéricas, fechas o etiquetas comunes
                    if any(exc in linea_lower for exc in palabras_excluidas):
                        continue
                    if re.search(r'\d{2}/\d{2}/\d{4}', linea):
                        continue
                    if len(linea) > 2:
                        # Nos quedamos con la primera línea válida que representa el nombre comercial
                        proveedor = linea[:30].strip()
                        break
                
                # Si por algún motivo la cabecera está vacía, recurrimos a las primeras palabras del nombre del archivo
                if not proveedor:
                    nombre_limpio_ext = re.sub(r'\.pdf$', '', nombre_original, flags=re.IGNORECASE)
                    # Si el archivo se llama "Proveedor_01.pdf" o similar, cogemos la primera parte
                    partes_nombre = re.split(r'[_-\s]+', nombre_limpio_ext)
                    proveedor = partes_nombre[0] if partes_nombre else f"Proveedor_{idx+1}"

                # Limpieza estricta de caracteres extraños para el nombre de la carpeta/proveedor
                proveedor_estricto = re.sub(r'[<>:"/\\|?*]', '', proveedor).strip().title()
                if not proveedor_estricto or len(proveedor_estricto) < 2:
                    proveedor_estricto = f"Proveedor_Desconocido_{idx+1}"

                # Extracción de importes para el CSV de resumen
                texto_total_completo = ""
                with pdfplumber.open(archivo_subido) as pdf:
                    for p in pdf.pages:
                        t = p.extract_text()
                        if t:
                            texto_total_completo += t + "\n"

                con_iva = 0.0
                importes = re.findall(r'(?:total|importe|a pagar|eur|\€)\D*([\d.,]+)', texto_total_completo, re.IGNORECASE)
                if importes:
                    try:
                        val_str = importes[-1].replace('.', '').replace(',', '.')
                        con_iva = float(val_str)
                    except:
                        pass
                sin_iva = round(con_iva / 1.21, 2)

                # Buscar NIF
                nif_prov = "Desconocido"
                match_nif = re.search(r'([A-Z]\d{7,8}[A-Z0-9]|\d{8}[A-Z])', texto_total_completo, re.IGNORECASE)
                if match_nif:
                    nif_prov = match_nif.group(1).upper()

                with logs_container:
                    st.write(f"📄 Archivo: `{nombre_original}` ➡ Proveedor detectado estrictamente: **{proveedor_estricto}**")

                # 2. Inicializar el escritor PDF individual para este proveedor si no existe
                if proveedor_estricto not in writers_por_proveedor:
                    writers_por_proveedor[proveedor_estricto] = PdfWriter()
                    datos_por_proveedor[proveedor_estricto] = {
                        "proveedor": proveedor_estricto,
                        "nif": nif_prov,
                        "total_albaranes": 0,
                        "suma_sin_iva": 0.0,
                        "suma_con_iva": 0.0
                    }

                # 3. Añadir el PDF de forma independiente al grupo de su proveedor
                archivo_subido.seek(0)
                writers_por_proveedor[proveedor_estricto].append(archivo_subido)
                
                # Acumular datos
                datos_por_proveedor[proveedor_estricto]["total_albaranes"] += 1
                datos_por_proveedor[proveedor_estricto]["suma_sin_iva"] += sin_iva
                datos_por_proveedor[proveedor_estricto]["suma_con_iva"] += con_iva
                
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
            
            # 4. Crear el ZIP con carpetas y PDFs separados de forma independiente
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                zip_file.writestr("resumen_general_albaranes.csv", csv_data)
                
                for prov, writer in writers_por_proveedor.items():
                    pdf_output = io.BytesIO()
                    writer.write(pdf_output)
                    pdf_output.seek(0)
                    
                    nombre_archivo_en_zip = f"{prov}/albaranes_{prov}.pdf"
                    zip_file.writestr(nombre_archivo_en_zip, pdf_output.read())
            
            zip_buffer.seek(0)

            st.success("¡Proceso completado! Los albaranes se han separado estrictamente por proveedor.")
            
            st.download_button(
                label="📦 Descargar ZIP con PDFs Separados por Proveedor",
                data=zip_buffer,
                file_name="albaranes_estrictos_por_proveedor.zip",
                mime="application/zip"
            )
