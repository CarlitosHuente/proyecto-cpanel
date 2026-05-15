/**
 * Presentación Huente — front-end (alineado a utils/formato_dinero.py y bitácora sección K).
 * Pesos CLP: siempre enteros (sin decimales visibles).
 * Porcentajes: típicamente 1 decimal (quien llama usa .toFixed(1)).
 * Métricos (kg, etc.): hasta 2 decimales, sin forzar ceros a la derecha.
 */
(function () {
    const optPeso = {
        style: "currency",
        currency: "CLP",
        maximumFractionDigits: 0,
        minimumFractionDigits: 0,
    };
    const optEntero = { maximumFractionDigits: 0, minimumFractionDigits: 0 };
    const optMetrico = { maximumFractionDigits: 2, minimumFractionDigits: 0 };

    function peso(n) {
        const v = Math.round(Number(n) || 0);
        return new Intl.NumberFormat("es-CL", optPeso).format(v);
    }

    /** Variación en $ con signo explícito (+/-) y sin decimales. */
    function pesoConSigno(n) {
        const v = Math.round(Number(n) || 0);
        if (v === 0) return peso(0);
        const absFmt = new Intl.NumberFormat("es-CL", optPeso).format(Math.abs(v));
        if (v > 0) return "+" + absFmt;
        return new Intl.NumberFormat("es-CL", optPeso).format(v);
    }

    function entero(n) {
        return new Intl.NumberFormat("es-CL", optEntero).format(Math.round(Number(n) || 0));
    }

    function metrico(n) {
        const x = Number(n);
        if (!Number.isFinite(x)) return "—";
        return new Intl.NumberFormat("es-CL", optMetrico).format(x);
    }

    window.HuenteFmt = { peso, pesoConSigno, entero, metrico };
})();
