import io
import json
import re
import zipfile
import google.generativeai as genai
from pdf2image import convert_from_bytes
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
    " gracias a la visión artificial de Gemini. Ideal para cobrar una"
    " suscripción mensual a empresas o gestorías."
)

uploaded_files = st.file_uploader(
    "Sube tus albaranes y facturas en PDF",
    type=["pdf"],
    accept_multiple_files=True,
)


def extraer_datos_con_gemini(pdf_bytes, api_key):
    """Envía el albarán convertido en imagen rápida a Gemini para extraer los datos."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-3.8-flash")

    # Bajamos el DPI a 110 para acelerar notablemente la conversión y subida
    imagenes = convert_from_bytes(pdf_bytes, first_page=1, last_page=1, dpi=110)
    if not imagenes:
        return None

    imagen_pil = imagenes[0]

    prompt = (
        "Analiza este documento comercial (albarán o factura). Extrae estrictamente"
        " en formato JSON puro, sin explicaciones ni bloques markdown de código"
        " (nada de ```json), exactamente con estas 4 claves:\n"
        '{"proveedor": "Nombre de la empresa emisora", "cif": "NIF o CIF o vacio", '
        '"fecha": "DD/MM/AAAA o vacio", "total": 0.0}'
    )

    response = model.generate_content([prompt, imagen_pil])
    texto_respuesta = response.text.strip()

    # Limpiar posibles marcas de formato markdown de la respuesta de la IA
    texto_respuesta = re.sub(r"^```json\s*", "", texto_respuesta)
    texto_respuesta = re.sub(r"^```\s*", "", texto_respuesta)
    texto_respuesta = re.sub(r"\s*```$", "", texto_respuesta)

    datos = json.loads(texto_respuesta)
    return datos


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

                resultado_ia = None
                try:
                    resultado_ia = extraer_datos_con_gemini(
                        file_bytes, api_key_input
                    )
                except Exception as e:
                    try:
                        genai.configure(api_key=api_key_input)
                        model_fallback = genai.GenerativeModel(
                            "gemini-2.5-flash"
                        )
                        imagenes = convert_from_bytes(
                            file_bytes, first_page=1, last_page=1, dpi=110
                        )
                        prompt = (
                            "Extrae en JSON plano con claves proveedor, cif,"
                            ' fecha, total (número): {"proveedor": "...", "cif":'
                            ' "...", "fecha": "...", "total": 0.0}'
                        )
                        resp = model_fallback.generate_content(
                            [prompt, imagenes[0]]
                        )
                        limpio = re.sub(
                            r"```json|```", "", resp.text
                        ).strip()
                        resultado_ia = json.loads(limpio)
                    except Exception as err:
                        st.error(
                            f"No se pudo leer {file.name}. Error técnico: {err}"
                        )
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

                # 2. Agrupar páginas físicas en el PDF unificado del proveedor
                if proveedor not in proveedores_pdfs:
                    proveedores_pdfs[proveedor] = pypdf.PdfWriter()

                reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                for page in reader.pages:
                    proveedores_pdfs[proveedor].add_page(page)

                # Actualizar barra de progreso
                barra_progreso.progress((i + 1) / total_archivos)

            st.session_state["df_albaranes"] = pd.DataFrame(detalle_albaranes)
            st.session_state["proveedores_pdfs"] = proveedores_pdfs
            st.success("¡Procesamiento ultrarrápido completado con éxito!")

    # Si ya se procesaron los datos, mostramos los resultados y opciones de descarga
    if "df_albaranes" in st.session_state:
        st.subheader("✏️ Validación y Corrección (Datos extraídos por la IA)")
        st.write(
            "La IA ha rellenado los campos automáticamente. Puedes verificar o"
            " corregir cualquier dato directamente en la tabla si lo necesitas."
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
                label="⬇️️ Descargar Informe CSV Definitivo",
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
