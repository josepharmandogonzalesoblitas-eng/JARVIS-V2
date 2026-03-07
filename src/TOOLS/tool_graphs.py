"""
HERRAMIENTA DE GRÁFICOS Y VISUALIZACIONES.

Genera imágenes de progreso, energía y estadísticas usando matplotlib.
Las imágenes se envían como fotos por Telegram.

Requiere: matplotlib, Pillow
"""

import os
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("tool_graphs")

# Paleta de colores oscura para JARVIS
COLORES = {
    "fondo": "#0d0d1a",
    "panel": "#16213e",
    "acento": "#00d4ff",
    "oro": "#ffd700",
    "verde": "#2ECC71",
    "naranja": "#F39C12",
    "rojo": "#E74C3C",
    "gris": "#aaaaaa",
    "borde": "#333366",
    "texto": "#ffffff"
}


def _setup_matplotlib():
    """Configura matplotlib con backend no-GUI."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec
        return plt, gridspec
    except ImportError:
        logger.error("matplotlib no instalado. Ejecuta: pip install matplotlib")
        raise


def _guardar_grafico(plt, nombre: str) -> str:
    """Guarda el gráfico en el directorio temporal y retorna la ruta."""
    os.makedirs("LOGS/temp", exist_ok=True)
    timestamp = int(datetime.now().timestamp() * 1000)
    path = os.path.join("LOGS", "temp", f"{nombre}_{timestamp}.png")
    plt.savefig(
        path,
        dpi=150,
        bbox_inches='tight',
        facecolor=COLORES["fondo"],
        edgecolor='none'
    )
    plt.close()
    logger.info(f"Gráfico guardado: {path}")
    return path


def generar_grafico_energia(dias: int = 7) -> Optional[str]:
    """
    Genera gráfico de barras con el nivel de energía de los últimos N días.

    Returns:
        Ruta al archivo .png generado, o None si no hay datos suficientes.
    """
    try:
        plt, _ = _setup_matplotlib()
        import matplotlib.dates as mdates
        from src.data import db_handler, schemas

        bitacora = db_handler.read_data("bitacora.json", schemas.GestorBitacora)

        # Recopilar todos los días disponibles
        todos_dias = dict(sorted(bitacora.historico_dias.items()))
        hoy = datetime.now().strftime("%Y-%m-%d")
        if bitacora.dia_actual and bitacora.dia_actual.fecha == hoy:
            todos_dias[hoy] = bitacora.dia_actual

        ultimos = list(todos_dias.items())[-dias:]

        if len(ultimos) < 2:
            logger.warning("Gráfico energía: datos insuficientes (menos de 2 días).")
            return None

        fechas = [datetime.strptime(f, "%Y-%m-%d") for f, _ in ultimos]
        energias = [r.nivel_energia for _, r in ultimos]
        estados = [r.estado_animo[:10] for _, r in ultimos]

        # Colores dinámicos por nivel de energía
        colores = []
        for e in energias:
            if e >= 7:
                colores.append(COLORES["verde"])
            elif e >= 4:
                colores.append(COLORES["naranja"])
            else:
                colores.append(COLORES["rojo"])

        # --- FIGURA ---
        fig, ax = plt.subplots(figsize=(10, 5))
        fig.patch.set_facecolor(COLORES["fondo"])
        ax.set_facecolor(COLORES["panel"])

        bars = ax.bar(fechas, energias, color=colores, alpha=0.85, width=0.6)

        # Línea de promedio
        if energias:
            promedio = sum(energias) / len(energias)
            ax.axhline(
                y=promedio, color=COLORES["acento"], linestyle='--',
                alpha=0.7, linewidth=1.5, label=f'Promedio: {promedio:.1f}'
            )

        # Etiquetas sobre barras
        for bar, val, estado in zip(bars, energias, estados):
            ax.text(
                bar.get_x() + bar.get_width() / 2., bar.get_height() + 0.2,
                str(val), ha='center', va='bottom',
                color=COLORES["texto"], fontsize=11, fontweight='bold'
            )

        # Estilo
        ax.set_ylim(0, 12)
        ax.set_title(
            f'⚡ Nivel de Energía — Últimos {len(ultimos)} días',
            color=COLORES["texto"], fontsize=14, fontweight='bold', pad=15
        )
        ax.set_xlabel('Fecha', color=COLORES["gris"], fontsize=10)
        ax.set_ylabel('Energía (1-10)', color=COLORES["gris"], fontsize=10)
        ax.tick_params(colors=COLORES["gris"], labelsize=9)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')
        ax.legend(facecolor=COLORES["fondo"], labelcolor=COLORES["texto"], fontsize=10)

        for spine in ax.spines.values():
            spine.set_edgecolor(COLORES["borde"])

        plt.tight_layout()
        return _guardar_grafico(plt, "energia")

    except ImportError:
        return None
    except Exception as e:
        logger.error(f"Error generando gráfico de energía: {e}", exc_info=True)
        return None


def generar_grafico_progreso_proyecto(nombre_proyecto: str) -> Optional[str]:
    """
    Genera gráfico de progreso para un proyecto específico (pie + barra).

    Returns:
        Ruta al archivo .png, o None si el proyecto no existe.
    """
    try:
        plt, _ = _setup_matplotlib()
        from src.data import db_handler, schemas

        proyectos = db_handler.read_data("proyectos.json", schemas.GestorProyectos)

        if nombre_proyecto not in proyectos.proyectos_activos:
            logger.warning(f"Proyecto '{nombre_proyecto}' no encontrado.")
            return None

        proyecto = proyectos.proyectos_activos[nombre_proyecto]
        total = len(proyecto.tareas_pendientes)
        if total == 0:
            logger.warning("Proyecto sin tareas registradas.")
            return None

        completadas = len([t for t in proyecto.tareas_pendientes if t.estado == 'completado'])
        en_proceso = len([t for t in proyecto.tareas_pendientes if t.estado == 'en_proceso'])
        bloqueadas = len([t for t in proyecto.tareas_pendientes if t.estado == 'bloqueado'])
        pendientes = total - completadas - en_proceso - bloqueadas

        porcentaje = round((completadas / total) * 100)

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        fig.patch.set_facecolor(COLORES["fondo"])

        # --- PIE CHART ---
        ax1.set_facecolor(COLORES["fondo"])
        sizes = [max(0, x) for x in [completadas, en_proceso, bloqueadas, pendientes]]
        labels_pie = ['Completadas', 'En Proceso', 'Bloqueadas', 'Pendientes']
        colors_pie = [COLORES["verde"], COLORES["acento"], COLORES["rojo"], COLORES["gris"]]
        valid = [(s, l, c) for s, l, c in zip(sizes, labels_pie, colors_pie) if s > 0]
        if valid:
            s_v, l_v, c_v = zip(*valid)
            ax1.pie(
                s_v, labels=l_v, colors=c_v,
                autopct='%1.0f%%', startangle=90,
                textprops={'color': COLORES["texto"], 'fontsize': 9},
                wedgeprops={'edgecolor': COLORES["fondo"], 'linewidth': 1.5}
            )
        nombre_corto = nombre_proyecto[:22] + "..." if len(nombre_proyecto) > 22 else nombre_proyecto
        ax1.set_title(f'📋 {nombre_corto}', color=COLORES["texto"], fontsize=12, fontweight='bold')

        # --- BARRA DE PROGRESO ---
        ax2.set_facecolor(COLORES["panel"])
        ax2.barh(['Progreso'], [porcentaje], color=COLORES["verde"], height=0.4)
        ax2.barh(['Progreso'], [100 - porcentaje], left=[porcentaje], color=COLORES["borde"], height=0.4)
        ax2.set_xlim(0, 100)
        ax2.set_title('🎯 Progreso Total', color=COLORES["texto"], fontsize=12, fontweight='bold')
        ax2.text(
            50, 0, f'{porcentaje}%', ha='center', va='center',
            color=COLORES["texto"], fontsize=22, fontweight='bold'
        )
        ax2.text(
            50, -0.4, f'{completadas}/{total} tareas completadas',
            ha='center', va='center', color=COLORES["gris"], fontsize=10
        )
        ax2.tick_params(colors=COLORES["gris"])
        ax2.set_yticks([])
        for spine in ax2.spines.values():
            spine.set_edgecolor(COLORES["borde"])

        plt.tight_layout()
        return _guardar_grafico(plt, f"proyecto_{nombre_proyecto[:12].replace(' ', '_')}")

    except ImportError:
        return None
    except Exception as e:
        logger.error(f"Error generando gráfico de proyecto: {e}", exc_info=True)
        return None


def generar_resumen_mensual() -> Optional[str]:
    """
    Genera un resumen visual del mes actual:
    - Línea de energía en el tiempo
    - Distribución alta/media/baja
    - Estadísticas clave del mes

    Returns:
        Ruta al archivo .png, o None si hay insuficientes datos.
    """
    try:
        plt, gridspec = _setup_matplotlib()
        import calendar
        from src.data import db_handler, schemas

        bitacora = db_handler.read_data("bitacora.json", schemas.GestorBitacora)
        hoy = datetime.now()
        mes_actual = hoy.strftime("%Y-%m")

        # Filtrar días del mes
        dias_mes = {}
        for fecha, registro in bitacora.historico_dias.items():
            if fecha.startswith(mes_actual):
                dias_mes[fecha] = registro
        if bitacora.dia_actual and bitacora.dia_actual.fecha.startswith(mes_actual):
            dias_mes[bitacora.dia_actual.fecha] = bitacora.dia_actual

        if not dias_mes:
            logger.warning("Sin datos del mes actual para resumen.")
            return None

        fechas_ord = sorted(dias_mes.keys())
        energias = [dias_mes[f].nivel_energia for f in fechas_ord]
        promedio = sum(energias) / len(energias)
        dias_alta = len([e for e in energias if e >= 7])
        dias_media = len([e for e in energias if 4 <= e <= 6])
        dias_baja = len([e for e in energias if e <= 3])

        fig = plt.figure(figsize=(14, 7))
        fig.patch.set_facecolor(COLORES["fondo"])
        gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.45, wspace=0.3)

        # 1. Gráfico de línea de energía (fila entera)
        ax1 = fig.add_subplot(gs[0, :])
        ax1.set_facecolor(COLORES["panel"])
        x = list(range(len(fechas_ord)))
        ax1.fill_between(x, energias, alpha=0.25, color=COLORES["acento"])
        ax1.plot(x, energias, color=COLORES["acento"], linewidth=2, marker='o', markersize=4)
        ax1.axhline(
            y=promedio, color=COLORES["oro"], linestyle='--',
            alpha=0.7, linewidth=1.2, label=f'Promedio mes: {promedio:.1f}'
        )
        ax1.set_ylim(0, 11)
        nombre_mes = calendar.month_name[hoy.month]
        ax1.set_title(
            f'📈 Energía Diaria — {nombre_mes} {hoy.year}',
            color=COLORES["texto"], fontsize=13, fontweight='bold'
        )
        ax1.tick_params(colors=COLORES["gris"])
        paso = max(1, len(fechas_ord) // 8)
        ax1.set_xticks(x[::paso])
        ax1.set_xticklabels([f[-5:] for f in fechas_ord[::paso]], rotation=30, fontsize=8)
        ax1.legend(facecolor=COLORES["fondo"], labelcolor=COLORES["texto"])
        for spine in ax1.spines.values():
            spine.set_edgecolor(COLORES["borde"])

        # 2. Distribución
        ax2 = fig.add_subplot(gs[1, 0])
        ax2.set_facecolor(COLORES["panel"])
        cats = ['Alta (7-10)', 'Media (4-6)', 'Baja (1-3)']
        vals = [dias_alta, dias_media, dias_baja]
        cols = [COLORES["verde"], COLORES["naranja"], COLORES["rojo"]]
        bars = ax2.bar(cats, vals, color=cols, alpha=0.85)
        for bar, val in zip(bars, vals):
            if val > 0:
                ax2.text(
                    bar.get_x() + bar.get_width() / 2., bar.get_height() + 0.1,
                    str(val), ha='center', color=COLORES["texto"], fontsize=11, fontweight='bold'
                )
        ax2.set_title('📊 Distribución de Energía', color=COLORES["texto"], fontsize=11)
        ax2.tick_params(colors=COLORES["gris"])
        for spine in ax2.spines.values():
            spine.set_edgecolor(COLORES["borde"])

        # 3. Estadísticas clave
        ax3 = fig.add_subplot(gs[1, 1])
        ax3.set_facecolor(COLORES["panel"])
        ax3.axis('off')
        stats = [
            ('📅 Días registrados:', str(len(fechas_ord))),
            ('⚡ Energía promedio:', f'{promedio:.1f}/10'),
            ('🔥 Días alta energía:', str(dias_alta)),
            ('😴 Días baja energía:', str(dias_baja)),
            ('📊 Rango energía:', f'{min(energias)} – {max(energias)}'),
        ]
        for i, (label, valor) in enumerate(stats):
            ax3.text(0.05, 0.88 - i * 0.18, label, transform=ax3.transAxes,
                     color=COLORES["gris"], fontsize=10)
            ax3.text(0.65, 0.88 - i * 0.18, valor, transform=ax3.transAxes,
                     color=COLORES["acento"], fontsize=10, fontweight='bold')
        ax3.set_title('📋 Resumen del Mes', color=COLORES["texto"], fontsize=11)

        return _guardar_grafico(plt, "resumen_mensual")

    except ImportError:
        return None
    except Exception as e:
        logger.error(f"Error generando resumen mensual: {e}", exc_info=True)
        return None
