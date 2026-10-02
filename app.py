def extraer_datos_con_gemini(pdf_bytes, api_key):
    """Envía el albarán convertido en imagen a Gemini para que extraiga los datos clave."""
    genai.configure(api_key=api_key)
    # Usamos gemini-1.5-flash como modelo principal estándar y rápido
    model = genai.GenerativeModel("gemini-1.5-flash")

    # Convertir la primera página del PDF en imagen para que la IA la "vea"
    imagenes = convert_from_bytes(pdf_bytes, first_page=1, last_page=1, dpi=200)
    if not imagenes:
        return None

    imagen_pil = imagenes[0]

    prompt = (
        "Analiza este documento comercial (albarán o factura). Extrae estrictamente"
        " en formato JSON puro, sin explicaciones ni bloques markdown de código"
        " (nada de ```json), exactamente con estas 4 claves:\n"
        '{"proveedor": "Nombre de la empresa emisora", "cif": "NIF o CIF o vacio", '
        '"fecha": "DD/MM/AAAA o vacio", "total": 0.0}'
    )

    response = model.generate_content([prompt, imagen_pil])
    texto_respuesta = response.text.strip()

    # Limpiar posibles marcas de formato markdown de la respuesta de la IA
    texto_respuesta = re.sub(r"^```json\s*", "", texto_respuesta)
    texto_respuesta = re.sub(r"^```\s*", "", texto_respuesta)
    texto_respuesta = re.sub(r"\s*```$", "", texto_respuesta)

    datos = json.loads(texto_respuesta)
    return datos
