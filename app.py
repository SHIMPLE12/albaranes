# --- ADICIÓN: Gráficos y Exportación a Excel Profesional ---
if 'df_resultados' in locals() and not df_resultados.empty:
    st.markdown("---")
    st.subheader("📊 Análisis y Gráficos de Proveedores")
    
    col1, col2 = st.columns(2)
    df_agrupado = df_resultados.groupby('Proveedor')['Total (€)'].sum().reset_index()
    
    with col1:
        fig_barras = px.bar(df_agrupado, x='Proveedor', y='Total (€)', title="Gasto por Proveedor")
        st.plotly_chart(fig_barras, use_container_width=True)
        
    with col2:
        fig_tarta = px.pie(df_agrupado, names='Proveedor', values='Total (€)', title="Porcentaje del Gasto")
        st.plotly_chart(fig_tarta, use_container_width=True)

    st.markdown("---")
    st.subheader("📥 Descargar para Contabilidad")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_resumen_contable = df_resultados.groupby(['Proveedor', 'CIF']).agg(
            N_Facturas=('Archivo', 'count'),
            Total_Euros=('Total (€)', 'sum')
        ).reset_index()
        
        df_resumen_contable.to_excel(writer, sheet_name='Resumen Contable', index=False)
        df_resultados.to_excel(writer, sheet_name='Detalle Facturas', index=False)
    
    excel_data = output.getvalue()

    st.download_button(
        label="📊 Descargar Informe Completo en Excel (.xlsx)",
        data=excel_data,
        file_name="resumen_contable_facturas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
