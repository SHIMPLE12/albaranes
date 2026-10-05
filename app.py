def extraer_datos_con_gemini(pdf_bytes, api_key):
    """Extrae datos de forma ultrarrápida: primero intenta leer texto directo, y si no, usa la IA con imagen."""
    genai.configure(api_key=api_key)
    
    # 1. INTENTO VELOCIDAD MÁXIMA: Leer texto directo del PDF (Cero espera de imagen)
    texto_pdf = ""
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        if len(reader.pages) > 0:
            texto_pdf = reader.pages[0].extract_text()
    except:
        pass

    model = genai.GenerativeModel(
        model_name="gemini-3.8-flash",
        generation_config={"temperature": 0.0}
    )

    prompt = (
        "Eres un asistente contable experto. Analiza este documento comercial (albarán o factura) "
        "y extrae la información en un formato JSON estricto con estas 4 claves exactas:\n"
        '{"proveedor": "Nombre de la empresa emisora", "cif": "NIF o CIF o vacio", '
        '"fecha": "DD/MM/AAAA o vacio", "total": 0.0}\n'
        "Devuelve ÚNICAMENTE el objeto JSON válido, sin bloques de código markdown ni texto adicional."
    )

    # 2. Si el PDF tiene texto digital limpio (como la mayoría de facturas actuales), se lo mandamos a Gemini como TEXTO plano (¡Vuela!)
    if texto_pdf and len(texto_pdf.strip()) > 50:
        response = model.generate_content([prompt, f"Texto de la factura:\n{texto_pdf}"])
    else:
        # 3. Si es un PDF escaneado (una foto), recurrimos a la imagen de forma ligera
        imagenes = convert_from_bytes(pdf_bytes, first_page=1, last_page=1, dpi=96)
        if not imagenes:
            return None
        response = model.generate_content([prompt, imagenes[0]])

    texto_respuesta = response.text.strip()

    # Limpiar marcas de formato markdown
    texto_respuesta = re.sub(r"^```json\s*", "", texto_respuesta)
    texto_respuesta = re.sub(r"^```\s*", "", texto_respuesta)
    texto_respuesta = re.sub(r"\s*```$", "", texto_respuesta)

    datos = json.loads(texto_respuesta)
    return datos
