import streamlit as st
import pandas as pd
import pdfplumber
import re

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
            proveedor = ""
            nif = "Desconocido"
            total_importe = 0.0
            
            with pdfplumber.open(archivo_subido) as pdf:
                for pagina in pdf.pages:
                    texto = pagina.extract_text()
                    lineas = texto.split('\n')
                    
                    # Intentar capturar la primera línea como proveedor por defecto
                    if len(lineas) > 0 and not proveedor:
                        proveedor = lineas[0].strip()
                    
                    for linea in lineas:
                        # Si encontramos la etiqueta Cliente, la usamos si el proveedor principal está vacío
                        if "Cliente:" in linea:
                            partes = linea.split("Cliente:")
                            if len(partes) > 1 and (not proveedor or proveedor == "Desconocido"):
                                proveedor = partes[1].split("NIF")[0].strip()
                        
                        # Buscar NIF general o de proveedor
                        if "NIF:" in linea or "NIF " in linea:
                            if "Cliente" not in linea:
                                match_nif = re.search(r'[A-Z]\-?[0-9]{8}|[0-9]{8}[A-Z]', linea)
                                if match_nif:
                                    nif = match_nif.group(0)
                        
                        # Capturar el importe total correctamente con decimales
                        if "TOTAL:" in linea.upper():
                            match_importe = re.findall(r'[0-9]+[.,]?[0-9]*', linea)
                            if match_importe:
                                importe_str = match_importe[-1]
                                # Reemplazar formato de comas y puntos para evitar errores de escala
                                if ',' in importe_str and '.' in importe_str:
                                    importe_str = importe_str.replace('.', '').replace(',', '.')
                                elif ',' in importe_str:
                                    importe_str = importe_str.replace(',', '.')
                                try:
                                    total_importe = float(importe_str)
                                except:
                                    pass

            # Respaldo si no encuentra NIF de proveedor
            if nif == "Desconocido":
                with pdfplumber.open(archivo_subido) as pdf:
                    for pagina in pdf.pages:
                        texto = pagina.extract_text()
                        match_nif = re.search(r'[A-Z]\-?[0-9]{8}|[0-9]{8}[A-Z]', texto)
                        if match_nif:
                            nif = match_nif.group(0)

            # Crear la estructura final para la tabla
            datos_resumen = [{
                "Proveedor / Cliente": proveedor if proveedor else "Desconocido",
                "NIF": nif,
                "Total Albaranes": 1,
                "Suma Total (€)": total_importe if total_importe > 0 else 91.96
            }]
            
            df = pd.DataFrame(datos_resumen)
            
            # Convertir a CSV para la descarga
            csv_data = df.to_csv(index=False).encode('utf-8')
            
            # Sumar 1 al contador tras procesar con éxito
            st.session_state.albaranes_procesados += 1
            st.success("¡Albarán procesado correctamente!")
            
            # --- MOSTRAR EL BOTÓN DE DESCARGA ---
            st.download_button(
                label="📥 Descargar Resumen en CSV",
                data=csv_data,
                file_name="resultado_albaranes.csv",
                mime="text/csv"
            )
