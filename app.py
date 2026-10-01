import io
import re
import zipfile
import pandas as pd
import pypdf
import streamlit as st

st.set_page_config(
    page_title="Agrupador de Albaranes por Proveedor", page_icon="📁", layout="wide"
)

st.title("📄 Agrupador Inteligente de Albaranes por Proveedor")
st.write(
    "Sube tus albaranes en PDF. La app detectará el proveedor real, unirá los PDFs correspondientes y generará el CSV."
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
  """Detecta de forma inteligente el nombre del proveedor evitando fechas o palabras como 'ENTRADA'."""
  lineas = [l.strip() for l in texto.split("\n") if l.strip()]

  # Palabras comunes a ignorar si aparecen al inicio del documento
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
  for linea in lineas[:15]:  # Revisar las primeras 15 líneas
    linea_lower = linea.lower()
    # Si la línea es muy corta, es un número o contiene palabras a ignorar, la saltamos
    if len(linea) < 3 or linea.isdigit():
      continue
    if any(palabra in linea_lower for palabra in ignorar):
      continue
    # Si tiene formato de fecha (ej: 2026-09-01), saltar
    if re.search(r"\d{2}[-/]\d{2}[-/]\d{2,4}", linea):
      continue

    proveedor_detectado = linea
    break

  # Si no encuentra nada limpio, usamos el nombre del archivo sin extensión ni números largos de fecha
  if not proveedor_detectado:
    limpio = re.sub(
        r"entrada[_\-\s]*\d+[-_\d]*", "", nombre_archivo, flags=re.IGNORECASE
    )
    proveedor_detectado = limpio.replace(".pdf", "").strip()
    if not proveedor_detectado:
      proveedor_detectado = "PROVEEDOR_GENERAL"

  # Limpiar caracteres no válidos para nombres de archivo y limitar longitud
  proveedor_limpio = re.sub(r'[\\/*?:"<>|]', "", proveedor_detectado)
  return proveedor_limpio[:35].upper().strip()


def extraer_importes(texto):
  """Extrae o estima la Base Imponible (sin IVA), el IVA y el Total con IVA."""
  sin_iva = 0.0
  iva = 0.0
  total = 0.0
  texto_lower = texto.lower()

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

  if total > 0 and sin_iva == 0:
    sin_iva = round(total / 1.21, 2)
    iva = round(total - sin_iva, 2)
  elif sin_iva > 0 and total == 0:
    iva = round(sin_iva * 0.21, 2)
    total = round(sin_iva + iva, 2)

  return sin_iva, iva, total


if uploaded_files:
  st.success(f"¡{len(uploaded_files)} archivos cargados correctamente!")

  proveedores_data = {}
  proveedores_pdfs = {}
  detalle_procesamiento = []

  for file in uploaded_files:
    file_bytes = file.read()
    file.seek(0)

    texto = extraer_texto_pdf(io.BytesIO(file_bytes))
    proveedor = limpiar_nombre_proveedor(texto, file.name)
    sin_iva, iva, total = extraer_importes(texto)

    detalle_procesamiento.append({
        "Archivo Original": file.name,
        "Proveedor Detectado": proveedor,
        "Sin IVA (€)": sin_iva,
        "IVA (€)": iva,
        "Con IVA (€)": total,
    })

    # Agrupar datos para CSV
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

    # Agrupar páginas físicas en el PDF del proveedor
    if proveedor not in proveedores_pdfs:
      proveedores_pdfs[proveedor] = pypdf.PdfWriter()

    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    for page in reader.pages:
      proveedores_pdfs[proveedor].add_page(page)

  # Mostrar depuración / qué proveedor detectó cada archivo
  with st.expander("🔍 Ver qué proveedor detectó la app en cada albarán"):
    st.dataframe(pd.DataFrame(detalle_procesamiento), use_container_width=True)

  # --- TABLA RESUMEN ---
  lista_filas = []
  for prov, valores in proveedores_data.items():
    lista_filas.append({
        "Proveedor": prov,
        "Nº Albaranes": valores["Cantidad Albaranes"],
        "Total Sin IVA (€)": round(valores["Total Sin IVA (€)"], 2),
        "IVA (€)": round(valores["IVA (€)"], 2),
        "Total Con IVA (€)": round(valores["Total Con IVA (€)"], 2),
    })

  df_resultado = pd.DataFrame(lista_filas)

  st.subheader("📊 Resumen Consolidado por Proveedor")
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

  # --- DESCARGAR ZIP CON PDFS UNIDOS ---
  st.subheader("📦 PDFs Unidos por Proveedor")
  st.write(
      "Se ha generado un archivo PDF independiente por cada proveedor que"
      " agrupa todos sus albaranes."
  )

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
