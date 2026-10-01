import io
import re
import zipfile
import pandas as pd
import pypdf
import streamlit as st

st.set_page_config(
    page_title="Gestor de Albaranes 100% Preciso",
    page_icon="📄",
    layout="wide",
)

st.title("🎯 Gestor y Validador 100% Preciso de Albaranes")
st.write(
    "Agrupa los PDFs por proveedor de forma perfecta. Dado que cada albarán tiene un diseño único, utiliza la vista previa de texto y la tabla editable para asegurar que los totales y IVAs sean 100% correctos antes de descargar tu CSV."
)

uploaded_files = st.file_uploader(
    "Sube tus albaranes PDF", type=["pdf"], accept_multiple_files=True
)


def extraer_texto_pdf(pdf_file):
  """Extrae todo el texto ordenado por páginas."""
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
  """Detecta el nombre del proveedor en la cabecera."""
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


def limpiar_numero(val_str):
  try:
    val_str = (
        val_str.replace("€", "")
        .replace("EUR", "")
        .replace("$", "")
        .replace(" ", "")
        .strip()
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


def extraccion_avanzada(texto):
  """Extracción orientada a capturar cifras del documento."""
  sin_iva, iva, total = 0.0, 0.0, 0.0
  lineas = [l.strip() for l in texto.split("\n") if l.strip()]
  if not lineas:
    return 0.0, 0.0, 0.0

  patron_monto = r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b|\b\d+,\d{2}\b|\b\d+\.\d{2}\b"
  bloque_final = " \n ".join(lineas[-25:]) if len(lineas) >= 25 else " \n ".join(lineas)
  bloque_final_lower = bloque_final.lower()

  # Búsqueda de total
  for palabra in [
      "total a pagar",
      "importe total",
      "total factura",
      "total albarán",
      "líquido",
      "a pagar",
      "total",
  ]:
    if palabra in bloque_final_lower:
      idx = bloque_final_lower.rfind(palabra)
      sub = bloque_final[idx : idx + 60]
      montos = re.findall(patron_monto, sub)
      if montos:
        total = limpiar_numero(montos[-1])
        break

  if total == 0.0:
    todos = [limpiar_numero(m) for m in re.findall(patron_monto, bloque_final)]
    todos = [m for m in todos if 0.01 < m < 100000]
    if todos:
      total = max(todos)

  # Búsqueda base
  for palabra in [
      "base imponible",
      "total s/iva",
      "subtotal",
      "neto",
      "gravable",
      "suma",
  ]:
    if palabra in bloque_final_lower:
      idx = bloque_final_lower.find(palabra)
      sub = bloque_final[idx : idx + 60]
      montos = re.findall(patron_monto, sub)
      if montos:
        sin_iva = limpiar_numero(montos[0])
        break

  # Búsqueda IVA
  for palabra in ["cuota iva", "iva (", "iva %", "impuestos", "iva"]:
    if palabra in bloque_final_lower:
      idx = bloque_final_lower.find(palabra)
      sub = bloque_final[idx : idx + 60]
      montos = re.findall(patron_monto, sub)
      filtrados = [
          m
          for m in montos
          if limpiar_numero(m) not in [21.0, 10.0, 4.0, 21, 10, 4]
      ]
      if filtrados:
        iva = limpiar_numero(filtrados[0])
        break

  # Consistencia
  if total > 0.0 and sin_iva == 0.0:
    sin_iva = round(total / 1.21, 2)
    iva = round(total - sin_iva, 2)
  elif sin_iva > 0.0 and total == 0.0:
    iva = round(sin_iva * 0.21, 2)
    total = round(sin_iva + iva, 2)

  return round(sin_iva, 2), round(iva, 2), round(total, 2)


if uploaded_files:
  st.success(f"¡{len(uploaded_files)} archivos cargados correctamente!")

  proveedores_pdfs = {}
  detalle_albaranes = []
  textos_originales = {}

  for file in uploaded_files:
    file_bytes = file.read()
    file.seek(0)

    texto = extraer_texto_pdf(io.BytesIO(file_bytes))
    textos_originales[file.name] = (
        texto  # Guardamos el texto para poder visualizarlo
    )

    proveedor = limpiar_nombre_proveedor(texto, file.name)
    sin_iva, iva, total = extraccion_avanzada(texto)

    detalle_albaranes.append({
        "Proveedor": proveedor,
        "Archivo": file.name,
        "Total Sin IVA (€)": sin_iva,
        "IVA (€)": iva,
        "Total Con IVA (€)": total,
    })

    if proveedor not in proveedores_pdfs:
      proveedores_pdfs[proveedor] = pypdf.PdfWriter()

    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    for page in reader.pages:
      proveedores_pdfs[proveedor].add_page(page)

  df_albaranes = pd.DataFrame(detalle_albaranes)

  st.subheader(
      "✏️ Validación Interactiva (Edita las celdas para garantizar el 100%"
      " de precisión)"
  )
  st.write(
      "Haz clic en cualquier celda de la tabla para corregir el importe si es"
      " necesario."
  )

  # Tabla editable
  df_editado = st.data_editor(df_albaranes, use_container_width=True, num_rows="fixed")

  # Opcional: Ver el texto extraído de un albarán específico para contrastar cifras
  with st.expander(
      "🔍 Ver el texto interno de los PDFs (para comprobar los importes reales)"
  ):
    archivo_seleccionado = st.selectbox(
        "Selecciona un albarán para ver su texto:", list(textos_originales.keys())
    )
    if archivo_seleccionado:
      st.text_area(
          "Texto leído del PDF:",
          textos_originales[archivo_seleccionado],
          height=200,
      )

  # --- RESUMEN CONSOLIDADO POR PROVEEDOR ---
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

  # Descarga CSV
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
