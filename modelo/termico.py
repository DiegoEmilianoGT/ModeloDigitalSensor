"""Modelo termico de una zona (la que mide un sensor) y deteccion de anomalias.

La zona se trata como un sistema de primer orden que tiende a una temperatura de equilibrio
que cambia a lo largo del dia:

    dT/dt = (T_eq(t) - T) / tau        T_eq(t) = nivel + perfil(hora, laboral o fin de semana)

En pasos de 10 min:  x[k+1] = phi * x[k] + f(t_k),  con x = T - nivel  y  phi = exp(-PASO / tau).
El nivel es el promedio de las ultimas 24 h (absorbe lo lento, como el clima) y f es una serie
de Fourier diaria, distinta para dias laborales y fines de semana.

Una medicion es anomala cuando se aparta de lo que el modelo previo HORIZONTE pasos antes mas
de lo que el historial considera normal a esa hora.

Las series son listas alineadas: marcas (epoch del inicio de cada promedio de 10 min, sin saltos)
y valores (°C, o None donde no hubo datos). Solo ajustar() necesita numpy; lo demas es Python puro
para que la API pueda usarlo en vivo.
"""
import math
import statistics
import time

PASO = 600              # segundos por punto
VENTANA_NIVEL = 144     # puntos que promedia el nivel (24 h)
MINIMO_NIVEL = 72       # con menos de 12 h de datos no hay nivel
ARMONICOS = 3           # terminos de la serie de Fourier diaria
HORIZONTE = 12          # pasos entre la prediccion y la comparacion (2 h)
CUANTIL = 0.99          # el umbral se fija para que el historial solo lo supere el 1 % del tiempo
UMBRAL_MINIMO = 3.5     # desviaciones: con un historial muy tranquilo el 1 % mas raro seguiria siendo normal
RESIDUO_MINIMO = 0.5    # °C: una diferencia menor no se marca aunque sea rara a esa hora
SIGMA_MINIMA = 0.12     # °C: piso de la dispersion, cerca de la resolucion de los sensores
DURACION_MINIMA = 2     # puntos anomalos seguidos para hablar de un episodio (20 min)


def tipo_y_hora(marca):
    t = time.localtime(marca)
    return (1 if t.tm_wday >= 5 else 0), t.tm_hour + t.tm_min / 60


def base(marca):
    # [1, cos, sen, ...] en las posiciones del tipo de dia que toca; ceros en las del otro
    tipo, hora = tipo_y_hora(marca)
    b = [1.0]
    for m in range(1, ARMONICOS + 1):
        b += [math.cos(2 * math.pi * m * hora / 24), math.sin(2 * math.pi * m * hora / 24)]
    ceros = [0.0] * len(b)
    return ceros + b if tipo else b + ceros


def forzamiento(modelo, marca):
    return sum(c * b for c, b in zip(modelo["coef"], base(marca)))


def equilibrio(modelo, marca):
    """Cuanto por encima del nivel se estabilizaria la zona si las condiciones de ese instante no cambiaran."""
    return forzamiento(modelo, marca) / (1 - modelo["phi"])


def niveles(valores):
    salida, suma, cuenta = [], 0.0, 0
    for i, v in enumerate(valores):
        if v is not None:
            suma += v
            cuenta += 1
        if i >= VENTANA_NIVEL and valores[i - VENTANA_NIVEL] is not None:
            suma -= valores[i - VENTANA_NIVEL]
            cuenta -= 1
        salida.append(suma / cuenta if cuenta >= MINIMO_NIVEL else None)
    return salida


def ajustar(marcas, valores):
    """Minimos cuadrados de x[k+1] contra x[k] y la base diaria, restando peso a los puntos atipicos."""
    import numpy as np

    nivel = niveles(valores)
    X, y = [], []
    for k in range(len(valores) - 1):
        if valores[k] is None or valores[k + 1] is None or nivel[k] is None:
            continue
        X.append([valores[k] - nivel[k]] + base(marcas[k]))
        y.append(valores[k + 1] - nivel[k])
    X, y = np.array(X), np.array(y)
    pesos = np.ones(len(y))
    for _ in range(8):  # pesos de Huber: los sustos (puertas, manipulacion del sensor) no deben mover el ajuste
        beta, *_ = np.linalg.lstsq(X * pesos[:, None] ** 0.5, y * pesos ** 0.5, rcond=None)
        residuo = y - X @ beta
        escala = 1.4826 * np.median(np.abs(residuo - np.median(residuo)))
        pesos = np.minimum(1, 1.5 * escala / np.maximum(np.abs(residuo), 1e-12))
    phi = float(beta[0])
    if not 0 < phi < 1:
        raise ValueError(f"El ajuste no dio una zona estable (phi = {phi:.3f})")
    return {"phi": phi, "tau_horas": -PASO / math.log(phi) / 3600, "coef": [float(b) for b in beta[1:]]}


def pronosticar(modelo, valor, nivel, marca, pasos=HORIZONTE):
    """Temperaturas previstas para los siguientes pasos, partiendo de valor en el instante marca."""
    x, salida = valor - nivel, []
    for j in range(pasos):
        x = modelo["phi"] * x + forzamiento(modelo, marca + j * PASO)
        salida.append(nivel + x)
    return salida


def tolerancia(modelo, marca):
    tipo, hora = tipo_y_hora(marca)
    return max(modelo["umbral"] * modelo["sigma"][tipo][int(hora)], RESIDUO_MINIMO)


def seguir(modelo, marcas, valores):
    """Compara cada medicion con lo previsto HORIZONTE pasos antes.

    Devuelve por punto (previsto, residuo, anomalo); los dos primeros son None si no se pudo comparar.
    Si el modelo aun no esta calibrado (sin sigma ni umbral) nada sale anomalo.
    """
    nivel = niveles(valores)
    calibrado = "umbral" in modelo
    puntos = []
    for k in range(len(valores)):
        origen = k - HORIZONTE
        previsto = residuo = None
        anomalo = False
        if origen >= 0 and valores[origen] is not None and nivel[origen] is not None:
            previsto = pronosticar(modelo, valores[origen], nivel[origen], marcas[origen])[-1]
            if valores[k] is not None:
                residuo = valores[k] - previsto
                anomalo = calibrado and abs(residuo) >= tolerancia(modelo, marcas[k])
                # la prediccion salio de un punto ya anomalo en sentido contrario: es la vuelta a lo normal
                if anomalo and puntos[origen][2] and puntos[origen][1] * residuo < 0:
                    anomalo = False
        puntos.append((previsto, residuo, anomalo))
    return puntos


def calibrar(modelo, marcas, valores):
    """Mide con el historial que tan lejos de la prediccion es normal estar a cada hora."""
    nivel = niveles(valores)
    por_paso = [[] for _ in range(HORIZONTE)]
    por_hora = {}
    for k in range(len(valores) - 1):
        if valores[k] is None or nivel[k] is None:
            continue
        for j, previsto in enumerate(pronosticar(modelo, valores[k], nivel[k], marcas[k])):
            destino = k + j + 1
            if destino >= len(valores) or valores[destino] is None:
                continue
            residuo = valores[destino] - previsto
            por_paso[j].append(residuo)
            if j == HORIZONTE - 1:
                tipo, hora = tipo_y_hora(marcas[destino])
                por_hora.setdefault((tipo, int(hora)), []).append(residuo)

    def dispersion(residuos):  # desviacion tipica robusta: no la inflan los episodios raros
        centro = statistics.median(residuos)
        return 1.4826 * statistics.median(abs(r - centro) for r in residuos)

    cruda = {clave: dispersion(residuos) for clave, residuos in por_hora.items()}
    general = dispersion([r for residuos in por_hora.values() for r in residuos])
    sigma = []
    for tipo in (0, 1):
        fila = []
        for hora in range(24):  # se suaviza con las horas vecinas; sin datos de ese tipo de dia, la general
            vecinas = [cruda[(tipo, (hora + d) % 24)] for d in (-1, 0, 1) if (tipo, (hora + d) % 24) in cruda]
            fila.append(max(sum(vecinas) / len(vecinas) if vecinas else general, SIGMA_MINIMA))
        sigma.append(fila)

    puntuaciones = sorted(
        abs(r) / sigma[clave[0]][clave[1]] for clave, residuos in por_hora.items() for r in residuos)
    return {
        "sigma": sigma,
        "umbral": max(puntuaciones[int(CUANTIL * len(puntuaciones))], UMBRAL_MINIMO),
        "error_por_paso": [dispersion(residuos) for residuos in por_paso],
    }


def episodios(marcas, puntos):
    """Tramos de al menos DURACION_MINIMA puntos anomalos seguidos: (inicio, fin, mayor residuo)."""
    lista, inicio = [], None
    for k in range(len(puntos) + 1):
        anomalo = k < len(puntos) and puntos[k][2]
        if anomalo and inicio is None:
            inicio = k
        elif not anomalo and inicio is not None:
            if k - inicio >= DURACION_MINIMA:
                lista.append((marcas[inicio], marcas[k - 1], max((p[1] for p in puntos[inicio:k]), key=abs)))
            inicio = None
    return lista
