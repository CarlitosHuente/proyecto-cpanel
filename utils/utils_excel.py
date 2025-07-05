from openpyxl.styles import numbers

def aplicar_formato_numerico_excel(cell):
    if isinstance(cell.value, (int, float)):
        # Esto es formato personalizado: separador de miles punto y decimal coma
        cell.number_format = '#.##0,00'
