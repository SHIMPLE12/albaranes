import streamlit as st
from google import genai
from PIL import Image
import pypdf
import io
import json
import pandas as pd
import plotly.express as px
from concurrent.futures import ThreadPoolExecutor
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Configuración de la página
st.set_page_config(
    page_title="Gestor Inteligente de Albaranes y Facturas",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Gestor Inteligente de Albaranes y Facturas")
st.markdown("Procesa tus documentos al instante, analiza gráficos y exporta a Excel con diseño profesional azul y pestañas organizadas.")

# Obtener la API Key desde los secretos
api_key = st.secrets.get("GEMINI_API_KEY", "")

if not api_key:
    st.warning("⚠️ No se ha encontrado la clave de API (GEMINI_API_KEY) en los secretos de Streamlit.")
else:
    client = genai.Client(api_key=api_key)

    # Subida de archivos (móvil y PC)
    uploaded_files = st.file_uploader(
        "Sube tus albaranes y facturas (PDF, JPG, PNG):",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True
    )

    def procesar_un_archivo(uploaded_file):
        """Función optimizada para procesar un único archivo en paralelo"""
        file_name = uploaded_file.name
        file_ext = file_name.split('.')[-1].lower()
        
        prompt_extraccion = """
        Analiza el siguiente albarán o factura y devuelve ÚNICAMENTE un objeto JSON válido con este formato estricto:
        {
            "proveedor": "Nombre de la empresa / proveedor",
            "nif_proveedor": "NIF o CIF del proveedor",
            "fecha": "DD/MM/YYYY",
            "numero_factura": "Número de albarán o factura",
            "importe_total": 0.0,
            "conceptos_resumen": "Resumen de los artículos o conceptos principales"
        }
        Asegúrate de que 'importe_total' sea un número decimal puro (sin símbolos de moneda, por ejemplo 105.27) y 'fecha' mantenga el formato DD/MM/YYYY. Si no encuentras algún dato, pon una cadena vacía "" o 0.0 para el importe.
        """

        try:
            json_response = ""
            
            # CASO 1: Imagen o foto de móvil
            if file_ext in ['png', 'jpg', 'jpeg']:
                imagen = Image.open(uploaded_file)
                imagen.thumbnail((1024, 1024))
                
                response = client.models.generate_content(
                    model='gemini-3.8-flash',
                    contents=[imagen, prompt_extraccion]
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
                    prompt_full = f"{prompt_extraccion}\n\nTexto extraído:\n{texto_pdf}"
                    response = client.models.generate_content(
                        model='gemini-3.8-flash',
                        contents=prompt_full
                    )
                    json_response = response.text
                else:
                    from pdf2image import convert_from_bytes
                    images = convert_from_bytes(uploaded_file.read())
                    if images:
                        img_pdf = images[0]
                        img_pdf.thumbnail((1024, 1024))
                        response = client.models.generate_content(
                            model='gemini-3.8-flash',
                            contents=[img_pdf, prompt_extraccion]
                        )
                        json_response = response.text

            clean_json = json_response.replace("```json", "").replace("```", "").strip()
            parsed_data = json.loads(clean_json)
            parsed_data["archivo"] = file_name
            return parsed_data

        except Exception as e:
            return {"archivo": file_name, "error": str(e)}

    if uploaded_files:
        if st.button("🚀 Procesar Documentos Ultrarrápido", type="primary"):
            datos_tabla = []
            
            with st.spinner("⚡ Procesando documentos simultáneamente con IA..."):
                with ThreadPoolExecutor(max_workers=4) as executor:
                    resultados = list(executor.map(procesar_un_archivo, uploaded_files))
            
            for res in resultados:
                if "error" in res:
                    st.error(f"❌ Error procesando {res['archivo']}: {res['error']}")
                else:
                    datos_tabla.append(res)

            if datos_tabla:
                st.session_state["df_resultados"] = pd.DataFrame(datos_tabla)

    # MOSTRAR RESULTADOS, TABLA Y DESCARGAS
    if "df_resultados" in st.session_state and not st.session_state["df_resultados"].empty:
        df = st.session_state["df_resultados"]

        df["importe_total"] = pd.to_numeric(df["importe_total"], errors='coerce').fillna(0.0)
        
        columnas_ordenadas = ["archivo", "proveedor", "nif_proveedor", "fecha", "numero_factura", "importe_total", "conceptos_resumen"]
        columnas_existentes = [col for col in columnas_ordenadas if col in df.columns]
        df = df[columnas_existentes]

        st.markdown("---")
        st.subheader("📋 Resumen General de Documentos")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Documentos", len(df))
        col2.metric("Gasto Total", f"{df['importe_total'].sum():,.2f} €")
        col3.metric("Proveedores Distintos", df["proveedor"].nunique())

        st.dataframe(df, use_container_width=True)

        # GRÁFICOS
        st.markdown("---")
        st.subheader("📈 Análisis y Gráficos de Gastos")
        
        c1, c2 = st.columns(2)
        with c1:
            fig_prov = px.pie(df, names="proveedor", values="importe_total", title="Gastos por Proveedor (€)")
            st.plotly_chart(fig_prov, use_container_width=True)
            
        with c2:
            fig_bar = px.bar(df, x="proveedor", y="importe_total", color="proveedor", title="Comparativa Importe por Proveedor")
            st.plotly_chart(fig_bar, use_container_width=True)

        # EXPORTACIÓN EXCEL PROFESIONAL CON ESTILO AZUL
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
            
            # Aplicar diseño profesional con cabecera azul
            workbook = writer.book
            header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
            header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
            align_center = Alignment(horizontal="center", vertical="center")
            
            for sheetname in workbook.sheetnames:
                sheet = workbook[sheetname]
                # Estilizar cabecera
                for col_num in range(1, sheet.max_column + 1):
                    cell = sheet.cell(row=1, column=col_num)
                    cell.fill = header_fill
                    cell.font = header_font
                    cell.alignment = align_center
                
                # Ajustar ancho de columnas automáticamente
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

        # VISTA POR PROVEEDOR
        st.markdown("---")
        st.subheader("📁 Agrupación y Vista por Proveedor")
        proveedores = df["proveedor"].unique().tolist()
        proveedor_sel = st.selectbox("Selecciona un proveedor:", proveedores)
        
        df_filtrado = df[df["proveedor"] == proveedor_sel]
        st.table(df_filtrado[["archivo", "nif_proveedor", "fecha", "numero_factura", "importe_total"]])
