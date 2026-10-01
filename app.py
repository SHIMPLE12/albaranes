import io
import re
import pandas as pd
import pypdf
import streamlit as st

st.set_page_config(
    page_title="Lector de Albaranes por Proveedor", page_icon="📄", layout="wide"
)

st.title("🤖 Lector Estricto de Albaranes por Proveedor")
st.write(
    "Sube tus archivos PDF de albaranes para extraer la información, agruparlos por proveedor y generar un CSV con los totales con y sin IVA."
)

# Sidebar / Configuración
st.sidebar.header("Configuración")
st.sidebar.info(
    "Este script analiza el texto de cada PDF para identificar al proveedor, extraer los importes y generar un resumen descargable en CSV."
)

uploaded_files = st.file_uploader(
    "Sube tus archivos PDF de albaranes aquí",
    type=["pdf"],
    accept_multiple_files=True,
)


def extraer_texto_pdf(pdf_file):
  """Extrae todo el texto de un archivo PDF usando pypdf."""
  texto = ""
  try:
    reader = pypdf.PdfReader(pdf_file)
    for pagina in reader.pages:
      t = pagina.extract_text()
      if t:
        texto += t + "\n"
  except Exception as e:
    st.error(f"Error leyendo el PDF: {e}")
  return texto


def detectar_proveedor(texto):
  """Intenta detectar el proveedor basándose en las primeras líneas o palabras clave."""
  lineas = [
      l.strip() for l in texto.split("\n") if l.strip() and len(l.strip()) > 3
  ]
  if lineas:
    # Por defecto, tomamos la primera línea significativa como el proveedor o cabecera
    # Puedes personalizar esto según tus proveedores habituales.
    return lineas[0][:40]
  return "Proveedor Desconocido"


def extraer_importes(texto):
  """Busca patrones de Total sin IVA, IVA y Total con IVA en el texto."""
  sin_iva = 0.0
  iva = 0.0
  total = 0.0

  # Normalizar texto para búsqueda
  texto_lower = texto.lower()

  # Expresiones regulares comunes para importes en España
  # Buscamos patrones tipo "Total: 123.45" o "Base Imponible: 100,00"
  patron_base = r"(?:base\s*imponible|total\s*s/iva|subtotal|neto)[\s:]*([0-9.,]+)"
  patron_iva = r"(?:cuota\s*iva|iva\s*(?:\d+%)?)[\s:]*([0-9.,]+)"
  patron_total = r"(?:total\s*(?:factura|albarán|a\s*pagar)?|importe\s*total)[\s:]*([0-9.,]+)"

  def limpiar_numero(val_str):
    try:
      # Limpiar formato de moneda europeo (ej: 1.234,56 -> 1234.56)
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

  # Si encontramos total pero no base o viceversa, intentamos estimar o calcular lógicamente
  if total > 0 and sin_iva == 0:
    if iva > 0:
      sin_iva = total - iva
    else:
      # Estimación estándar de IVA al 21% si no se especifica
      sin_iva = round(total / 1.21, 2)
      iva = round(total - sin_iva, 2)
  elif sin_iva > 0 and total == 0:
    if iva == 0:
      iva = round(sin_iva * 0.21, 2)  # 21% por defecto
    total = round(sin_iva + iva, 2)

  return sin_iva, iva, total


if uploaded_files:
  st.success(f"Se han cargado {len(uploaded_files)} archivos PDF.")

  resultados = []

  for file in uploaded_files:
    texto_pdf = extraer_texto_pdf(file)
    proveedor = detectar_proveedor(texto_pdf)
    sin_iva, iva, total = extraer_importes(texto_pdf)

    resultados.append({
        "Archivo": file.name,
        "Proveedor": proveedor,
        "Total Sin IVA (€)": sin_iva,
        "IVA (€)": iva,
        "Total Con IVA (€)": total,
    })

  df = pd.DataFrame(resultados)

  st.subheader("📊 Vista Previa de Albaranes Procesados")
  st.dataframe(df, use_container_width=True)

  # Resumen agrupado por Proveedor
  if not df.empty:
    st.subheader("📁 Resumen Agrupado por Proveedor")
    df_resumen = (
        df.groupby("Proveedor")[
            ["Total Sin IVA (€)", "IVA (€)", "Total Con IVA (€)"]
        ]
        .sum()
        .reset_index()
    )
    st.dataframe(df_resumen, use_container_width=True)

    # Botón de descarga para CSV
    csv_data = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Descargar CSV Consolidado",
        data=csv_data,
        file_name="resumen_albaranes.csv",
        mime="text/csv",
    )
else:
  st.info(
      "Por favor, sube uno o varios archivos PDF en el campo superior para"
      " comenzar."
  )
