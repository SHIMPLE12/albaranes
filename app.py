import streamlit as st
import base64
from openai import OpenAI

st.set_page_config(page_title="Gestor IA de Albaranes", layout="wide")

# Validar que la API Key exista en Secrets
if "OPENROUTER_API_KEY" not in st.secrets or not st.secrets["OPENROUTER_API_KEY"]:
    st.error("Por favor, añade OPENROUTER_API_KEY en los Secrets de Streamlit.")
    st.stop()

# Configurar cliente para OpenRouter con los headers requeridos
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=st.secrets["OPENROUTER_API_KEY"].strip(),
    default_headers={
        "HTTP-Referer": "https://streamlit.io",
        "X-Title": "Gestor de Albaranes App",
    }
)

st.title("⚡ Escáner de Albaranes (OpenRouter)")
st.write("Sube una foto del albarán para extraer los datos al instante.")

archivo = st.file_uploader("Selecciona la imagen del albarán", type=["jpg", "jpeg", "png"])

if archivo and st.button("Procesar Albarán"):
    with st.spinner("Analizando albarán..."):
        try:
            bytes_data = archivo.read()
            base64_image = base64.b64encode(bytes_data).decode('utf-8')
            mime_type = archivo.type

            completion = client.chat.completions.create(
                model="openrouter/free",
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
                                }
                            }
                        ]
                    }
                ]
            )

            resultado = completion.choices[0].message.content
            
            # Guardar el resultado en el estado de sesión para que no se borre al interactuar
            st.session_state["resultado_albaran"] = resultado
            st.session_state["nombre_archivo"] = archivo.name

        except Exception as e:
            st.error(f"Error al procesar la imagen: {str(e)}")

# Mostrar resultados y botón de descarga si ya ha sido procesado
if "resultado_albaran" in st.session_state:
    st.success("¡Albarán procesado con éxito!")
    st.markdown(st.session_state["resultado_albaran"])
    
    # Botón para descargar en formato de texto/documento estructurado
    st.download_button(
        label="📥 Descargar datos extraídos",
        data=st.session_state["resultado_albaran"],
        file_name=f"albaran_{st.session_state['nombre_archivo'].split('.')[0]}.txt",
        mime="text/plain"
    )
