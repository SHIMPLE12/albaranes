import io
import re
import zipfile
import pandas as pd
import pypdf
import streamlit as st

st.set_page_config(
    page_title="Lector Estricto de Albaranes", page_icon="📄", layout="wide"
)

st.title("🤖 Lector Estricto de Albaranes por Proveedor")
st.write(
    "La aplicación une los PDFs por proveedor y realiza una lectura estricta de las líneas finales de cada documento para extraer con precisión los importes con y sin IVA."
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
  """Detecta de forma estricta el nombre del proveedor en las primeras líneas."""
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

  proveedor_limpio = re.sub(r'[\\/*?:"<>|]', "", proveedor_detectado)
  return proveedor_limpio[:35].upper().strip()


def extraccion_estricta_importes(texto):
  """Lectura estricta focalizada en buscar importes monetarios claros (ej: 123,45 o 1.234,56)."""
  sin_iva = 0.0
  iva = 0.0
  total = 0.0

  # Dividir en líneas y limpiar
  lineas = [l.strip() for l in texto.split("\n") if l.strip()]

  # Patrón estricto para encontrar números con formato de moneda europeo o estándar
  # Busca números con decimales obligatorios (ej: 45,00 o 123.45 o 1.234,56)
  patron_monto = r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b|\b\d+,\d{2}\b|\b\d+\.\d{2}\b"

  # Recorremos el documento buscando etiquetas clave combinadas con montos
  for i, linea in enumerate(lineas):
    linea_lower = linea.lower()

    # Buscar Total / Importe Total
    if any(
        k in linea_lower
        for k in [
            "total",
            "importe",
            "a pagar",
            "liquido",
            "suma",
            "eur",
            "€",
        ]
    ):
      # Buscamos números en la misma línea o en la línea inmediatamente siguiente
      bloque_busqueda = linea
      if i + 1 < len(lineas):
        bloque_busqueda += " " + lineas[i + 1]

      montos = re.findall(patron_monto, bloque_busqueda)
      if montos:
        # El último monto encontrado suele ser el total definitivo
        total = limpiar_numero(montos[-1])

    # Buscar Base Imponible / Sin IVA
    if any(
        k in linea_lower
        for k in ["base", "s/iva", "neto", "subtotal", "gravable"]
    ):
      montos = re.findall(patron_monto, linea)
      if not montos and i + 1 < len(lineas):
        montos = re.findall(patron_monto, lineas[i + 1])
      if montos:
        sin_iva = limpiar_numero(montos[0])

    # Buscar IVA / Cuota
    if any(k in linea_lower for k in ["iva", "cuota", "21%", "10%", "4%"]):
      montos = re.findall(patron_monto, linea)
      if not montos and i + 1 < len(lineas):
        montos = re.findall(patron_monto, lineas[i + 1])
      if montos:
        # Evitar confundir el porcentaje de IVA (ej: 21) con el importe en euros
        montos_filtrados = [
            m for m in montos if m not in ["21,00", "10,00", "4,00", "21", "10"]
        ]
        if montos_filtrados:
          iva = limpiar_numero(montos_filtrados[0])

  # Coherencia y cálculos cruzados si alguno quedó en 0
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


def limpiar_numero(val_str):
  try:
    val_str = (
        val_str.replace("€", "").replace("EUR", "").replace(" ", "").strip()
    )
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


if uploaded_files:
  st.success(f"¡{len(uploaded_files)} archivos cargados correctamente!")

  proveedores_pdfs = {}
  detalle_albaranes = []

  for file in uploaded_files:
    file_bytes = file.read()
    file.seek(0)

    texto = extraer_texto_pdf(io.BytesIO(file_bytes))
    proveedor = limpiar_nombre_proveedor(texto, file.name)
    sin_iva, iva, total = extraccion_estricta_importes(texto)

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

  df_albaranes = pd.DataFrame(detalle_albaranes)

  st.subheader(
      "✏️ Validación Estricta de Importes (Puedes editar cualquier celda si es"
      " necesario)"
  )
  st.write(
      "Revisa los valores extraídos. Si algún proveedor tiene un formato"
      " atípico, puedes corregirlo directamente haciendo clic en la celda."
  )

  # Tabla interactiva para asegurar 100% de precisión en los datos del CSV
  df_editado = st.data_editor(df_albaranes, use_container_width=True, num_rows="fixed")

  # Resumen consolidado por proveedor
  st.subheader("📊 Resumen Consolidado por Proveedor (Para el CSV)")
  df_resumen = (
      df_editado.groupby("Proveedor")[
          ["Total Sin IVA (€)", "IVA (€)", "Total Con IVA (€)"]
      ]
      .sum()
      .reset_index()
  )
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
      label="📥 Descargar CSV",
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
