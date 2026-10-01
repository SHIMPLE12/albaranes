import io
import re
import zipfile
import pandas as pd
import pypdf
import streamlit as st

st.set_page_config(
    page_title="Agrupador de Albaranes por Proveedor", page_icon="📁", layout="wide"
)

st.title("📄 Agrupador y Lector de Albaranes por Proveedor")
st.write(
    "Sube tus albaranes en PDF. La app identificará al proveedor, unirá los PDFs correspondientes de cada proveedor en un archivo individual y generará un CSV con los totales (con y sin IVA)."
)

# Cargar archivos múltiples
uploaded_files = st.file_uploader(
    "Sube tus albaranes PDF", type=["pdf"], accept_multiple_files=True
)


def extraer_texto_pdf(pdf_file):
  """Extrae el texto de un PDF."""
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


def limpiar_nombre_proveedor(texto):
  """Intenta extraer el nombre del proveedor de forma limpia desde el texto del albarán."""
  lineas = [
      l.strip()
      for l in texto.split("\n")
      if l.strip() and len(l.strip()) > 3 and not l.strip().isdigit()
  ]
  if lineas:
    # Tomamos la primera línea significativa y limpiamos caracteres raros para usarla como nombre de archivo
    proveedor = lineas[0][:30]
    proveedor = re.sub(r'[\\/*?:"<>|]', "", proveedor)  # Caracteres no válidos
    return proveedor.upper().strip()
  return "PROVEEDOR_DESCONOCIDO"


def extraer_importes(texto):
  """Extrae o estima la Base Imponible (sin IVA), el IVA y el Total con IVA."""
  sin_iva = 0.0
  iva = 0.0
  total = 0.0
  texto_lower = texto.lower()

  # Expresiones regulares para buscar importes
  patron_base = r"(?:base\s*imponible|total\s*s/iva|subtotal|neto)[\s:]*([0-9.,]+)"
  patron_iva = r"(?:cuota\s*iva|iva\s*(?:\d+%)?)[\s:]*([0-9.,]+)"
  patron_total = (
      r"(?:total\s*(?:factura|albarán|a\s*pagar)?|importe\s*total)[\s:]*([0-9.,]+)"
  )

  def limpiar_numero(val_str):
    try:
      val_str = (
          val_str.replace(".", "").replace(",", ".")
          if "." in val_str and "," in val_str
          else val_str.replace(",", ".")
      )
      return float(val_str)
    except:
      return 0.0

  match_base = re.search(patron_base, texto_lower)
  if match_base:
    sin_iva = limpiar_numero(match_base.group(1))

  match_iva = re.search(patron_iva, texto_lower)
  if match_iva:
    iva = limpiar_numero(match_iva.group(1))

  match_total = re.search(patron_total, texto_lower)
  if match_total:
    total = limpiar_numero(match_total.group(1))

  # Lógica de respaldo si faltan datos
  if total > 0 and sin_iva == 0:
    sin_iva = round(total / 1.21, 2)
    iva = round(total - sin_iva, 2)
  elif sin_iva > 0 and total == 0:
    iva = round(sin_iva * 0.21, 2)
    total = round(sin_iva + iva, 2)

  return sin_iva, iva, total


if uploaded_files:
  st.success(f"¡{len(uploaded_files)} archivos cargados correctamente!")

  # Diccionarios para agrupar
  proveedores_data = {}  # Para el CSV y métricas
  proveedores_pdfs = (
      {}
  )  # Para almacenar los objetos PdfMerger / creadores de PDF

  # Procesar cada archivo
  for file in uploaded_files:
    # Guardamos los bytes originales para pypdf
    file_bytes = file.read()
    file.seek(0)

    texto = extraer_texto_pdf(io.BytesIO(file_bytes))
    proveedor = limpiar_nombre_proveedor(texto)
    sin_iva, iva, total = extraer_importes(texto)

    # 1. Agrupar datos para el DataFrame / CSV
    if proveedor not in proveedores_data:
      proveedores_data[proveedor] = {
          "Total Sin IVA (€)": 0.0,
          "IVA (€)": 0.0,
          "Total Con IVA (€)": 0.0,
          "Cantidad Albaranes": 0,
      }

    proveedores_data[proveedor]["Total Sin IVA (€)"] += sin_iva
    proveedores_data[proveedor]["IVA (€)"] += iva
    proveedores_data[proveedor]["Total Con IVA (€)"] += total
    proveedores_data[proveedor]["Cantidad Albaranes"] += 1

    # 2. Agrupar PDFs físicos por proveedor
    if proveedor not in proveedores_pdfs:
      proveedores_pdfs[proveedor] = pypdf.PdfWriter()

    # Añadir páginas del PDF actual al escritor del proveedor correspondiente
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    for page in reader.pages:
      proveedores_pdfs[proveedor].add_page(page)

  # --- CREAR DATAFRAME Y CSV ---
  lista_filas = []
  for prov, valores in proveedores_data.items():
    lista_filas.append({
        "Proveedor": prov,
        "Albaranes": valores["Cantidad Albaranes"],
        "Total Sin IVA (€)": round(valores["Total Sin IVA (€)"], 2),
        "IVA (€)": round(valores["IVA (€)"], 2),
        "Total Con IVA (€)": round(valores["Total Con IVA (€)"], 2),
    })

  df_resultado = pd.DataFrame(lista_filas)

  st.subheader("📊 Resumen por Proveedor (Con y Sin IVA)")
  st.dataframe(df_resultado, use_container_width=True)

  # Descargar CSV
  csv_bytes = df_resultado.to_csv(index=False).encode("utf-8")
  st.download_button(
      label="📥 Descargar CSV de Totales",
      data=csv_bytes,
      file_name="resumen_albaranes_por_proveedor.csv",
      mime="text/csv",
  )

  st.divider()

  # --- CREAR ZIP CON LOS PDFS UNIDOS POR PROVEEDOR ---
  st.subheader("📦 PDFs Unidos por Proveedor")
  st.write(
      "Puedes descargar un archivo ZIP que contiene un PDF unificado por cada"
      " proveedor."
  )

  zip_buffer = io.BytesIO()
  with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
    for prov, writer in proveedores_pdfs.items():
      pdf_buffer = io.BytesIO()
      writer.write(pdf_buffer)
      pdf_bytes = pdf_buffer.getvalue()

      # Añadir cada PDF unificado al ZIP
      nombre_archivo_pdf = f"{prov.replace(' ', '_')}_unificado.pdf"
      zip_file.writestr(nombre_archivo_pdf, pdf_bytes)

  zip_buffer.seek(0)

  st.download_button(
      label="📥 Descargar ZIP con PDFs Unidos por Proveedor",
      data=zip_buffer,
      file_name="albaranes_unidos_por_proveedor.zip",
      mime="application/zip",
  )

else:
  st.info("Sube tus archivos PDF en el botón de arriba para comenzar.")
