import streamlit as st
from google import genai
from google.genai import types
from PIL import Image
import pypdf
import io
import json
import pandas as pd
import plotly.express as px
import os
from concurrent.futures import ThreadPoolExecutor
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

# Configuración de la página
st.set_page_config(
    page_title="Gestor Inteligente de Albaranes y Facturas",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Gestor Inteligente de Albaranes y Facturas")
st.markdown("Modo Ultra-Rápido activado: extracción optimizada con IA, gráficos y exportación a Excel profesional.")

# Obtener la API Key desde las variables de entorno de Render
api_key = os.environ.get("GEMINI_API_KEY", "")

if not api_key:
    st.warning("⚠️ No se ha encontrado la clave de API (GEMINI_API_KEY) en las variables de entorno de Render.")
else:
    client = genai.Client(api_key=api_key)

    # Subida de archivos (PDF, PNG, JPG, JPEG)
    uploaded_files = st.file_uploader(
        "Sube tus albaranes y facturas (PDF, JPG, PNG):",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True
    )

    def procesar_un_archivo(uploaded_file):
        """Función optimizada para máxima velocidad y ahorro de tokens con la IA"""
        file_name = uploaded_file.name
        file_ext = file_name.split('.')[-1].lower()
        
        # Prompt ultracorto y directo para acelerar la respuesta del modelo
        prompt_extraccion = """
        Extrae de este documento y devuélvelo en formato JSON exacto:
        {
            "proveedor": "Nombre del proveedor",
            "nif_proveedor": "NIF o CIF",
            "fecha": "DD/MM/YYYY",
            "numero_factura": "Número",
            "importe_total": 0.0,
            "conceptos_resumen": "Breve resumen"
        }
        """

        # Configuración para forzar una respuesta JSON pura y evitar fallos de parseo
        config_json = types.GenerateContentConfig(
            response_mime_type="application/json"
        )

        try:
            json_response = ""
            
            # CASO 1: Imagen o foto
            if file_ext in ['png', 'jpg', 'jpeg']:
                imagen = Image.open(uploaded_file)
                # Reducimos resolución máxima a 800x800 para consumir menos recursos
                imagen.thumbnail((800, 800))
                img_byte_arr = io.BytesIO()
                imagen.convert("RGB").save(img_byte_arr, format="JPEG", quality=65)
                img_byte_arr.seek(0)
                imagen_optimizada = Image.open(img_byte_arr)
                
                response = client.models.generate_content(
                    model='gemini-2.5-flash', # Actualizado al modelo flash eficiente
                    contents=[imagen_optimizada, prompt_extraccion],
                    config=config_json
                )
                json_response = response.text

            # CASO 2: Documento PDF
            elif file_ext == 'pdf':
                pdf_reader = pypdf.PdfReader(uploaded_file)
                texto_pdf = ""
                for page in pdf_reader.pages:
                    text = page.extract_text()
                    if text:
                        texto_pdf += text + "\n"

                if texto_pdf and len(texto_pdf.strip()) > 50:
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[f"{prompt_extraccion}\n\nTexto:\n{texto_pdf}"],
                        config=config_json
                    )
                    json_response = response.text
                else:
                    from pdf2image import convert_from_bytes
                    images = convert_from_bytes(uploaded_file.read())
                    if images:
                        img_pdf = images[0]
                        img_pdf.thumbnail((800, 800))
                        response = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=[img_pdf, prompt_extraccion],
                            config=config_json
                        )
                        json_response = response.text

            parsed_data = json.loads(json_response)
            parsed_data["archivo"] = file_name
            return parsed_data

        except Exception as e:
            return {"archivo": file_name, "error": str(e)}

    if uploaded_files:
        if st.button("⚡ Procesar a Máxima Velocidad", type="primary"):
            datos_tabla = []
            
            # Procesamiento simultáneo en hilos
            with st.spinner("🚀 Leyendo documentos en paralelo... (esto puede tardar unos segundos según el número de archivos)"):
                with ThreadPoolExecutor(max_workers=4) as executor:
                    resultados = list(executor.map(procesar_un_archivo, uploaded_files))
            
            for res in resultados:
                if "error" in res:
                    st.error(f"❌ Error procesando {res['archivo']}: {res['error']}")
                else:
                    datos_tabla.append(res)

            if datos_tabla:
                st.session_state["df_resultados"] = pd.DataFrame(datos_tabla)

    # MOSTRAR RESULTADOS, TABLA EDITABLE Y DESCARGAS
    if "df_resultados" in st.session_state and not st.session_state["df_resultados"].empty:
        df_original = st.session_state["df_resultados"]

        df_original["importe_total"] = pd.to_numeric(df_original["importe_total"], errors='coerce').fillna(0.0)
        
        columnas_ordenadas = ["archivo", "proveedor", "nif_proveedor", "fecha", "numero_factura", "importe_total", "conceptos_resumen"]
        columnas_existentes = [col for col in columnas_ordenadas if col in df_original.columns]
        df_original = df_original[columnas_existentes]

        st.markdown("---")
        st.subheader("📋 Resumen General de Documentos")
        st.markdown("💡 *Puedes hacer clic en cualquier celda de la tabla inferior para corregir errores de lectura de la IA antes de exportar.*")
        
        # TABLA EDITABLE: El usuario puede corregir datos mal leídos al instante
        df = st.data_editor(
            df_original,
            use_container_width=True,
            key="editor_facturas_tabla"
        )
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Documentos", len(df))
        col2.metric("Gasto Total", f"{df['importe_total'].sum():,.2f} €")
        col3.metric("Proveedores Distintos", df["proveedor"].nunique())

        # GRÁFICOS (Basados en el DataFrame editado)
        st.markdown("---")
        st.subheader("📈 Análisis y Gráficos de Gastos")
        
        c1, c2 = st.columns(2)
        with c1:
            fig_prov = px.pie(df, names="proveedor", values="importe_total", title="Gastos por Proveedor (€)")
            st.plotly_chart(fig_prov, use_container_width=True)
            
        with c2:
            fig_bar = px.bar(df, x="proveedor", y="importe_total", color="proveedor", title="Comparativa Importe por Proveedor")
            st.plotly_chart(fig_bar, use_container_width=True)

        # EXPORTACIÓN EXCEL PROFESIONAL
        st.markdown("---")
        st.subheader("📥 Exportación de Datos Optimizada")

        col_ex, col_csv = st.columns(2)

        df_resumen_contable = df.groupby(["proveedor", "nif_proveedor"]).agg(
            N_Facturas=("numero_factura", "count"),
            Total_Euros=("importe_total", "sum")
        ).reset_index()

        output_excel = io.BytesIO()
        with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
            df_resumen_contable.to_excel(writer, index=False, sheet_name='Resumen Contable')
            df.to_excel(writer, index=False, sheet_name='Detalle Facturas')
            
            workbook = writer.book
            header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
            header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
            align_center = Alignment(horizontal="center", vertical="center")
            
            for sheetname in workbook.sheetnames:
                sheet = workbook[sheetname]
                for col_num in range(1, sheet.max_column + 1):
                    cell = sheet.cell(row=1, column=col_num)
                    cell.fill = header_fill
                    cell.font = header_font
                    cell.alignment = align_center
                
                for col in sheet.columns:
                    max_len = max(len(str(cell.value or '')) for cell in col)
                    col_letter = get_column_letter(col[0].column)
                    sheet.column_dimensions[col_letter].width = max(max_len + 4, 12)

        excel_data = output_excel.getvalue()

        col_ex.download_button(
            label="📊 Descargar Informe Excel Estilizado (.xlsx)",
            data=excel_data,
            file_name="resumen_contable_facturas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        csv_data = df.to_csv(index=False).encode('utf-8')
        col_csv.download_button(
            label="📄 Descargar Datos en CSV",
            data=csv_data,
            file_name="informe_facturas_albaranes.csv",
            mime="text/csv"
        )
