archivo_subido = st.file_uploader("Sube tus archivos PDF aquí", type=["pdf"])
    
    if archivo_subido is not None:
        if st.button("Procesar Albarán"):
            # AQUÍ VA TU LÓGICA DE EXTRACCIÓN CON PDFPLUMBER
            # Supongamos que guardas los datos extraídos en una variable llamada 'df' (un DataFrame de Pandas)
            # df = tu_funcion_extraccion(archivo_subido)
            
            # Sumar 1 al contador tras procesar con éxito
            st.session_state.albaranes_procesados += 1
            st.success("¡Albarán procesado correctamente!")
            
            # --- AÑADE ESTO PARA QUE APAREZCA EL BOTÓN DE DESCARGA ---
            # Convertir tus datos a CSV (o Excel) para la descarga:
            # csv = df.to_csv(index=False).encode('utf-8')
            
            # st.download_button(
            #     label="📥 Descargar Excel / CSV con los datos",
            #     data=csv,
            #     file_name="albaran_extraido.csv",
            #     mime="text/csv",
            # )
