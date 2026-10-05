def extraer_datos_con_gemini(pdf_bytes, api_key):
    """Envía el albarán optimizado a Gemini Flash de forma rápida y segura."""
    genai.configure(api_key=api_key)
    
    # 1. Convertir la primera página a una resolución ligera (120 DPI) para que vuele
    imagenes = convert_from_bytes(pdf_bytes, first_page=1, last_page=1, dpi=120)
    if not imagenes:
        return None

    imagen_pil = imagenes[0]

    prompt = (
        "Eres un asistente contable experto. Analiza este documento comercial (albarán o factura) "
        "y extrae la información en un formato JSON estricto con estas 4 claves exactas:\n"
        '{"proveedor": "Nombre de la empresa emisora", "cif": "NIF o CIF o vacio", '
        '"fecha": "DD/MM/AAAA o vacio", "total": 0.0}\n'
        "Devuelve ÚNICAMENTE el objeto JSON válido, sin bloques de código markdown ni texto adicional."
    )

    # 2. Usar el modelo oficial actual y temperature=0 para velocidad máxima
    model = genai.GenerativeModel(
        model_name="gemini-3.8-flash",
        generation_config={"temperature": 0.0}
    )

    response = model.generate_content([prompt, imagen_pil])
    texto_respuesta = response.text.strip()

    # Limpiar marcas de formato markdown
    texto_respuesta = re.sub(r"^```json\s*", "", texto_respuesta)
    texto_respuesta = re.sub(r"^```\s*", "", texto_respuesta)
    texto_respuesta = re.sub(r"\s*```$", "", texto_respuesta)

    datos = json.loads(texto_respuesta)
    return datos
