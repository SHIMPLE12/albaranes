import gc
import os
import time
import json
import io
import streamlit as st
import pandas as pd
from PIL import Image
import pypdf
from concurrent.futures import ThreadPoolExecutor
from google import genai
from google.genai import types

# -----------------------------------------------------------------------------
# 1. CONFIGURACIÓN Y PLANES
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Extractor de Facturas y Albaranes",
    page_icon="📊",
    layout="wide"
)

PLANES = {
    "gratis": {"limite": 25, "nombre": "Prueba Gratuita (25 facturas)"},
    "19": {"limite": 150, "nombre": "Plan Básico (19€)"},
    "49": {"limite": 600, "nombre": "Plan Pro (49€)"},
    "89": {"limite": 2000, "nombre": "Plan Enterprise (89€)"}
}

URL_GUMROAD_19 = "https://tuusuario.gumroad.com/l/plan-basico"
URL_GUMROAD_49 = "https://tuusuario.gumroad.com/l/plan-pro"
URL_GUMROAD_89 = "https://tuusuario.gumroad.com/l/plan-enterprise"

ARCHIVO_BD = "uso_usuarios.json"

def cargar_bd():
    if os.path.exists(ARCHIVO_BD):
        with open(ARCHIVO_BD, "r") as f:
            try:
                return json.load(f)
            except:
                return {}
    return {}

def guardar_bd(datos):
    with open(ARCHIVO_BD, "w") as f:
        json.dump(datos, f)

# -----------------------------------------------------------------------------
# 2. PANTALLA DE ACCESO (CONTRASEÑA ÚNICA POR GESTORÍA)
# -----------------------------------------------------------------------------
st.title("📊 Gestor Inteligente de Facturas y Albaranes")

if "sesion_activa" not in st.session_state:
    st.session_state["sesion_activa"] = None

if not st.session_state["sesion_activa"]:
    st.markdown("### 🔑 Introduce la contraseña de tu gestoría")
    st.markdown("Si es tu primera vez, introduce el código o contraseña que quieras usar para tu gestoría.")
    
    with st.form("form_login"):
        input_clave = st.text_input("Contraseña de la Gestoría:", type="default")
        boton_entrar = st.form_submit_button("Acceder a la App")
        
        if boton_entrar:
            clave_limpia = input_clave.strip().lower()
            if clave_limpia:
                bd = cargar_bd()
                
                # Si la contraseña es nueva, la registramos automáticamente con 25 gratis
                if clave_limpia not in bd:
                    bd[clave_limpia] = {"plan": "gratis", "gastadas": 0}
                    guardar_bd(bd)
                
                st.session_state["sesion_activa"] = clave_limpia
                st.rerun()
            else:
                st.warning("⚠️ Introduce una contraseña válida.")
    st.stop()

# -----------------------------------------------------------------------------
# 3. CONTROL DE LÍMITES POR CADA GESTORÍA
# -----------------------------------------------------------------------------
usuario_key = st.session_state["sesion_activa"]
bd = cargar_bd()
datos_usuario = bd.get(usuario_key, {"plan": "gratis", "gastadas": 0})

tipo_plan = datos_usuario["plan"]
facturas_gastadas = datos_usuario["gastadas"]
limite_maximo = PLANES[tipo_plan]["limite"]
facturas_restantes = max(0, limite_maximo - facturas_gastadas)

# Cabecera informativa
col_h1, col_h2 = st.columns([4, 1])
with col_h1:
    st.info(f"🏢 **Gestoría (Clave: `{usuario_key}`):** Plan **{PLANES[tipo_plan]['nombre']}** | Te quedan **{facturas_restantes}** facturas.")
with col_h2:
    if st.button("Cerrar sesión"):
        st.session_state["sesion_activa"] = None
        st.rerun()

st.progress(facturas_gastadas / limite_maximo)

# SI LLEGA AL LÍMITE: CORTAR EL GRIFO
if facturas_gastadas >= limite_maximo:
    if tipo_plan == "gratis":
        st.error(f"🔒 **La gestoría `{usuario_key}` ha agotado las 25 facturas de su prueba gratuita.**")
    else:
        st.error(f"🔒 **Has alcanzado el límite mensual de tu {PLANES[tipo_plan]['nombre']}.**")
        
    st.markdown("### 🚀 Elige un plan profesional para continuar sin límites:")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("#### Plan Básico")
        st.markdown("**19€ / mes**\n* 150 facturas\n* Soporte estándar")
        st.markdown(f"[Suscribirme (19€)]({URL_GUMROAD_19})", unsafe_allow_html=True)
    with c2:
        st.markdown("#### Plan Pro")
        st.markdown("**49€ / mes**\n* 600 facturas\n* Soporte prioritario")
        st.markdown(f"[Suscribirme (49€)]({URL_GUMROAD_49})", unsafe_allow_html=True)
    with c3:
        st.markdown("#### Plan Enterprise")
        st.markdown("**89€ / mes**\n* 2.000 facturas\n* Soporte VIP")
        st.markdown(f"[Suscribirme (89€)]({URL_GUMROAD_89})", unsafe_allow_html=True)
        
    st.stop()

# -----------------------------------------------------------------------------
# 4. PROCESAMIENTO DE ARCHIVOS CON GEMINI (OPTIMIZADO MULTIPÁGINA)
# -----------------------------------------------------------------------------
api_key = os.environ.get("GEMINI_API_KEY", "")

if not api_key:
    st.warning("⚠️ Clave de API no configurada en las variables de entorno.")
else:
    client = genai.Client(api_key=api_key)

    uploaded_files = st.file_uploader(
        f"Sube tus albaranes y facturas (Máximo {facturas_restantes} en este lote):",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True
    )

    def procesar_un_archivo(uploaded_file):
        file_name = uploaded_file.name
        file_ext = file_name.split('.')[-1].lower()
        
        prompt_extraccion = """
        Extrae los datos fiscales de este documento y devuélvelo ÚNICAMENTE en formato JSON válido, sin texto adicional ni bloques de markdown:
        {
            "proveedor": "Nombre del proveedor",
            "nif_proveedor": "NIF o CIF",
            "fecha": "DD/MM/YYYY",
            "numero_factura": "Número",
            "base_imponible": 0.0,
            "cuota_iva": 0.0,
            "importe_total": 0.0,
            "conceptos_resumen": "Breve resumen"
        }
        """

        config_json = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1
        )

        try:
            json_response = ""
            uploaded_file.seek(0)
            
            if file_ext == 'pdf':
                pdf_reader = pypdf.PdfReader(uploaded_file)
                texto_pdf = ""
                for page in pdf_reader.pages:
                    text = page.extract_text()
                    if text:
                        texto_pdf += text + "\n"

                if texto_pdf and len(texto_pdf.strip()) > 30:
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[f"{prompt_extraccion}\n\nTexto del documento:\n{texto_pdf}"],
                        config=config_json
                    )
                    json_response = response.text
                else:
                    uploaded_file.seek(0)
                    from pdf2image import convert_from_bytes
                    
                    # Convertimos la primera página (cabecera y datos)
                    primera_img = convert_from_bytes(uploaded_file.read(), first_page=1, last_page=1)
                    
                    # Comprobamos el total de páginas del PDF
                    uploaded_file.seek(0)
                    reader_temp = pypdf.PdfReader(uploaded_file)
                    total_paginas = len(reader_temp.pages)
                    
                    images_a_procesar = primera_img
                    
                    # Si tiene más de 1 página (ej. 5 o 10), añadimos la última página (donde está el total)
                    if total_paginas > 1:
                        uploaded_file.seek(0)
                        ultima_img = convert_from_bytes(uploaded_file.read(), first_page=total_paginas, last_page=total_paginas)
                        images_a_procesar.extend(ultima_img)

                    if images_a_procesar:
                        imgs_procesadas = []
                        for img in images_a_procesar:
                            img.thumbnail((600, 600))
                            img_byte_arr = io.BytesIO()
                            img.convert("RGB").save(img_byte_arr, format="JPEG", quality=50)
                            img_byte_arr.seek(0)
                            imgs_procesadas.append(Image.open(img_byte_arr))
                        
                        contenido_gemini = imgs_procesadas + [prompt_extraccion]
                        
                        response = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=contenido_gemini,
                            config=config_json
                        )
                        json_response = response.text

            elif file_ext in ['png', 'jpg', 'jpeg']:
                with Image.open(uploaded_file) as imagen:
                    imagen.thumbnail((600, 600))
                    img_byte_arr = io.BytesIO()
                    imagen.convert("RGB").save(img_byte_arr, format="JPEG", quality=50)
                    img_byte_arr.seek(0)
                    
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[Image.open(img_byte_arr), prompt_extraccion],
                        config=config_json
                    )
                    json_response = response.text

            json_response = json_response.strip()
            if json_response.startswith("```json"):
                json_response = json_response[7:]
            if json_response.endswith("```"):
                json_response = json_response[:-3]
            json_response = json_response.strip()

            parsed_data = json.loads(json_response)
            parsed_data["archivo"] = file_name
            return parsed_data

        except Exception as e:
            return {"archivo": file_name, "error": str(e)}

    # -----------------------------------------------------------------------------
    # 5. EJECUCIÓN Y ACTUALIZACIÓN EN SERVIDOR
    # -----------------------------------------------------------------------------
    if uploaded_files:
        cant_archivos = len(uploaded_files)
        
        if cant_archivos > facturas_restantes:
            st.error(f"⚠️ Has seleccionado {cant_archivos} archivos, pero a tu gestoría solo le quedan {facturas_restantes} facturas.")
        else:
            if st.button("⚡ Procesar Documentos", type="primary"):
                datos_tabla = []
                barra_progreso = st.progress(0, text="🚀 Procesando documentos...")
                
                tamano_lote = 5
                for i in range(0, cant_archivos, tamano_lote):
                    lote = uploaded_files[i:i + tamano_lote]
                    
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        resultados_lote = list(executor.map(procesar_un_archivo, lote))
                    
                    for res in resultados_lote:
                        if "error" in res:
                            st.error(f"❌ Error en {res['archivo']}: {res['error']}")
                        else:
                            datos_tabla.append(res)
                            
                            # Actualizar consumo en el servidor para esta gestoría específica
                            bd = cargar_bd()
                            if usuario_key in bd:
                                bd[usuario_key]["gastadas"] = bd[usuario_key].get("gastadas", 0) + 1
                                guardar_bd(bd)
                    
                    gc.collect()

                    progreso_actual = min(int(((i + len(lote)) / cant_archivos) * 100), 100)
                    barra_progreso.progress(progreso_actual, text=f"🚀 Procesados {i + len(lote)} de {cant_archivos}...")
                    time.sleep(0.3)

                barra_progreso.empty()

                if datos_tabla:
                    st.success("✅ ¡Procesamiento completado con éxito!")
                    df = pd.DataFrame(datos_tabla)
                    st.dataframe(df, use_container_width=True)
                    
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False, sheet_name='Facturas')
                    excel_data = output.getvalue()
                    
                    st.download_button(
                        label="📥 Descargar Excel para Contabilidad",
                        data=excel_data,
                        file_name="facturas_procesadas.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    
                    st.rerun()
