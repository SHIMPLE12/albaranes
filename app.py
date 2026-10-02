import io
import json
import re
import zipfile
import google.generativeai as genai
import pandas as pd
import pypdf
import streamlit as st

# Configuración de la página
st.set_page_config(
    page_title="Gestor IA Pro de Albaranes", page_icon="🤖", layout="wide"
)

st.title("🤖 Gestor y Lector IA de Albaranes (Powered by Gemini)")
st.write(
    "Automatiza tu negocio. Sube los albaranes y la Inteligencia Artificial de"
    " Google Gemini extraerá automáticamente los datos y unificará los"
    " documentos por proveedor."
)

# --- BARRA LATERAL PARA CONFIGURAR LA API KEY ---
st.sidebar.header("🔑 Configuración de la IA")
api_key_input = st.sidebar.text_input(
    "Introduce tu clave API de Gemini:",
    type="password",
    help=(
        "Consíguela gratis en aistudio.google.com (Crea tu clave y pégala"
        " aquí)."
    ),
)

st.sidebar.info(
    "💡 **Consejo comercial:** Esta app lee los albaranes de forma autónoma"
    " gracias a la inteligencia artificial de Gemini. Ideal para cobrar una"
    " suscripción mensual a empresas o gestorías."
)

uploaded_files = st.file_uploader(
    "Sube tus albaranes y facturas en PDF",
    type=["pdf"],
    accept_multiple_files=True,
)


def extraer_texto_pdf(pdf_bytes):
    """Extrae todo el texto plano del PDF de forma tradicional."""
    texto = ""
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            t = page.extract_text()
            if t:
                texto += t + "\n"
    except Exception as e:
        print(f"Error leyendo PDF: {e}")
    return texto


def analizar_con_gemini(texto_pdf, api_key):
    """Envía el texto extraído a Gemini para que devuelva los datos estructurados en JSON."""
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        prompt = f"""
        Analiza el siguiente texto extraído de un documento comercial (albarán o factura). 
        Extrae los siguientes datos y devuélvelos en formato JSON puro (sin bloques de código markdown, solo el objeto JSON):
        {{
          "proveedor": "Nombre de la empresa emisora",
          "cif": "CIF o NIF del emisor",
          "fecha": "Fecha del documento en formato DD/MM/AAAA",
          "total": 0.0
        }}

        Texto del documento:
        {texto_pdf}
        """

        response = model.generate_content(prompt)
        texto_respuesta = response.text.strip()

        # Limpieza de formato markdown
        texto_respuesta = re.sub(r"^```json\s*", "", texto_respuesta)
        texto_respuesta = re.sub(r"^```\s*", "", texto_respuesta)
        texto_respuesta = re.sub(r"\s*```$", "", texto_respuesta)

        match = re.search(r"\{.*\}", texto_respuesta, re.DOTALL)
        if match:
            texto_respuesta = match.group(0)

        datos = json.loads(texto_respuesta)
        return datos

    except Exception as e:
        print(f"Error con Gemini: {e}")
        return None


if uploaded_files:
    if not api_key_input:
        st.error(
            "⚠️ Por favor, introduce tu Clave API de Gemini en la barra lateral"
            " izquierda para que la inteligencia artificial pueda leer los"
            " albaranes."
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

                # 1. Extraer texto del PDF
                texto_extraido = extraer_texto_pdf(file_bytes)

                # 2. Enviar texto a Gemini
                resultado_ia = None
                if texto_extraido.strip():
                    resultado_ia = analizar_con_gemini(
                        texto_extraido, api_key_input
                    )

                if resultado_ia and isinstance(resultado_ia, dict):
                    proveedor_raw = str(
                        resultado_ia.get("proveedor", "")
                    ).strip()
                    if (
                        not proveedor_raw
                        or proveedor_raw.lower() == "none"
                        or proveedor_raw == ""
                    ):
                        nombre_limpio = (
                            file.name.rsplit(".", 1)[0]
                            .replace("_", " ")
                            .replace("-", " ")
                        )
                        proveedor = (
                            nombre_limpio.upper()[:35]
                            if len(nombre_limpio) > 2
                            else "PROVEEDOR_GENERAL"
                        )
                    else:
                        proveedor = re.sub(
                            r'[\\/*?:"<>|]', "", proveedor_raw
                        ).upper()[:35]

                    cif = str(resultado_ia.get("cif", ""))
                    fecha = str(resultado_ia.get("fecha", ""))
                    try:
                        total = float(resultado_ia.get("total", 0.0))
                    except:
                        total = 0.0
                else:
                    nombre_limpio = (
                        file.name.rsplit(".", 1)[0]
                        .replace("_", " ")
                        .replace("-", " ")
                    )
                    proveedor = (
                        nombre_limpio.upper()[:35]
                        if len(nombre_limpio) > 2
                        else "PROVEEDOR_GENERAL"
                    )
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

                # Agrupar páginas físicas en el PDF unificado del proveedor
                if proveedor not in proveedores_pdfs:
                    proveedores_pdfs[proveedor] = pypdf.PdfWriter()

                reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                for page in reader.pages:
                    proveedores_pdfs[proveedor].add_page(page)

                barra_progreso.progress((i + 1) / total_archivos)

            st.session_state["df_albaranes"] = pd.DataFrame(detalle_albaranes)
            st.session_state["proveedores_pdfs"] = proveedores_pdfs
            st.success("¡Procesamiento completado con éxito!")

    if "df_albaranes" in st.session_state:
        st.subheader("✏️ Validación y Corrección (Datos extraídos por la IA)")
        st.write(
            "La IA ha procesado los documentos. Puedes verificar y ajustar"
            " cualquier campo directamente haciendo clic en las celdas de la"
            " tabla antes de realizar tus descargas."
        )

        df_editado = st.data_editor(
            st.session_state["df_albaranes"],
            use_container_width=True,
            num_rows="fixed",
        )

        # --- RESUMEN CONSOLIDADO POR PROVEEDOR ---
        st.subheader(
            "📊 Resumen Consolidado por Proveedor (Listo para Contabilidad)"
        )
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

        # Opciones de descarga
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
                csv_data = df_resumen.to_csv(index=False).encode("utf-8")
                nombre_csv = "resumen_contable_proveedores.csv"
            else:
                csv_data = df_editado.to_csv(index=False).encode("utf-8")
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

else:
    st.info(
        "👆 Sube tus albaranes y configura tu clave API de Gemini en la barra"
        " lateral para comenzar."
    )
