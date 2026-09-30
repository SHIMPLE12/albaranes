import streamlit as st

# Configurar el nuevo límite gratuito
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
    st.warning("Actualiza al **Plan Pro** por 19€/mes para procesar albaranes de forma ilimitada.")
    
    # Aquí colocaremos el enlace o botón de pago (por ejemplo, de Stripe)
    st.link_button("Actualizar a Plan Pro (19€/mes)", "https://tu-enlace-de-pago-stripe.com")
else:
    # Zona de subida de archivos con pdfplumber
    archivo_subido = st.file_uploader("Sube tus archivos PDF aquí", type=["pdf"])
    
    if archivo_subido is not None:
        if st.button("Procesar Albarán"):
            # AQUÍ VA TU LÓGICA DE EXTRACCIÓN CON PDFPLUMBER
            # ...
            
            # Sumar 1 al contador tras procesar con éxito
            st.session_state.albaranes_procesados += 1
            st.success("¡Albarán procesado correctamente!")
