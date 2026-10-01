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

st.title("🤖 Procesador Definitivo de Albaranes (Modo Ultra Rápido sin Bloqueos)")

# --- BARRA LATERAL ---
st.sidebar.header("Configuración")
st.sidebar.info(f"Has usado {st.session_state.albaranes_procesados} de {LIMITE_GRATUITO} albaranes este mes.")

st.sidebar.markdown("---")
st.sidebar.info("ℹ️ Este modo utiliza extracción inteligente local ultrarrápida, eliminando por completo los errores de cuota (429) de la API.")

if st.session_state.albaranes_procesados >= LIMITE_GRATUITO:
    st.error("Has alcanzado el límite de tu plan gratuito (15 albaranes).")
    st.warning("Para continuar con albaranes ilimitados, pásate al **Plan Pro** por 19€/mes.")
else:
    archivos_subidos = st.file_uploader("Sube tus archivos PDF de albaranes aquí", type=["pdf"], accept_multiple_files=True)
    
    if archivos_subidos:
        if st.button("🚀 Procesar Definitivo por Proveedor"):
            writers_por_grupo = {}
            datos_por_grupo = {}
            
            barra_progreso = st.progress(0)
            total_archivos = len(archivos_subidos)
            
            logs_container = st.expander("🔍 Ver detalles de extracción por cada albarán", expanded=True)
            
            for idx, archivo_subido in enumerate(archivos_subidos):
                texto_completo = ""
                nombre_original = archivo_subido.name
                
                # 1. Extraer texto plano con pdfplumber
                with pdfplumber.open(archivo_subido) as pdf:
                    for pagina in pdf.pages:
                        t = pagina.extract_text(layout=False)
                        if t:
                            texto_completo += t + "\n"
                
                # Extracción inteligente local por patrones (Regex)
                proveedor = "Proveedor_Generico"
                nif_prov = "Desconocido"
                sin_iva = 0.0
                con_iva = 0.0
                
                lineas = [l.strip() for l in texto_completo.split('\n') if l.strip()]
                
                # Intentar detectar el proveedor de las primeras líneas del albarán
                if lineas:
                    # Por lo general, la primera línea con texto largo que no sea una fecha/factura es el proveedor
                    posibles_proveedores = [l for l in lineas[:5] if len(l) > 3 and not re.search(r'\d{2}/\d{2}/\d{4}', l)]
                    if posibles_proveedores:
                        proveedor = posibles_proveedores[0][:30].title() # Limitar longitud
                
                # Buscar NIF/CIF mediante expresión regular
                match_nif = re.search(r'([A-Z]\d{7,8}[A-Z0-9]|\d{8}[A-Z])', texto_completo, re.IGNORECASE)
                if match_nif:
                    nif_prov = match_nif.group(1).upper()

                # Buscar importes totales (buscando palabras clave como TOTAL, IMPORTE, etc.)
                importes = re.findall(r'(?:total|importe|a pagar|eur|\€)\D*([\d.,]+)', texto_completo, re.IGNORECASE)
                if importes:
                    try:
                        # Limpiar y convertir el último importe encontrado que suele ser el total
                        val_str = importes[-1].replace('.', '').replace(',', '.')
                        con_iva = float(val_str)
                        sin_iva = round(con_iva / 1.21, 2) # Estimación base imponible si tiene 21% IVA
                    except:
                        pass

                with logs_container:
                    st.write(f"✅ **{nombre_original}** -> Proveedor detectado: `{proveedor}` | Total: `{con_iva}€`")

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

            st.success("¡Éxito total! Albaranes clasificados, unidos por proveedor y archivo ZIP generado al instante.")
            
            st.download_button(
                label="📦 Descargar ZIP Definitivo Organizado",
                data=zip_buffer,
                file_name="albaranes_definitivos_por_proveedor.zip",
                mime="application/zip"
            )
