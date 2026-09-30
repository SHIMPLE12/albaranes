import streamlit as st
import pandas as pd

# Configurar el límite gratuito
LIMITE_GRATUITO = 15

# Inicializar el contador en la sesión del usuario si no existe
if 'albaranes_procesados' not in st.session_state:
    st.session_state.albaranes_procesados = 0

st.title("Procesador de Albaranes para Hostelería")

# Mostrar el consumo actual al usuario en la barra lateral
st.sidebar.info(f"Has usado {st.session_state.albaranes_procesados} de {LIMITE_GRATUITO} albaranes gratuitos este mes.")

# Comprobar si ha superado el límite de 15
if st.session_state.albaranes_procesados >= LIMITE_GRATUITO:
    st.error("Has alcanzado el límite de tu plan gratuito (15 albaranes).")
    st.warning("Para continuar con albaranes ilimitados, pásate al **Plan Pro** por 19€/mes.")
    st.info("📲 **¿Cómo activar el Plan Pro?**\n"
            "1. Realiza un Bizum de 19€ al teléfono de contacto.\n"
            "2. Envíanos un correo o WhatsApp con tu comprobante y te activaremos el acceso ilimitado.")
else:
    # Zona de subida de archivos con pdfplumber
    archivo_subido = st.file_uploader("Sube tus archivos PDF aquí", type=["pdf"])
    
    if archivo_subido is not None:
        if st.button("Procesar Albarán"):
            # AQUÍ VA TU LÓGICA DE EXTRACCIÓN CON PDFPLUMBER
            # Ejemplo simulado de datos extraídos para que funcione el botón de descarga:
            datos_ejemplo = {
                "Concepto": ["Artículo extraído del albarán"],
                "Cantidad": [1],
                "Precio": [0.0]
            }
            df = pd.DataFrame(datos_ejemplo)
            
            # Convertir a CSV para la descarga
            csv_data = df.to_csv(index=False).encode('utf-8')
            
            # Sumar 1 al contador tras procesar con éxito
            st.session_state.albaranes_procesados += 1
            st.success("¡Albarán procesado correctamente!")
            
            # --- MOSTRAR EL BOTÓN DE DESCARGA ---
            st.download_button(
                label="📥 Descargar resultados (CSV)",
                data=csv_data,
                file_name="albaran_procesado.csv",
                mime="text/csv"
            )
