import io
import re
import zipfile
import pandas as pd
import pypdf
import streamlit as st

st.set_page_config(
    page_title="Lector Ultra Preciso de Albaranes",
    page_icon="📄",
    layout="wide",
)

st.title("🎯 Lector Ultra Preciso de Albaranes por Proveedor")
st.write(
    "Agrupa los albaranes perfectamente por proveedor y aplica un algoritmo avanzado de detección de importes. Si algún valor requiere ajuste, puedes editarlo directamente en la tabla y los totales se recalcularán solos."
)

uploaded_files = st.file_uploader(
    "Sube tus albaranes PDF", type=["pdf"], accept_multiple_files=True
)


def extraer_texto_pdf(pdf_file):
  """Extrae todo el texto manteniendo la estructura de líneas."""
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
  """Detecta con precisión el nombre del proveedor en la cabecera del documento."""
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
      "tlf",
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
  """Convierte cadenas de texto monetarias a float de forma segura."""
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


def extraccion_ultra_precisa(texto):
  """Algoritmo avanzado de búsqueda de importes analizando todo el texto y bloques de resumen."""
  sin_iva = 0.0
  iva = 0.0
  total = 0.0

  lineas = [l.strip() for l in texto.split("\n") if l.strip()]
  if not lineas:
    return 0.0, 0.0, 0.0

  # Patrón para capturar importes monetarios (ej: 12,34 o 1.234,56)
  patron_monto = r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b|\b\d+,\d{2}\b|\b\d+\.\d{2}\b"

  # Unimos las últimas 30 líneas que es donde obligatoriamente residen los totales e impuestos
  bloque_final = " \n ".join(lineas[-30:]) if len(lineas) >= 30 else " \n ".join(lineas)
  bloque_final_lower = bloque_final.lower()

  # 1. Búsqueda de Base Imponible / Sin IVA
  claves_base = [
      "base imponible",
      "total s/iva",
      "tot.s/iva",
      "subtotal",
      "neto",
      "gravable",
      "importe neto",
      "suma",
      "bruto",
  ]
  for clave in claves_base:
    if clave in bloque_final_lower:
      idx = bloque_final_lower.find(clave)
      sub = bloque_final[idx : idx + 50]
      montos = re.findall(patron_monto, sub)
      if montos:
        sin_iva = limpiar_numero(montos[0])
        break

  # 2. Búsqueda de Cuota IVA
  claves_iva = [
      "cuota iva",
      "iva 21",
      "iva 10",
      "iva 4",
      "impuestos",
      "iva",
      "i.v.a.",
  ]
  for clave in claves_iva:
    if clave in bloque_final_lower:
      idx = bloque_final_lower.find(clave)
      sub = bloque_final[idx : idx + 50]
      montos = re.findall(patron_monto, sub)
      # Filtrar por si pilla porcentajes puros
      filtrados = [
          m
          for m in montos
          if limpiar_numero(m) not in [21.0, 10.0, 4.0, 21, 10, 4, 0]
      ]
      if filtrados:
        iva = limpiar_numero(filtrados[0])
        break

  # 3. Búsqueda de Total con IVA
  claves_total = [
      "total a pagar",
      "importe total",
      "total factura",
      "total albarán",
      "total general",
      "líquido",
      "a pagar",
      "total",
  ]
  for clave in claves_total:
    if clave in bloque_final_lower:
      # Buscamos la última coincidencia de la palabra total en el documento (suele ser el pie)
      idx = bloque_final_lower.rfind(clave)
      sub = bloque_final[idx : idx + 60]
      montos = re.findall(patron_monto, sub)
      if montos:
        total = limpiar_numero(montos[-1])
        break

  # Respaldo si falta el total absoluto: buscamos el número con decimales más alto del bloque final
  if total == 0.0:
    todos = [limpiar_numero(m) for m in re.findall(patron_monto, bloque_final)]
    todos = [m for m in todos if 0.01 < m < 200000]
    if todos:
      total = max(todos)

  # Consistencia matemática automática
  if total > 0.0 and sin_iva == 0.0:
    if iva > 0.0:
      sin_iva = round(total - iva, 2)
    else:
      sin_iva = round(total / 1.21, 2)
      iva = round(total - sin_iva, 2)
  elif sin_iva > 0.0 and total == 0.0:
    if iva == 0.0:
      iva = round(sin_iva * 0.21, 2)
    total = round(sin_iva + iva, 2)
  elif sin_iva > 0.0 and iva > 0.0 and total == 0.0:
    total = round(sin_iva + iva, 2)
  elif total > 0.0 and sin_iva > 0.0 and iva == 0.0:
    iva = round(total - sin_iva, 2)

  return round(sin_iva, 2), round(iva, 2), round(total, 2)


if uploaded_files:
  st.success(f"¡{len(uploaded_files)} archivos cargados correctamente!")

  proveedores_pdfs = {}
  detalle_albaranes = []

  for file in uploaded_files:
    file_bytes = file.read()
    file.seek(0)

    texto = extraer_texto_pdf(io.BytesIO(file_bytes))
    proveedor = limpiar_nombre_proveedor(texto, file.name)
    sin_iva, iva, total = extraccion_ultra_precisa(texto)

    detalle_albaranes.append({
        "Proveedor": proveedor,
        "Archivo": file.name,
        "Total Sin IVA (€)": sin_iva,
        "IVA (€)": iva,
        "Total Con IVA (€)": total,
    })

    # Agrupar páginas físicas en el PDF unificado del proveedor
    if proveedor not in proveedores_pdfs:
      proveedores_pdfs[proveedor] = pypdf.PdfWriter()

    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    for page in reader.pages:
      proveedores_pdfs[proveedor].add_page(page)

  df_albaranes = pd.DataFrame(detalle_albaranes)

  st.subheader("✏️ Validación y Ajuste Fino de Importes")
  st.write(
      "Modifica directamente cualquier celda si necesitas corregir alguna"
      " cifra antes de exportar."
  )

  # Tabla interactiva editable
  df_editado = st.data_editor(df_albaranes, use_container_width=True, num_rows="fixed")

  # Recalcular totales agrupados por proveedor basados en la tabla (por si el usuario editó algo)
  st.subheader("📊 Resumen Consolidado por Proveedor (Listo para CSV)")
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

  # Selector de CSV
  tipo_csv = st.radio(
      "Selecciona el formato del archivo CSV:",
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
