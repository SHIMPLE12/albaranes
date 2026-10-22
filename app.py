import streamlit as st
import json
import io
import pandas as pd
from google import genai
from google.genai import types
from PIL import Image
import fitz  # PyMuPDF para leer PDFs
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

st.set_page_config(page_title="Gestor IA de Albaranes y Facturas", layout="wide")

# Validar clave de Google en los Secrets de Streamlit
if "GEMINI_API_KEY" not in st.secrets or not st.secrets["GEMINI_API_KEY"]:
    st.error("Por favor, añade GEMINI_API_KEY en los Secrets de Streamlit.")
    st.stop()

# Inicializar cliente oficial de Google GenAI
client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"].strip())

def crear_excel_profesional(datos):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Documento Extraído"
    ws.views.sheetView[0].showGridLines = True

    navy_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    soft_blue = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    light_gray = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
    
    font_title = Font(name="Calibri", size=16, bold=True, color="1F4E78")
    font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    font_bold = Font(name="Calibri", size=11, bold=True)
    font_normal = Font(name="Calibri", size=11)
    
    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'), right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'), bottom=Side(style='thin', color='D9D9D9')
    )

    ws["A1"] = "RESUMEN DE DOCUMENTO EXTRAÍDO"
    ws["A1"].font = font_title
    
    datos_cabecera = [
        ("Proveedor:", datos.get("proveedor", "N/D"), "NIF / CIF:", datos.get("nif", "N/D")),
        ("N° Albarán/Factura:", datos.get("numero_albaran", "N/D"), "Fecha:", datos.get("fecha", "N/D")),
    ]

    for r_idx, row in enumerate(datos_cabecera, start=3):
        ws.cell(row=r_idx, column=1, value=row[0]).font = font_bold
        ws.cell(row=r_idx, column=2, value=row[1]).font = font_normal
        ws.cell(row=r_idx, column=3, value=row[2]).font = font_bold
        ws.cell(row=r_idx, column=4, value=row[3]).font = font_normal

    start_row_items = 7
    headers = ["Descripción / Artículo", "Cantidad", "Precio Unitario", "Importe Total"]
    
    for c_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=start_row_items, column=c_idx, value=header)
        cell.font = font_header
        cell.fill = navy_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    articulos = datos.get("articulos", [])
    current_row = start_row_items + 1

    if articulos:
        for item in articulos:
            desc = item.get("descripcion", "")
            cant = item.get("cantidad", 1)
            precio = item.get("precio_unitario", 0.0)
            total_prod = item.get("total", cant * precio if (isinstance(cant, (int,float)) and isinstance(precio, (int,float))) else 0.0)

            ws.cell(row=current_row, column=1, value=desc).font = font_normal
            c_cant = ws.cell(row=current_row, column=2, value=cant)
            c_cant.font = font_normal
            c_cant.alignment = Alignment(horizontal="center")
            c_prec = ws.cell(row=current_row, column=3, value=precio)
            c_prec.font = font_normal
            c_prec.number_format = '#,##0.00 €'
            c_tot = ws.cell(row=current_row, column=4, value=total_prod)
            c_tot.font = font_normal
            c_tot.number_format = '#,##0.00 €'

            for col in range(1, 5):
                cell = ws.cell(row=current_row, column=col)
                cell.border = thin_border
                if (current_row - start_row_items) % 2 == 0:
                    cell.fill = light_gray
            current_row += 1
    else:
        ws.cell(row=current_row, column=1, value="Sin detalles de línea detectados").font = font_normal
        current_row += 1

    current_row += 1
    ws.cell(row=current_row, column=3, value="TOTAL DOCUMENTO:").font = font_bold
    ws.cell(row=current_row, column=3).alignment = Alignment(horizontal="right")
    
    total_val = datos.get("total", 0.0)
    c_final = ws.cell(row=current_row, column=4, value=total_val)
    c_final.font = font_bold
    c_final.fill = soft_blue
    c_final.number_format = '#,##0.00 €'
    c_final.border = thin_border

    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = max(max_len + 4, 15)

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()

st.title("⚡ Escáner B2B Rápido de Albaranes y Facturas")
st.write("Sube una foto o un archivo **PDF** para extraer los datos al instante y generar tu Excel profesional.")

archivo = st.file_uploader("Selecciona el documento (Imagen o PDF)", type=["jpg", "jpeg", "png", "pdf"])

if archivo and st.button("Procesar Documento"):
    with st.spinner("Procesando a velocidad de rayo con Google Gemini..."):
        try:
            bytes_data = archivo.read()
            
            # Si es PDF, convertimos la primera página a imagen
            if archivo.type == "application/pdf" or archivo.name.endswith(".pdf"):
                doc = fitz.open(stream=bytes_data, filetype="pdf")
                page = doc[0]
                pix = page.get_pixmap(dpi=150)
                image = Image.open(io.BytesIO(pix.tobytes("jpeg")))
            else:
                image = Image.open(io.BytesIO(bytes_data))

            prompt_json = """
            Analiza este albarán o factura y responde ÚNICAMENTE con un objeto JSON válido (sin formato markdown ni bloques de código) con esta estructura exacta:
            {
                "proveedor": "Nombre del proveedor",
                "nif": "NIF / CIF del proveedor",
                "fecha": "DD/MM/AAAA",
                "numero_albaran": "Número de documento",
                "articulos": [
                    {
                        "descripcion": "Concepto",
                        "cantidad": 1,
                        "precio_unitario": 0.0,
                        "total": 0.0
                    }
                ],
                "total": 0.0
            }
            """

            # Llamada rápida utilizando el modelo oficial de Google Gemini
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[image, prompt_json]
            )

            raw_response = response.text.strip()
            
            if "```json" in raw_response:
                raw_response = raw_response.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_response:
                raw_response = raw_response.split("```")[1].split("```")[0].strip()
            
            datos_dict = json.loads(raw_response)
            
            st.session_state["datos_albaran"] = datos_dict
            st.session_state["excel_bytes"] = crear_excel_profesional(datos_dict)
            st.session_state["nombre_archivo"] = archivo.name

        except json.JSONDecodeError:
            st.error("La IA respondió con un formato no válido. Vuelve a intentarlo.")
        except Exception as e:
            st.error(f"Error al procesar el documento: {str(e)}")

if "datos_albaran" in st.session_state:
    st.success("¡Documento analizado a velocidad récord!")
    
    datos = st.session_state["datos_albaran"]
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🏢 Proveedor", datos.get("proveedor", "N/D"))
    col2.metric("🆔 NIF/CIF", datos.get("nif", "N/D"))
    col3.metric("📄 N° Doc", datos.get("numero_albaran", "N/D"))
    col4.metric("💰 Total", f"{datos.get('total', 0)} €")

    st.markdown("### 📊 Vista previa del Excel generado")
    if datos.get("articulos"):
        df_items = pd.DataFrame(datos.get("articulos"))
        st.dataframe(df_items, use_container_width=True)

    st.download_button(
        label="📊 Descargar Excel Profesional (.xlsx)",
        data=st.session_state["excel_bytes"],
        file_name=f"Documento_{datos.get('proveedor', 'Proveedor')}_{st.session_state['nombre_archivo'].split('.')[0]}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
