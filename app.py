import streamlit as st
from google import genai
from google.genai import types
from PIL import Image
import pypdf
import io
import json

# Configuración de la página
st.set_page_config(
    page_title="Gestor IA Albaranes y Facturas",
    page_icon="📄",
    layout="wide"
)

st.title("📄 Gestor Inteligente de Albaranes y Facturas")
st.markdown("Sube tus documentos en **PDF** o hazles una **foto con el móvil** (JPG, PNG) para extraer los datos automáticamente.")

# Configuración de la API de Gemini (asegúrate de tener tu API Key en los Secrets o cárgala aquí)
# st.secrets["GEMINI_API_KEY"]
api_key = st.secrets.get("GEMINI_API_KEY", "")

if not api_key:
    st.warning("⚠️ No se ha encontrado la clave de API en los secretos de Streamlit. Por favor, configúrala.")
else:
    # Inicializar el cliente oficial de Google GenAI
    client = genai.Client(api_key=api_key)

    # Componente de subida de archivos (admite PDF y fotos de móvil)
    uploaded_files = st.file_uploader(
        "Sube tus archivos (PDF, PNG, JPG, JPEG):",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True
    )

    if uploaded_files:
        if st.button("🚀 Procesar Documentos"):
            resultados = []
            
            # Prompt estructurado para la IA
            prompt_extraccion = (
                "Extrae los datos clave de este albarán o factura en formato JSON estricto "
                "con las siguientes claves: 'proveedor', 'fecha', 'numero_factura', 'importe_total', 'conceptos'."
            )

            for uploaded_file in uploaded_files:
                file_name = uploaded_file.name
                file_extension = file_name.split('.')[-1].lower()
                
                with st.spinner(f"Procesando: {file_name}..."):
                    try:
                        response_text = ""
                        
                        # CASO 1: Es una imagen (foto de móvil, JPG, PNG)
                        if file_extension in ['png', 'jpg', 'jpeg']:
                            imagen = Image.open(uploaded_file)
                            response = client.models.generate_content(
                                model='gemini-2.5-flash',
                                contents=[imagen, prompt_extraccion]
                            )
                            response_text = response.text

                        # CASO 2: Es un archivo PDF
                        elif file_extension == 'pdf':
                            pdf_reader = pypdf.PdfReader(uploaded_file)
                            texto_pdf = ""
                            for page in pdf_reader.pages:
                                text = page.extract_text()
                                if text:
                                    texto_pdf += text + "\n"

                            # Si el PDF tiene texto nativo suficiente, usamos vía rápida (texto)
                            if texto_pdf and len(texto_pdf.strip()) > 50:
                                prompt_con_texto = f"{prompt_extraccion}\n\nTexto del documento:\n{texto_pdf}"
                                response = client.models.generate_content(
                                    model='gemini-2.5-flash',
                                    contents=prompt_con_texto
                                )
                                response_text = response.text
                            else:
                                # Si es un PDF escaneado (imagen), avisamos o tratamos
                                st.info(f"ℹ️ El PDF '{file_name}' parece escaneado. Convirtiendo para lectura visual...")
                                # Aquí puedes añadir la conversión a imagen si lo deseas, o dejar que la IA lo procese
                                from pdf2image import convert_from_bytes
                                images = convert_from_bytes(uploaded_file.read())
                                if images:
                                    response = client.models.generate_content(
                                        model='gemini-2.5-flash',
                                        contents=[images[0], prompt_extraccion]
                                    )
                                    response_text = response.text

                        # Guardar el resultado para la tabla final
                        resultados.append({
                            "Archivo": file_name,
                            "Resultado JSON / Datos": response_text
                        })
                        
                    except Exception as e:
                        st.error(f"❌ Error al procesar {file_name}: {e}")

            if resultados:
                st.success("✅ ¡Proceso completado con éxito!")
                st.subheader("Resultados extraídos:")
                for res in resultados:
                    with st.expander(f"📁 {res['Archivo']}"):
                        st.code(res['Resultado JSON'], language='json')
