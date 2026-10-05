import io
import json
import re
import time
import zipfile
import google.generativeai as genai
from pdf2image import convert_from_bytes
import pandas as pd
import pypdf
import streamlit as st
import plotly.express as px
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Configuración básica de la página
st.set_page_config(
    page_title="Gestor IA Pro de Albaranes", page_icon="🤖", layout="wide"
)

# Forzamos una traza visual de prueba por si acaso
st.title("🤖 Gestor y Lector IA de Albaranes")
st.write("¡Aplicación iniciada correctamente!")
