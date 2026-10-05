import io
import json
import re
import time
import zipfile
import google.generativeai as genai
from pdf2image import convert_from_bytes
import pandas as pd
import pypdf
import streamlit as st
import plotly.express as px
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Configuración de la página
st.set_page_config(
    page_title="Gestor IA Pro de Albaranes", page_icon="🤖", layout="wide"
)

st.title("🤖 Gestor y Lector IA de Albaranes")
st.write(
    "Automatiza tu negocio. Sube los albaranes y la Inteligencia Artificial "
    "extraerá automáticamente los datos y unificará los documentos por proveedor."
)

# --- CONFIGURACIÓN INTERNA DE LA API ---
try:
    api_key_interna = st.secrets["GEMINI_API_KEY"]
except:
    api_key_interna = ""

uploaded_files = st.file_uploader(
    "Sube tus albaranes y facturas en PDF",
    type=["pdf"],
    accept_multiple_files=True,
)


def extraer_datos_con_gemini(pdf_bytes, api_key):
    """Envía el albarán optimizado a Gemini Flash de forma rápida y segura."""
    genai.configure(api_key=api_key)
    
    # Convertir la primera página a una resolución ligera (120 DPI)
    imagenes = convert_from_bytes(pdf_bytes, first_page=1, last_page=1, dpi=96)
    if not imagenes:
        return None

    imagen_pil = imagenes[0]

    prompt = (
        "Eres un asistente contable experto. Analiza este documento comercial (albarán o factura) "
        "y extrae la información en un formato JSON estricto con estas 4 claves exactas:\n"
        '{"proveedor": "Nombre de la empresa emisora", "cif": "NIF o CIF o vacio", '
        '"fecha": "DD/MM/AAAA o vacio", "total": 0.0}\n'
        "Devuelve ÚNICAMENTE el objeto JSON válido, sin bloques de código markdown ni texto adicional."
    )

    model = genai.GenerativeModel(
        model_name="gemini-3.8-flash",
        generation_config={"temperature": 0.0}
    )

    response = model.generate_content([prompt, imagen_pil])
    texto_respuesta = response.text.strip()

    # Limpiar marcas de formato markdown
    texto_respuesta = re.sub(r"^```json\s*", "", texto_respuesta)
    texto_respuesta = re.sub(r"^```\s*", "", texto_respuesta)
    texto_respuesta = re.sub(r"\s*```$", "", texto_respuesta)

    datos = json.loads(texto_respuesta)
    return datos


if uploaded_files:
    if not api_key_interna:
        st.error(
            "⚠️ Error de configuración en el servidor: No se ha detectado la clave API interna de Gemini."
        )
    else:
        st.success(
            f"¡{len(uploaded_files)} archivos listos para ser procesados por la IA!"
        )

        if st.button(
            "🚀 Procesar Albaranes con Inteligencia Artificial",
            type="primary",
        ):
            proveedores_pdfs = {}
            detalle_albaranes = []

            barra_progreso = st.progress(0)
            total_archivos = len(uploaded_files)

            for i, file in enumerate(uploaded_files):
                file_bytes = file.read()
                file.seek(0)

                resultado_ia = None
                try:
                    resultado_ia = extraer_datos_con_gemini(
                        file_bytes, api_key_interna
                    )
                except Exception as err:
                    st.error(f"No se pudo leer {file.name}. Error técnico: {err}")
                    resultado_ia = None

                if resultado_ia:
                    proveedor = (
                        str(resultado_ia.get("proveedor", "PROVEEDOR_GENERAL"))
                        .upper()
                        .strip()
                    )
                    proveedor = re.sub(r'[\\/*?:"<>|]', "", proveedor)[:35]
                    if not proveedor or proveedor == "NONE":
                        proveedor = "PROVEEDOR_GENERAL"

                    cif = str(resultado_ia.get("cif", ""))
                    fecha = str(resultado_ia.get("fecha", ""))
                    try:
                        total = float(resultado_ia.get("total", 0.0))
                    except:
                        total = 0.0
                else:
                    proveedor = "PROVEEDOR_GENERAL"
                    cif = ""
                    fecha = ""
                    total = 0.0

                detalle_albaranes.append({
                    "Proveedor": proveedor,
                    "CIF": cif,
                    "Fecha": fecha,
                    "Archivo": file.name,
                    "Total (€)": round(total, 2),
                })

                if proveedor not in proveedores_pdfs:
                    proveedores_pdfs[proveedor] = pypdf.PdfWriter()

                reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                for page in reader.pages:
                    proveedores_pdfs[proveedor].add_page(page)

                barra_progreso.progress((i + 1) / total_archivos)

            st.session_state["df_albaranes"] = pd.DataFrame(detalle_albaranes)
            st.session_state["proveedores_pdfs"] = proveedores_pdfs
            st.success("¡Procesamiento completado con éxito por la IA!")

# Secciones protegidas para evitar pantallas en blanco si no hay datos procesados
if "df_albaranes" in st.session_state and not st.session_state["df_albaranes"].empty:
    st.subheader("✏ Validación y Corrección (Datos extraídos por la IA)")
    df_editado = st.data_editor(
        st.session_state["df_albaranes"],
        use_container_width=True,
        num_rows="fixed",
    )
    st.session_state["df_resultados"] = df_editado

    st.subheader("📊 Resumen Consolidado por Proveedor")
    df_resumen = (
        df_editado.groupby("Proveedor")[["Total (€)"]].sum().reset_index()
    )
    conteo = (
        df_editado.groupby("Proveedor")
        .size()
        .reset_index(name="Nº Albaranes")
    )
    df_resumen = pd.merge(conteo, df_resumen, on="Proveedor")

    st.dataframe(df_resumen, use_container_width=True)

    st.subheader("📥 Descarga de Resultados")
    col1, col2 = st.columns(2)

    with col1:
        tipo_csv = st.radio(
            "Formato de exportación CSV:",
            [
                "Resumen por Proveedor (Totales agrupados)",
                "Detalle completo por albarán",
            ],
            horizontal=False,
        )

        if "Resumen" in tipo_csv:
            csv_data = df_resumen.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")
            nombre_csv = "resumen_contable_proveedores.csv"
        else:
            csv_data = df_editado.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")
            nombre_csv = "detalle_completo_albaranes.csv"

        st.download_button(
            label="⬇ Descargar Informe CSV Definitivo",
            data=csv_data,
            file_name=nombre_csv,
            mime="text/csv",
        )

    with col2:
        st.write("**Paquete de PDFs Agrupados:**")
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for prov, writer in st.session_state["proveedores_pdfs"].items():
                pdf_buffer = io.BytesIO()
                writer.write(pdf_buffer)
                pdf_bytes = pdf_buffer.getvalue()

                nombre_archivo_pdf = f"{prov.replace(' ', '_')}_agrupado.pdf"
                zip_file.writestr(nombre_archivo_pdf, pdf_bytes)

        zip_buffer.seek(0)
        st.download_button(
            label="📦 Descargar ZIP con PDFs por Proveedor",
            data=zip_buffer,
            file_name="albaranes_agrupados_por_proveedor.zip",
            mime="application/zip",
        )

if "df_resultados" in st.session_state and not st.session_state["df_resultados"].empty:
    st.markdown("---")
    st.subheader("📊 Análisis y Gráficos de Proveedores")
    
    col_g1, col_g2 = st.columns(2)
    df_agrupado = st.session_state["df_resultados"].groupby('Proveedor')['Total (€)'].sum().reset_index()
    
    with col_g1:
        fig_barras = px.bar(df_agrupado, x='Proveedor', y='Total (€)', title="Gasto por Proveedor")
        st.plotly_chart(fig_barras, use_container_width=True)
        
    with col_g2:
        fig_tarta = px.pie(df_agrupado, names='Proveedor', values='Total (€)', title="Porcentaje del Gasto")
        st.plotly_chart(fig_tarta, use_container_width=True)

    st.markdown("---")
    st.subheader("📥 Descargar para Contabilidad (Excel Estilizado)")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_resumen_contable = st.session_state["df_resultados"].groupby(['Proveedor', 'CIF']).agg(
            N_Facturas=('Archivo', 'count'),
            Total_Euros=('Total (€)', 'sum')
        ).reset_index()
        
        df_resumen_contable.to_excel(writer, sheet_name='Resumen Contable', index=False)
        st.session_state["df_resultados"].to_excel(writer, sheet_name='Detalle Facturas', index=False)
        
        workbook = writer.book
        header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        align_center = Alignment(horizontal="center", vertical="center")
        align_left = Alignment(horizontal="left", vertical="center")
        border_thin = Border(
            left=Side(style='thin', color='D9D9D9'),
            right=Side(style='thin', color='D9D9D9'),
            top=Side(style='thin', color='D9D9D9'),
            bottom=Side(style='thin', color='D9D9D9')
        )

        for sheetname in workbook.sheetnames:
            sheet = workbook[sheetname]
            for col_num in range(1, sheet.max_column + 1):
                cell = sheet.cell(row=1, column=col_num)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = align_center

            for col in sheet.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    if cell.value:
                        max_len = max(max_len, len(str(cell.value)))
                
                ancho_calculado = max(max_len + 5, 15)
                if col_letter == 'A':
                    ancho_calculado = max(ancho_calculado, 38)
                
                sheet.column_dimensions[col_letter].width = ancho_calculado
                for cell in col:
                    cell.border = border_thin
                    if cell.row > 1:
                        if isinstance(cell.value, (int, float)):
                            cell.alignment = Alignment(horizontal="right", vertical="center")
                        else:
                            cell.alignment = align_left

    excel_data = output.getvalue()
    st.download_button(
        label="📊 Descargar Informe Completo en Excel (.xlsx) con Estilo",
        data=excel_data,
        file_name="resumen_contable_facturas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
