import io
import re
import zipfile
import pandas as pd
import pypdf
import streamlit as st

st.set_page_config(
    page_title="Gestor Integral Pro de Albaranes", page_icon="🚀", layout="wide"
)

st.title("🚀 Sistema Integral de Gestión y Automatización de Albaranes")
st.write(
    "Plataforma profesional para la extracción automática, control de duplicados, agrupación por proveedor y exportación lista para programas de contabilidad o asesorías."
)

# Inicializar base de datos de sesión para control de duplicados y histórico
if "historico_procesados" not in st.session_state:
  st.session_state["historico_procesados"] = set()

uploaded_files = st.file_uploader(
    "Sube tus albaranes y facturas en PDF",
    type=["pdf"],
    accept_multiple_files=True,
)


def extraer_texto_pdf(pdf_file):
  """Extrae el texto completo de un PDF de forma robusta."""
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
  """Detecta con precisión el nombre del proveedor en las primeras líneas."""
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


def deteccion_automatica_total(texto):
  """Intenta extraer de forma automática el total del documento."""
  lineas = [l.strip() for l in texto.split("\n") if l.strip()]
  if not lineas:
    return 0.0

  patron_monto = r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b|\b\d+,\d{2}\b|\b\d+\.\d{2}\b"
  bloque_final = " \n ".join(lineas[-25:]) if len(lineas) >= 25 else " \n ".join(lineas)
  bloque_final_lower = bloque_final.lower()

  total = 0.0
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
        val_str = (
            montos[-1]
            .replace("€", "")
            .replace(".", "")
            .replace(",", ".")
            .strip()
        )
        try:
          total = float(val_str)
          break
        except:
          pass

  if total == 0.0:
    todos = []
    for m in re.findall(patron_monto, bloque_final):
      try:
        val = float(m.replace(".", "").replace(",", ".").strip())
        if 0.01 < val < 100000:
          todos.append(val)
      except:
        pass
    if todos:
      total = max(todos)

  return round(total, 2)


if uploaded_files:
  st.success(f"¡{len(uploaded_files)} archivos cargados en el sistema!")

  proveedores_pdfs = {}
  detalle_albaranes = []
  duplicados_detectados = []

  for file in uploaded_files:
    file_bytes = file.read()
    file.seek(0)

    # Control de Duplicados (basado en el nombre del archivo y tamaño)
    identificador_unico = f"{file.name}_{len(file_bytes)}"
    if identificador_unico in st.session_state["historico_procesados"]:
      duplicados_detectados.append(file.name)
      continue

    st.session_state["historico_procesados"].add(identificador_unico)

    texto = extraer_texto_pdf(io.BytesIO(file_bytes))
    proveedor = limpiar_nombre_proveedor(texto, file.name)
    total_auto = deteccion_automatica_total(texto)

    detalle_albaranes.append({
        "Proveedor": proveedor,
        "Archivo": file.name,
        "Total (€)": total_auto,
        "Estado": "Verificado",
    })

    # Agrupar páginas físicas por proveedor
    if proveedor not in proveedores_pdfs:
      proveedores_pdfs[proveedor] = pypdf.PdfWriter()

    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    for page in reader.pages:
      proveedores_pdfs[proveedor].add_page(page)

  if duplicados_detectados:
    st.warning(
        f"⚠️ Se han omitido {len(duplicados_detectados)} archivos por estar"
        " duplicados en esta sesión:"
        f" {', '.join(duplicados_detectados)}"
    )

  if detalle_albaranes:
    df_albaranes = pd.DataFrame(detalle_albaranes)

    st.subheader("✏️ Panel de Validación y Corrección Rápida")
    st.write(
        "El sistema ha intentado autocompletar los totales. Revisa y edita"
        " cualquier celda si lo consideras necesario para asegurar precisión"
        " absoluta."
    )

    df_editado = st.data_editor(df_albaranes, use_container_width=True, num_rows="fixed")

    # --- RESUMEN CONSOLIDADO POR PROVEEDOR ---
    st.subheader(
        "📊 Resumen Consolidado por Proveedor (Optimizado para Contabilidad)"
    )
    df_resumen = df_editado.groupby("Proveedor")[["Total (€)"]].sum().reset_index()
    conteo = df_editado.groupby("Proveedor").size().reset_index(name="Nº Documentos")
    df_resumen = pd.merge(conteo, df_resumen, on="Proveedor")

    st.dataframe(df_resumen, use_container_width=True)

    # Opciones de exportación profesional
    st.subheader("📥 Exportación de Datos y Documentos")
    col1, col2 = st.columns(2)

    with col1:
      tipo_csv = st.radio(
          "Formato del informe CSV:",
          [
              "Resumen por Proveedor (Totales agrupados)",
              "Detalle completo por documento",
          ],
          horizontal=False,
      )

      if "Resumen" in tipo_csv:
        csv_data = df_resumen.to_csv(index=False).encode("utf-8")
        nombre_csv = "resumen_contable_proveedores.csv"
      else:
        csv_data = df_editado.to_csv(index=False).encode("utf-8")
        nombre_csv = "detalle_completo_albaranes.csv"

      st.download_button(
          label="⬇️ Descargar Informe CSV",
          data=csv_data,
          file_name=nombre_csv,
          mime="text/csv",
      )

    with col2:
      st.write("**Paquete de PDFs Organizados:**")
      zip_buffer = io.BytesIO()
      with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for prov, writer in proveedores_pdfs.items():
          pdf_buffer = io.BytesIO()
          writer.write(pdf_buffer)
          pdf_bytes = pdf_buffer.getvalue()

          nombre_archivo_pdf = f"{prov.replace(' ', '_')}_agrupado.pdf"
          zip_file.writestr(nombre_archivo_pdf, pdf_bytes)

      zip_buffer.seek(0)

      st.download_button(
          label="📦 Descargar ZIP con PDFs por Proveedor",
          data=zip_buffer,
          file_name="albaranes_clasificados_proveedores.zip",
          mime="application/zip",
      )
  else:
    st.info("No hay documentos nuevos para procesar (todos están duplicados).")

else:
  st.info("👆 Sube tus albaranes y facturas en PDF para iniciar el sistema.")
