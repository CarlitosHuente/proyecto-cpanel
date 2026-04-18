from flask import Blueprint, render_template
from utils.auth import login_requerido, permiso_modulo

utilidades_bp = Blueprint('utilidades', __name__, url_prefix='/utilidades')

@utilidades_bp.route('/calculadora_margen')
@login_requerido
@permiso_modulo("utilidades")
def calculadora_margen():
    """Calculadora de margen comercial rápida."""
    return render_template('utilidades/calculadora_margen.html')