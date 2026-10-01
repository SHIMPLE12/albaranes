import io
import re
import zipfile
import pandas as pd
import pypdf
import streamlit as st

st.set_page_config(
    page_title="Gestor y Agrupador de Albaranes", page_icon="📄", layout="wide"
)

st.title("📄 Gestor de Albaranes por Proveedor")
st.write(
    "Sube tus albaranes. La app los agrupa y unifica automáticamente por proveedor en archivos PDF. Introduce el **Total (€)** de cada albarán directamente en la tabla de forma rápida y sencilla."
)

uploaded_files = st.file_uploader(
    "Sube tus albaranes PDF", type=["pdf"], accept_multiple_files=True
)


def extraer_texto_pdf(pdf_file):
  """Extrae el texto del PDF para detectar el nombre del proveedor."""
  texto = ""
  try:
    reader = pypdf.PdfReader(pdf_file)
    for pagina in reader.pages:
      t = pagina.extract_text()
      if t:
        texto += t + "\n"
  except Exception as e:
    pass
  return texto


def limpiar_nombre_proveedor(texto, nombre_archivo):
  """Detecta el nombre del proveedor en las primeras líneas del PDF."""
  lineas = [l.strip() for l in texto.split("\n") if l.strip()]
  ignorar = [
      "entrada",
      "albarán",
      "factura",
      "fecha",
      "página",
      "cliente",
      "nif",
      "cif",
      "dirección",
      "tel",
  ]

  proveedor_detectado = ""
  for linea in lineas[:12]:
    linea_lower = linea.lower()
    if len(linea) < 3 or linea.isdigit():
      continue
    if any(palabra in linea_lower for palabra in ignorar):
      continue
    if re.search(r"\d{2}[-/]\d{2}[-/]\d{2,4}", linea):
      continue
    proveedor_detectado = linea
    break

  if not proveedor_detectado:
    limpio = re.sub(
        r"entrada[_\-\s]*\d+[-_\d]*", "", nombre_archivo, flags=re.IGNORECASE
    )
    proveedor_detectado = limpio.replace(".pdf", "").strip()
    if not proveedor_detectado:
      proveedor_detectado = "PROVEEDOR_GENERAL"

  return (
      re.sub(r'[\\/*?:"<>|]', "", proveedor_detectado)[:35].upper().strip()
  )


if uploaded_files:
  st.success(f"¡{len(uploaded_files)} archivos cargados correctamente!")

  proveedores_pdfs = {}
  detalle_albaranes = []

  for file in uploaded_files:
    file_bytes = file.read()
    file.seek(0)

    texto = extraer_texto_pdf(io.BytesIO(file_bytes))
    proveedor = limpiar_nombre_proveedor(texto, file.name)

    # Solo guardamos Proveedor, Archivo y el Total (€)
    detalle_albaranes.append({
        "Proveedor": proveedor,
        "Archivo": file.name,
        "Total (€)": 0.0,
    })

    # Agrupar páginas físicas en el PDF unificado del proveedor
    if proveedor not in proveedores_pdfs:
      proveedores_pdfs[proveedor] = pypdf.PdfWriter()

    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    for page in reader.pages:
      proveedores_pdfs[proveedor].add_page(page)

  df_albaranes = pd.DataFrame(detalle_albaranes)

  st.subheader("✏️ Introduce los Totales Reales")
  st.write(
      "Introduce o verifica el importe total de cada albarán directamente en"
      " esta tabla."
  )

  # Tabla interactiva totalmente editable con una sola columna de importe
  df_editado = st.data_editor(df_albaranes, use_container_width=True, num_rows="fixed")

  # --- RESUMEN CONSOLIDADO POR PROVEEDOR ---
  st.subheader("📊 Resumen Consolidado por Proveedor (Para el CSV)")
  df_resumen = df_editado.groupby("Proveedor")[["Total (€)"]].sum().reset_index()
  conteo = df_editado.groupby("Proveedor").size().reset_index(name="Nº Albaranes")
  df_resumen = pd.merge(conteo, df_resumen, on="Proveedor")

  st.dataframe(df_resumen, use_container_width=True)

  # Opciones de descarga CSV
  tipo_csv = st.radio(
      "Selecciona el formato del CSV a descargar:",
      [
          "Resumen por Proveedor (Totales agrupados)",
          "Detalle completo por albarán",
      ],
      horizontal=True,
  )

  if "Resumen" in tipo_csv:
    csv_data = df_resumen.to_csv(index=False).encode("utf-8")
    nombre_csv = "resumen_albaranes_por_proveedor.csv"
  else:
    csv_data = df_editado.to_csv(index=False).encode("utf-8")
    nombre_csv = "detalle_albaranes_completo.csv"

  st.download_button(
      label="📥 Descargar CSV Definitivo",
      data=csv_data,
      file_name=nombre_csv,
      mime="text/csv",
  )

  st.divider()

  # Descargar ZIP con PDFs unidos por proveedor
  st.subheader("📦 PDFs Unidos por Proveedor")
  zip_buffer = io.BytesIO()
  with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
    for prov, writer in proveedores_pdfs.items():
      pdf_buffer = io.BytesIO()
      writer.write(pdf_buffer)
      pdf_bytes = pdf_buffer.getvalue()

      nombre_archivo_pdf = f"{prov.replace(' ', '_')}_albaranes_unidos.pdf"
      zip_file.writestr(nombre_archivo_pdf, pdf_bytes)

  zip_buffer.seek(0)

  st.download_button(
      label="📥 Descargar ZIP con PDFs Agrupados por Proveedor",
      data=zip_buffer,
      file_name="albaranes_unidos_por_proveedor.zip",
      mime="application/zip",
  )

else:
  st.info("Sube tus archivos PDF en el botón de arriba para comenzar.")
