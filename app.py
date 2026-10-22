import streamlit as st
import base64
from groq import Groq

st.set_page_config(page_title="Gestor IA de Albaranes - Groq", layout="wide")

# Inicializar cliente de Groq con la clave de los secrets
if "GROQ_API_KEY" in st.secrets:
    client = Groq(api_key=st.secrets["GROQ_API_KEY"])
else:
    st.error("Por favor, añade GROQ_API_KEY en los Secrets de Streamlit.")
    st.stop()

st.title("⚡ Escáner Ultra-Rápido de Albaranes (Groq)")
st.write("Sube una foto del albarán para extraer los datos al instante.")

# Subida de imagen
archivo = st.file_uploader("Selecciona la imagen del albarán", type=["jpg", "jpeg", "png"])

if archivo and st.button("Procesar Albarán"):
    with st.spinner("Analizando albarán..."):
        try:
            # Convertir imagen a base64 para el modelo de visión
            bytes_data = archivo.read()
            base64_image = base64.b64encode(bytes_data).decode('utf-8')
            mime_type = archivo.type

            # Llamada al modelo de visión de Groq
            chat_completion = client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text", 
                                "text": "Analiza este albarán y extrae de forma estructurada: Proveedor, Fecha, Número de albarán, Lista de artículos con importes y el Total."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_image}"
                                },
                            },
                        ],
                    }
                ],
                model="llama-3.2-11b-vision-instruct",
            ]

            # Mostrar el resultado obtenido
            resultado = chat_completion.choices[0].message.content
            st.success("¡Albarán procesado con éxito!")
            st.markdown(resultado)

        except Exception as e:
            st.error(f"Error al procesar la imagen: {str(e)}")
