import csv
import os
import re
import pdfplumber
import streamlit as st

st.title("Procesador de Albaranes para Hostelería")
st.write(
    "Sube tus albaranes en PDF y obtén tu resumen contable al instante de"
    " forma gratuita."
)

# Creamos un selector en la web para subir varios archivos PDF a la vez
uploaded_files = st.file_uploader(
    "Sube tus archivos PDF aquí", type="pdf", accept_multiple_files=True
)

if uploaded_files:
  st.success(f"¡Se han subido {len(uploaded_files)} archivos correctamente!")

  if st.button("Procesar Albaranes"):
    resumen_proveedores = {}
    total_procesados = 0

    for uploaded_file in uploaded_files:
      try:
        # Leemos el PDF directamente desde la web
        with pdfplumber.open(uploaded_file) as pdf:
          texto_total = ""
          for pagina in pdf.pages:
            texto_total += pagina.extract_text() + "\n"
            tables = pagina.extract_tables()
            for table in tables:
              for row in table:
                row_str = " ".join([str(cell) for cell in row if cell])
                texto_total += row_str + "\n"

        match_proveedor = re.search(r"Proveedor:\s*(.*)", texto_total)
        if match_proveedor:
          proveedor_raw = match_proveedor.group(1).strip()
          proveedor = re.sub(r"^\d+\s*", "", proveedor_raw)
        else:
          proveedor = "Proveedor No Identificado"

        match_total = re.search(
            r"\b(?:Total|TOTAL|Suma)\b[\s\:\-\_]*([0-9]+(?:[.,][0-9]+)?)",
            texto_total,
        )

        if match_total:
          total_str = match_total.group(1).replace(",", ".")
          try:
            total_val = float(total_str)
          except:
            total_val = 0.0
        else:
          total_val = 0.0

        if proveedor not in resumen_proveedores:
          resumen_proveedores[proveedor] = {
              "cantidad": 0,
              "total_acumulado": 0.0,
          }

        resumen_proveedores[proveedor]["cantidad"] += 1
        resumen_proveedores[proveedor]["total_acumulado"] += total_val
        total_procesados += 1

      except Exception as e:
        st.warning(f"No se pudo leer {uploaded_file.name}: {e}")

    # Creamos el CSV en memoria para que se pueda descargar
    csv_data = "Proveedor,Total Albaranes,Suma Total\n"
    for prov, datos in resumen_proveedores.items():
      val_total = datos["total_acumulado"]
      val_formateado = (
          f"{val_total:.2f}".replace(".", ",")
          if val_total % 1 != 0
          else str(int(val_total))
      )
      csv_data += f'"{prov}",{datos["cantidad"]},{val_formateado}\n'

    st.success(
        f"¡Proceso completado con éxito! ({total_procesados} archivos leídos)"
    )

    # Botón de descarga para el usuario
    st.download_button(
        label="Descargar Resumen en Excel/CSV",
        data=csv_data,
        file_name="resultados_facturas.csv",
        mime="text/csv",
    )