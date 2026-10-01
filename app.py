import io
import re
import zipfile
import pandas as pd
import pypdf
import streamlit as st

st.set_page_config(
    page_title="Agrupador y Lector de Albaranes", page_icon="📄", layout="wide"
)

st.title("📄 Lector y Agrupador de Albaranes por Proveedor")
st.write(
    "Sube tus albaranes. La app los unirá por proveedor y calculará los importes. Si alguna cifra no es correcta, puedes editarla directamente en la tabla antes de descargar el CSV."
)

uploaded_files = st.file_uploader(
    "Sube tus albaranes PDF", type=["pdf"], accept_multiple_files=True
)


def extraer_texto_pdf(pdf_file):
  """Extrae el texto de todas las páginas de un PDF."""
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
  """Detecta el nombre del proveedor evitando palabras genéricas y fechas."""
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
  ]

  proveedor_detectado = ""
  for linea in lineas[:15]:
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

  proveedor_limpio = re.sub(r'[\\/*?:"<>|]', "", proveedor_detectado)
  return proveedor_limpio[:35].upper().strip()


def extraer_importes(texto):
  """Busca de forma más flexible los importes sin IVA, IVA y Total con IVA."""
  sin_iva = 0.0
  iva = 0.0
  total = 0.0
  texto_lower = texto.lower()

  # Patrones más amplios para capturar distintas nomenclaturas en albaranes
  patron_base = r"(?:base\s*imponible|subtotal|neto|gravable|total\s*s/?iva)[\s:]*([0-9.,]+)"
  patron_iva = (
      r"(?:cuota\s*iva|iva\s*(?:\d+[\.,]?\d*%?)?|impuestos)[\s:]*([0-9.,]+)"
  )
  patron_total = r"(?:total\s*(?:factura|albarán|a\s*pagar|general)?|importe\s*total|a\s*pagar)[\s:]*([0-9.,]+)"

  def limpiar_numero(val_str):
    try:
      # Manejo de formatos de moneda (ej: 1.234,56 o 1234.56 o 1,234.56)
      val_str = val_str.replace("€", "").strip()
      if "." in val_str and "," in val_str:
        if val_str.rfind(",") > val_str.rfind("."):
          val_str = val_str.replace(".", "").replace(",", ".")
        else:
          val_str = val_str.replace(",", "")
      elif "," in val_str:
        val_str = val_str.replace(",", ".")
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

  # Lógica de respaldo cruzada
  if total > 0 and sin_iva == 0:
    if iva > 0:
      sin_iva = round(total - iva, 2)
    else:
      sin_iva = round(total / 1.21, 2)
      iva = round(total - sin_iva, 2)
  elif sin_iva > 0 and total == 0:
    if iva == 0:
      iva = round(sin_iva * 0.21, 2)
    total = round(sin_iva + iva, 2)
  elif sin_iva > 0 and iva > 0 and total == 0:
    total = round(sin_iva + iva, 2)

  return sin_iva, iva, total


if uploaded_files:
  st.success(f"¡{len(uploaded_files)} archivos cargados correctamente!")

  proveedores_pdfs = {}
  detalle_albaranes = []

  for file in uploaded_files:
    file_bytes = file.read()
    file.seek(0)

    texto = extraer_texto_pdf(io.BytesIO(file_bytes))
    proveedor = limpiar_nombre_proveedor(texto, file.name)
    sin_iva, iva, total = extraer_importes(texto)

    # Guardamos el detalle individual de cada albarán
    detalle_albaranes.append({
        "Proveedor": proveedor,
        "Archivo": file.name,
        "Total Sin IVA (€)": sin_iva,
        "IVA (€)": iva,
        "Total Con IVA (€)": total,
    })

    # Agrupar páginas físicas en el PDF del proveedor
    if proveedor not in proveedores_pdfs:
      proveedores_pdfs[proveedor] = pypdf.PdfWriter()

    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    for page in reader.pages:
      proveedores_pdfs[proveedor].add_page(page)

  # Convertir a DataFrame inicial de albaranes individuales
  df_albaranes = pd.DataFrame(detalle_albaranes)

  st.subheader(
      "✏️ Detalle de Albaranes Detectados (Editable si necesitas corregir"
      " cifras)"
  )
  st.write(
      "Puedes hacer clic directamente sobre cualquier celda de importes en la"
      " tabla para corregirla antes de generar el resumen y el CSV."
  )

  # Tabla editable de albaranes
  df_editado = st.data_editor(df_albaranes, use_container_width=True, num_rows="fixed")

  # --- RESUMEN AGRUPADO POR PROVEEDOR (Basado en la tabla editada) ---
  st.subheader("📊 Resumen Consolidado por Proveedor")
  df_resumen = (
      df_editado.groupby("Proveedor")[
          ["Total Sin IVA (€)", "IVA (€)", "Total Con IVA (€)"]
      ]
      .sum()
      .reset_index()
  )
  # Añadir conteo de albaranes
  conteo = df_editado.groupby("Proveedor").size().reset_index(name="Nº Albaranes")
  df_resumen = pd.merge(conteo, df_resumen, on="Proveedor")

  st.dataframe(df_resumen, use_container_width=True)

  # Botón de descarga para CSV (exporta el resumen consolidado o el detalle editado)
  tipo_csv = st.radio(
      "¿Qué formato de CSV deseas descargar?",
      [
          "Resumen por Proveedor (Totales agrupados)",
          "Detalle completo de todos los albaranes",
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
      label="📥 Descargar CSV",
      data=csv_data,
      file_name=nombre_csv,
      mime="text/csv",
  )

  st.divider()

  # --- DESCARGAR ZIP CON PDFS UNIDOS ---
  st.subheader("📦 PDFs Unidos por Proveedor")
  st.write("Descarga el archivo ZIP con los PDFs unidos por cada proveedor.")

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
