import streamlit as st
from google import genai
from PIL import Image
import pypdf
import io
import json
import pandas as pd
import plotly.express as px

# Configuración de la página
st.set_page_config(
    page_title="Gestor Inteligente de Albaranes y Facturas",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Gestor Inteligente de Albaranes y Facturas")
st.markdown("Procesa tus **PDFs** y **Fotos de Móvil (JPG, PNG)** de forma ultrarrápida, analiza los gastos con **gráficos** y descarga tus datos en **Excel / CSV**.")

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

    if uploaded_files:
        if st.button("🚀 Procesar Documentos", type="primary"):
            datos_tabla = []
            
            prompt_extraccion = """
            Analiza el siguiente albarán o factura y devuelve ÚNICAMENTE un objeto JSON válido con este formato estricto:
            {
                "proveedor": "Nombre de la empresa / proveedor",
                "fecha": "DD/MM/YYYY",
                "numero_factura": "Número de albarán o factura",
                "importe_total": 0.0,
                "conceptos_resumen": "Resumen de los artículos o conceptos principales"
            }
            Asegúrate de que 'importe_total' sea un número decimal puro (sin símbolos de moneda) y 'fecha' mantenga el formato DD/MM/YYYY.
            """

            for uploaded_file in uploaded_files:
                file_name = uploaded_file.name
                file_ext = file_name.split('.')[-1].lower()
                
                with st.spinner(f"Optimizando y analizando {file_name}..."):
                    try:
                        json_response = ""
                        
                        # CASO 1: Foto desde el móvil o imagen (Con compresión automática para mayor velocidad)
                        if file_ext in ['png', 'jpg', 'jpeg']:
                            imagen = Image.open(uploaded_file)
                            # Redimensionamos la imagen manteniendo la proporción (máx 1024px) para que vuele
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

                        # Limpieza del formato Markdown del JSON
                        clean_json = json_response.replace("```json", "").replace("```", "").strip()
                        parsed_data = json.loads(clean_json)
                        parsed_data["archivo"] = file_name
                        datos_tabla.append(parsed_data)

                    except Exception as e:
                        st.error(f"❌ Error procesando {file_name}: {e}")

            if datos_tabla:
                st.session_state["df_resultados"] = pd.DataFrame(datos_tabla)

    # MOSTRAR RESULTADOS, GRÁFICOS Y OPCIONES DE DESCARGA
    if "df_resultados" in st.session_state and not st.session_state["df_resultados"].empty:
        df = st.session_state["df_resultados"]

        # Convertir columna de importe a numérico por seguridad
        df["importe_total"] = pd.to_numeric(df["importe_total"], errors='coerce').fillna(0)

        st.markdown("---")
        st.subheader("📋 Resumen General de Documentos")
        
        # Métricas principales
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Documentos", len(df))
        col2.metric("Gasto Total", f"{df['importe_total'].sum():,.2f} €")
        col3.metric("Proveedores Distintos", df["proveedor"].nunique())

        # Tabla interactiva
        st.dataframe(df[["archivo", "proveedor", "fecha", "numero_factura", "importe_total", "conceptos_resumen"]], use_container_width=True)

        # SECCIÓN DE GRÁFICOS
        st.markdown("---")
        st.subheader("📈 Análisis Visión General y Gráficos")
        
        c1, c2 = st.columns(2)
        with c1:
            fig_prov = px.pie(df, names="proveedor", values="importe_total", title="Gastos por Proveedor (€)")
            st.plotly_chart(fig_prov, use_container_width=True)
            
        with c2:
            fig_bar = px.bar(df, x="proveedor", y="importe_total", color="proveedor", title="Comparativa Importe por Proveedor")
            st.plotly_chart(fig_bar, use_container_width=True)

        # DESCARGA EXCEL Y CSV
        st.markdown("---")
        st.subheader("📥 Exportación de Datos (Excel / CSV)")

        col_ex, col_csv = st.columns(2)

        # Exportar Excel (.xlsx)
        output_excel = io.BytesIO()
        with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Facturas_Albaranes')
        excel_data = output_excel.getvalue()

        col_ex.download_button(
            label="📊 Descargar Informe en Excel (.xlsx)",
            data=excel_data,
            file_name="informe_facturas_albaranes.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        # Exportar CSV
        csv_data = df.to_csv(index=False).encode('utf-8')
        col_csv.download_button(
            label="📄 Descargar Datos en CSV",
            data=csv_data,
            file_name="informe_facturas_albaranes.csv",
            mime="text/csv"
        )

        # AGRUPACIÓN POR PROVEEDOR
        st.markdown("---")
        st.subheader("📁 Agrupación y Vista por Proveedor")
        
        proveedores = df["proveedor"].unique().tolist()
        proveedor_sel = st.selectbox("Selecciona un proveedor para ver sus documentos:", proveedores)
        
        df_filtrado = df[df["proveedor"] == proveedor_sel]
        st.write(f"**Documentos asociados a {proveedor_sel}:**")
        st.table(df_filtrado[["archivo", "fecha", "numero_factura", "importe_total"]])
