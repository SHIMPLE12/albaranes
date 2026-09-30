import streamlit as st
import pandas as pd
import pdfplumber
import re
from pypdf import PdfWriter
import io
import zipfile
import os

# Configurar el límite gratuito
LIMITE_GRATUITO = 15

# Inicializar contador en sesión
if 'albaranes_procesados' not in st.session_state:
    st.session_state.albaranes_procesados = 0

st.title("Procesador, Agrupador y Organizador de Albaranes")

# Mostrar consumo en la barra lateral
st.sidebar.info(f"Has usado {st.session_state.albaranes_procesados} de {LIMITE_GRATUITO} albaranes gratuitos este mes.")

# Comprobar límite gratuito
if st.session_state.albaranes_procesados >= LIMITE_GRATUITO:
    st.error("Has alcanzado el límite de tu plan gratuito (15 albaranes).")
    st.warning("Para continuar con albaranes ilimitados, pásate al **Plan Pro** por 19€/mes.")
    st.info("📲 **¿Cómo activar el Plan Pro por Bizum?**\n"
            "1. Realiza un Bizum de 19€ al teléfono de contacto.\n"
            "2. Envíanos tu comprobante y te activaremos el acceso ilimitado.")
else:
    # Subida de múltiples archivos PDF
    archivos_subidos = st.file_uploader("Sube tus archivos PDF de albaranes aquí", type=["pdf"], accept_multiple_files=True)
    
    if archivos_subidos:
        if st.button("Procesar y Organizar por Proveedor"):
            datos_globales = []
            # Diccionario para agrupar los bytes de los PDFs por su criterio de proveedor/nif/fecha
            archivos_por_grupo = {}
            
            for archivo_subido in archivos_subidos:
                texto_completo = ""
                
                # Leer PDF con pdfplumber para extracción de datos
                with pdfplumber.open(archivo_subido) as pdf:
                    for pagina in pdf.pages:
                        t = pagina.extract_text(layout=False)
                        if t:
                            texto_completo += t + "\n"
                
                lineas = [l.strip() for l in texto_completo.split('\n') if l.strip()]
                
                # 1. Extracción de Identificación (Proveedor -> NIF -> Fecha)
                proveedor = "Desconocido"
                nif_identificador = "Desconocido"
                fecha_doc = "Desconocida"
                total_importe = 0.0
                
                # Buscar Proveedor en las primeras líneas
                for linea in lineas[:6]:
                    linea_up = linea.upper()
                    if any(term in linea_up for term in ["S.L.", "S.A.", "SL", "SA", "CB", "LOGÍSTICA", "DISTRIBUCIÓN", "FOOD", "HOSTELERÍA"]):
                        proveedor = linea
                        break
                if proveedor == "Desconocido" and len(lineas) > 0:
                    proveedor = lineas[0]

                # Expresión regular para NIF/CIF y Fechas
                regex_nif = r'\b([A-HJ-NP-SU-W][0-9]{7}[0-9A-J]|[0-9]{8}[A-Z]|[A-Z][0-9]{7}[0-9A-J])\b'
                regex_fecha = r'\b(0?[1-9]|[12][0-9]|3[01])[-/.](0?[1-9]|1[012])[-/.](20[2-9][0-9])\b'

                for linea in lineas:
                    linea_upper = linea.upper()
                    
                    if "NIF" in linea_upper or "CIF" in linea_upper:
                        match_nif = re.search(regex_nif, linea)
                        if match_nif and nif_identificador == "Desconocido":
                            nif_identificador = match_nif.group(0)
                    
                    match_f = re.search(regex_fecha, linea)
                    if match_f and fecha_doc == "Desconocida":
                        fecha_doc = match_f.group(0)

                    if "TOTAL" in linea_upper and "SUBTOTAL" not in linea_upper:
                        match_importe = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2}|\d+[\.,]\d{2})', linea)
                        if match_importe:
                            imp_str = match_importe[-1].replace('.', '').replace(',', '.')
                            try:
                                val = float(imp_str)
                                if val > total_importe:
                                    total_importe = val
                            except:
                                pass

                # Lógica de agrupación en cascada solicitada: Proveedor -> si no, NIF -> si no, Fecha
                criterio_agrupacion = proveedor
                if proveedor == "Desconocido" or not proveedor:
                    if nif_identificador != "Desconocido":
                        criterio_agrupacion = f"NIF_{nif_identificador}"
                    else:
                        criterio_agrupacion = f"Fecha_{fecha_doc}"

                # Limpiar caracteres extraños en el nombre de la carpeta para evitar errores del sistema de ficheros
                criterio_agrupacion = re.sub(r'[<>:"/\\|?*]', '', criterio_agrupacion).strip()

                # Añadir a los datos del CSV resumen
                datos_globales.append({
                    "Agrupado Por": criterio_agrupacion,
                    "NIF Identificado": nif_identificador,
                    "Fecha Detectada": fecha_doc,
                    "Total Albaranes": 1,
                    "Suma Total (€)": round(total_importe, 2),
                    "Nombre Archivo Original": archivo_subido.name
                })
                
                # Almacenar el binario del PDF agrupado por su proveedor/criterio
                archivo_subido.seek(0)
                if criterio_agrupacion not in archivos_por_grupo:
                    archivos_por_grupo[criterio_agrupacion] = []
                archivos_por_grupo[criterio_agrupacion].append((archivo_subido.name, archivo_subido.read()))
                
                st.session_state.albaranes_procesados += 1

            # Crear DataFrame resumen general
            df = pd.DataFrame(datos_globales)
            csv_data = df.to_csv(index=False).encode('utf-8')
            
            # Crear archivo ZIP en memoria que contendrá las carpetas por proveedor
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                # Añadir el CSV resumen general dentro del ZIP principal
                zip_file.writestr("resumen_general_albaranes.csv", csv_data)
                
                # Crear carpetas virtuales dentro del ZIP por cada proveedor y meter sus PDFs
                for grupo, lista_archivos in archivos_por_grupo.items():
                    for nombre_original, contenido_pdf in lista_archivos:
                        # Ruta dentro del ZIP: CarpetaProveedor/nombre_archivo.pdf
                        ruta_en_zip = os.path.join(grupo, nombre_original)
                        zip_file.writestr(ruta_en_zip, contenido_pdf)
            
            zip_buffer.seek(0)

            st.success("¡Albaranes procesados y organizados por carpetas de proveedores con éxito!")
            
            # Botón único de descarga del paquete ZIP completo
            st.download_button(
                label="📦 Descargar Paquete ZIP (Carpetas por Proveedor + CSV)",
                data=zip_buffer,
                file_name="albaranes_organizados_por_proveedor.zip",
                mime="application/zip"
            )
