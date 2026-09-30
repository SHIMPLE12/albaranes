import streamlit as st
import pandas as pd
import pdfplumber

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
            # LÓGICA DE EXTRACCIÓN REAL CON PDFPLUMBER
            filas_extraidas = []
            
            with pdfplumber.open(archivo_subido) as pdf:
                for pagina in pdf.pages:
                    # Extraer texto de la página línea por línea
                    texto = pagina.extract_text()
                    lineas = texto.split('\n')
                    
                    for linea in lineas:
                        # Aquí puedes afinar el filtro según cómo aparezcan los datos en tus albaranes
                        filas_extraidas.append({
                            "Texto Detectado": linea
                        })
            
            # Si prefieres extraer tablas estructuradas directamente si el PDF las soporta:
            # (Intentamos extraer tablas de la primera página como refuerzo)
            with pdfplumber.open(archivo_subido) as pdf:
                for pagina in pdf.pages:
                    tabla = pagina.extract_table()
                    if tabla:
                        # Si encuentra tabla estructurada, la aprovechamos
                        headers = tabla[0]
                        for fila in tabla[1:]:
                            if len(fila) >= 3:
                                filas_extraidas.append({
                                    "Concepto": fila[1] if len(fila) > 1 else "N/D",
                                    "Cantidad": fila[0] if len(fila) > 0 else "N/D",
                                    "Precio": fila[2] if len(fila) > 2 else "N/D"
                                })

            # Si no ha pillado tabla estructurada por celdas, guardamos el texto plano analizado
            if not filas_extraidas:
                filas_extraidas = [{"Concepto": "Revisar PDF - Texto extraído genérico", "Cantidad": 1, "Precio": 0.0}]

            df = pd.DataFrame(filas_extraidas)
            
            # Convertir a CSV para la descarga
            csv_data = df.to_csv(index=False).encode('utf-8')
            
            # Sumar 1 al contador tras procesar con éxito
            st.session_state.albaranes_procesados += 1
            st.success("¡Albarán procesado correctamente!")
            
            # --- MOSTRAR EL BOTÓN DE DESCARGA ---
            st.download_button(
                label="📥 Descargar resultados reales (CSV)",
                data=csv_data,
                file_name="albaran_procesado.csv",
                mime="text/csv"
            )
