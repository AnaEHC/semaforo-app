# --- IMPORTS ---
import streamlit as st
import pandas as pd
import os
import io
import requests  # ✅ Para conectarse a la API PHP
from datetime import datetime, timedelta

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Ruta Semáforo: Del Contacto al Cierre", page_icon="🚦", layout="wide")
st.title("🚦 Ruta Semáforo: Del Contacto al Cierre")

# --- COLORES DEL SEMÁFORO (estilo visual) ---
colores_semaforo = {
    "AZUL - FINALIZADO": ("#0070C0", "#ffffff"),
    "VERDE": ("#00B050", "#ffffff"),
    "AMARILLO": ("#FFFF00", "#000000"),
    "ROJO": ("#FF0000", "#ffffff"),
    "": ("#F2F2F2", "#000000")
}

# --- API URL ---
API_URL = "https://ehclegislacionymarketing.es/api_semaforo.php"

# --- Obtener festivos desde API ---
def obtener_festivos():
    try:
        response = requests.post(API_URL, data={"accion": "festivos"})
        response.raise_for_status()

        fechas_json = response.json()

        if not isinstance(fechas_json, list) or not fechas_json:
            return set()

        fechas = set([pd.to_datetime(f).date() for f in fechas_json])
        return fechas

    except Exception as e:
        return set()

# Cargar festivos desde API
festivos = obtener_festivos()

# --- FUNCIONES GLOBALES ---
def calcular_dia_habil(fecha, festivos):
    while fecha.weekday() >= 5 or fecha in festivos:
        fecha += timedelta(days=1)
    return fecha

def dias_habiles(fecha_entrada):
    if pd.isna(fecha_entrada):
        return 0
    try:
        fecha = pd.to_datetime(fecha_entrada).date()
        hoy = datetime.now().date()
        dias = 0
        while fecha <= hoy:
            if fecha.weekday() < 5 and fecha not in festivos:
                dias += 1
            fecha += timedelta(days=1)
        return dias
    except Exception:
        return 0


        
    
def insertar_cliente(cal, comercial, cliente, fecha_entrada=None):
    if fecha_entrada is None:
        fecha_entrada = calcular_dia_habil(datetime.now().date(), festivos)

    fecha = fecha_entrada
    filas = []
    for i in range(3):
        fila = {
            "CAL": cal,
            "COMERCIAL": comercial,
            "CLIENTE": cliente,
            "DIA": fecha,
            **{p: "❌" for p in productos},
            "SEMAFORO": "",
            "FECHA_ENTRADA": fecha_entrada  # 🔧 Aquí va en las 3 filas
        }
        filas.append(fila)
        fecha = calcular_dia_habil(fecha + timedelta(days=1), festivos)
    return pd.DataFrame(filas)


def actualizar_semaforo(df):
    hoy = datetime.now().date()
    df = df.copy()

    # ✅ Asegurar que la columna DIA existe
    if "DIA" not in df.columns:
        df["DIA"] = pd.NaT

    df["DIA"] = pd.to_datetime(df["DIA"], errors="coerce").dt.date

    # 🔑 Asegurar tipo date
    df["DIA"] = pd.to_datetime(df["DIA"], errors="coerce").dt.date

    for cliente in df["CLIENTE"].unique():
        bloque = df[df["CLIENTE"] == cliente].sort_values("DIA")
        if len(bloque) < 3:
            continue  # No tiene 3 días aún, no puede evaluarse

        # Extraemos índices de los 3 días clave
        idxs = bloque.index.tolist()
        checks = bloque[productos].applymap(lambda x: x == "✔").sum(axis=1)
        cruces = bloque[productos].applymap(lambda x: x == "❌").sum(axis=1)

        # AZUL - todos ✔ en cualquier fila
        if any(checks == len(productos)):
            for idx in bloque.index:
                if df.at[idx, "DIA"] <= hoy:
                    df.at[idx, "SEMAFORO"] = "AZUL - FINALIZADO"
                else:
                    df.at[idx, "SEMAFORO"] = ""
            continue

        # VERDE - 1er día con al menos 1 ✔
        if df.at[idxs[0], "DIA"] <= hoy and checks.iloc[0] >= 1:
            df.at[idxs[0], "SEMAFORO"] = "VERDE"

        # AMARILLO - 2º día con al menos 1 ❌
        if df.at[idxs[1], "DIA"] <= hoy and cruces.iloc[1] >= 1:
            df.at[idxs[1], "SEMAFORO"] = "AMARILLO"

        # ROJO - 3er día:
        #     🔴 Si tiene algún ❌
        #     🔴 O si no hay ningún ✔ (bloque en blanco también)
        if df.at[idxs[2], "DIA"] <= hoy:
            if cruces.iloc[2] >= 1 or checks.iloc[2] == 0:
                df.at[idxs[2], "SEMAFORO"] = "ROJO"

    return df.fillna("")

    
    
def estandarizar_fechas(df):
    if "DIA" in df.columns:
        df["DIA"] = pd.to_datetime(df["DIA"], errors="coerce").dt.date
    else:
        df["DIA"] = pd.NaT

    if "FECHA_ENTRADA" in df.columns:
        df["FECHA_ENTRADA"] = pd.to_datetime(df["FECHA_ENTRADA"], errors="coerce")
    else:
        df["FECHA_ENTRADA"] = pd.NaT

    return df


def limpiar_clientes_expirados(df):
    hoy = datetime.now().date()
    clientes_eliminar = []

    for cliente in df["CLIENTE"].unique():
        bloque = df[df["CLIENTE"] == cliente].sort_values("DIA")
        if len(bloque) < 3:
            continue
        primer_dia = bloque.iloc[0]["DIA"]
        fecha_limite = primer_dia
        for _ in range(3):
            fecha_limite = calcular_dia_habil(fecha_limite + timedelta(days=1), festivos)
        if hoy >= fecha_limite:
            clientes_eliminar.append(cliente)

    # 💾 Exportamos los ROJOS vencidos si no han sido ya exportados
    df_rojos = df[
        (df["CLIENTE"].isin(clientes_eliminar)) &
        (df["SEMAFORO"] == "ROJO") &
        ((df["ASIGNADO_CLOSER"].isna()) | (df["ASIGNADO_CLOSER"] == ""))
    ]

    if not df_rojos.empty:
        # ✅ Corregimos la columna para asegurar que FECHA_ENTRADA esté presente
        df_rojos["FECHA_ENTRADA"] = pd.to_datetime(df_rojos["FECHA_ENTRADA"], errors="coerce")
        nombre_archivo = f"{CARPETA_ROJOS}/ROJOS_{usuario_actual}_{hoy}.xlsx"
        df_rojos.to_excel(nombre_archivo, index=False)
        st.success(f"📤 Clientes ROJO exportados: {nombre_archivo}")

    # ❌ OJO: NO borramos del Excel original, solo los ocultamos en Coordinación
    df_filtrado = df[~df["CLIENTE"].isin(clientes_eliminar)]
    return df_filtrado

# --- VARIABLES GLOBALES ---
CARPETA_ROJOS = "ROJOS_PENDIENTES"

os.makedirs(CARPETA_ROJOS, exist_ok=True)




# --- DEFINIR ESTRUCTURA BASE (sin Excel) ---
columnas_base = [
    "CAL", "COMERCIAL", "CLIENTE", "DIA", "SEMAFORO",
    "FECHA_ENTRADA", "ASIGNADO_CLOSER", "FECHA_ASIGNACION_CLOSER",
    "ASIGNADO_SUPERCLOSER", "FECHA_ASIGNACION_SUPERCLOSER",
    "ESTADO_CIERRE", "SEGUIMIENTO_CLOSER", "SEGUIMIENTO_SUPERCLOSER",
    "F2025", "F2026", "HL",
    "CLOSER_F2025", "CLOSER_F2026", "CLOSER_HL",
    "SUPERCLOSER_F2025", "SUPERCLOSER_F2026", "SUPERCLOSER_HL"
]


# --- Cargar días festivos desde API PHP ---
import requests

API_URL = "https://ehclegislacionymarketing.es/api_semaforo.php"


# Llamada real
festivos = obtener_festivos()


# --- Definir productos globales ---
excluidos = ["CAL", "COMERCIAL", "CLIENTE", "DIA", "SEMAFORO", "CLOSER", "OBSERVACIONES CLOSER", "OBSERVACIONES SUPER-CLOSER", "ESTADO FINAL"]
productos = [col for col in columnas_base if col not in excluidos]

# --- Cargar clientes desde la API PHP ---
try:
    response = requests.post(API_URL, data={"accion": "clientes"})
    response.raise_for_status()
    datos_clientes = response.json()

    df = pd.DataFrame(datos_clientes)

    if df.empty:
        st.warning("📭 No hay datos de clientes disponibles.")
    else:
        df = estandarizar_fechas(df)
        df["CAL"] = df["CAL"].astype(str).str.strip().str.upper()
        df["COMERCIAL"] = df["COMERCIAL"].astype(str).str.strip()
        df["CLIENTE"] = df["CLIENTE"].astype(str).str.strip()

        columnas_requeridas = ["FECHA_ENTRADA", "DIA"]
        for col in columnas_requeridas:
            if col not in df.columns:
                st.error(f"❌ Falta la columna obligatoria: {col}")
                st.stop()

        df["FECHA_ENTRADA"] = pd.to_datetime(df["FECHA_ENTRADA"], errors="coerce").dt.date
        df["DIA"] = pd.to_datetime(df["DIA"], errors="coerce").dt.date

        if df["FECHA_ENTRADA"].isna().any():
            st.warning("⚠️ Hay filas con FECHA_ENTRADA vacía.")
        if df["DIA"].isna().any():
            st.warning("⚠️ Hay filas con DIA vacía.")

except Exception as e:
    st.error(f"❌ Error al cargar clientes desde la API: {e}")
    df = pd.DataFrame(columns=columnas_base)
    for col in [
        "ASIGNADO_CLOSER", "FECHA_ASIGNACION_CLOSER", "FECHA_ENTRADA",
        "ASIGNADO_SUPERCLOSER", "FECHA_ASIGNACION_SUPERCLOSER",
        "ESTADO_CIERRE", "SEGUIMIENTO_CLOSER", "SEGUIMIENTO_SUPERCLOSER"
    ]:
        if col not in df.columns:
            df[col] = ""
    df["FECHA_ENTRADA"] = pd.to_datetime(df["FECHA_ENTRADA"], errors="coerce")


# --- LECTURA DE USUARIOS DESDE API PHP ---
try:
    response = requests.post(API_URL, data={"accion": "usuarios"})
    response.raise_for_status()
    datos_usuarios = response.json()

    df_usuarios = pd.DataFrame(datos_usuarios)

    usuarios_dict = {
        row["usuario"]: {
            "clave": str(row["contraseña"]),
            "rol": row["rol"].upper()
        }
        for _, row in df_usuarios.iterrows()
    }

except Exception as e:
    st.error(f"❌ No se pudo cargar la tabla de usuarios desde la API: {e}")
    st.stop()

# --- LOGIN LIBRE Y ROL DINÁMICO ---
if "usuario" not in st.session_state:
    st.session_state.usuario = ""
    st.session_state.rol = ""

if not st.session_state.usuario:
    st.subheader("🔐 Iniciar sesión")
    usuario = st.text_input("Usuario")
    clave = st.text_input("Contraseña", type="password")
    if st.button("Entrar"):
        if usuario in usuarios_dict and usuarios_dict[usuario]["clave"] == clave:
            st.session_state.usuario = usuario
            st.session_state.rol = usuarios_dict[usuario]["rol"].upper()
            st.rerun()
        else:
            st.error("❌ Usuario o contraseña incorrectos")
    st.stop()

usuario_actual = st.session_state.usuario.strip().upper()
rol_actual = st.session_state.rol

# --- BARRA DE USUARIO DISCRETA ARRIBA A LA DERECHA ---
with st.container():
    col1, col2 = st.columns([8, 1])
    with col1:
        st.markdown(f"👤 **{usuario_actual}** — {rol_actual.title()}")
    with col2:
        cambiar = st.button("🔁", help="Cambiar usuario")
        if cambiar:
            st.session_state.usuario = ""
            st.session_state.rol = ""
            st.rerun()



es_direccion = rol_actual == "DIRECCION"
es_coordinador = rol_actual == "COORDINADOR"
es_closer = rol_actual == "CLOSER"
es_super = rol_actual == "SUPER"

seccion_direccion = None  

if es_direccion:
    st.markdown("### 🔧 Secciones de Dirección")
    opciones = ["SEMAFORO", "CLOSERS", "SUPER CLOSERS", "GESTIÓN DE USUARIOS", "FUERA DE FLUJO"]
    seccion_direccion = st.radio("", opciones, horizontal=True)
    
    print(f"🔍 [DEBUG] Entrando en direccion")




if seccion_direccion == "SEMAFORO":
    st.subheader("📊 Semáforo General — Consulta por Dirección")

    try:
        response = requests.post(API_URL, data={"accion": "clientes"})
        response.raise_for_status()
        datos = response.json()
        df = pd.DataFrame(datos)

        df = estandarizar_fechas(df)
        df["DIAS_HABILES"] = df["FECHA_ENTRADA"].apply(dias_habiles)
        df = actualizar_semaforo(df)

        if "DIA" not in df.columns or df["DIA"].isna().all():
            st.info("📭 No hay clientes con fechas asignadas en el semáforo todavía.")
            st.stop()

        # Mostrar solo una fila por cliente, la más reciente
        df = df.sort_values("DIA", ascending=False).drop_duplicates("CLIENTE")

        # --- Filtros ---
        col1, col2 = st.columns(2)
        opciones_cal = sorted(df["CAL"].dropna().unique().tolist())
        filtro_cal = col1.selectbox("📞 Filtrar por CAL", options=["Todos"] + opciones_cal)
        opciones_semaforo = ["Todos"] + list(colores_semaforo.keys())
        filtro_semaforo = col2.selectbox("🚦 Filtrar por Semáforo", options=opciones_semaforo)

        df_filtrado = df.copy()
        if filtro_cal != "Todos":
            df_filtrado = df_filtrado[df_filtrado["CAL"] == filtro_cal]
        if filtro_semaforo != "Todos":
            df_filtrado = df_filtrado[df_filtrado["SEMAFORO"] == filtro_semaforo]

        st.write(f"🔍 Mostrando **{df_filtrado['CLIENTE'].nunique()}** clientes tras aplicar filtros")

        columnas_mostrar = {
            "CLIENTE": "Cliente",
            "CAL": "CAL",
            "COMERCIAL": "Comercial",
            "SEMAFORO": "Semáforo",
            "ASIGNADO_CLOSER": "Asignado a Closer",
            "ASIGNADO_SUPERCLOSER": "Asignado a Supercloser",
            "ESTADO_CIERRE": "Estado de cierre"
        }

        df_mostrar = df_filtrado[list(columnas_mostrar.keys())].rename(columns=columnas_mostrar)
        st.dataframe(df_mostrar, use_container_width=True)

        # --- Botón de resumen imprimible ---
        if "mostrar_resumen_direccion" not in st.session_state:
            st.session_state.mostrar_resumen_direccion = False

        if st.button("🖨️ Resumen imprimible de clientes"):
            st.session_state.mostrar_resumen_direccion = not st.session_state.mostrar_resumen_direccion
            st.rerun()

        if st.session_state.mostrar_resumen_direccion:
            df_resumen = df_filtrado.sort_values("DIA", ascending=False).drop_duplicates("CLIENTE")

            for _, row in df_resumen.iterrows():
                productos_coord = [p for p in productos if row.get(p) == "✔"]
                productos_closer = [p for p in productos if row.get(f"CLOSER_{p}") == "✔"]
                productos_super = [p for p in productos if row.get(f"SUPER_{p}") == "✔"]

                st.markdown("---")
                st.markdown(f"**👤 Cliente: {row['CLIENTE']}**")
                st.markdown(f"📞 **CAL:** {row['CAL']}")
                st.markdown(f"👨‍💼 **Comercial:** {row['COMERCIAL']}")
                st.markdown(f"🚦 **Semáforo:** {row['SEMAFORO']}")
                st.markdown(f"🔗 **Closer:** {row.get('ASIGNADO_CLOSER', '')}")
                st.markdown(f"⏫ **Supercloser:** {row.get('ASIGNADO_SUPERCLOSER', '')}")
                st.markdown(f"📌 **Estado cierre:** {row.get('ESTADO_CIERRE', '')}")
                st.markdown(f"🟢 **Coordi:** {', '.join(productos_coord) if productos_coord else 'Ninguno'}")
                st.markdown(f"🟠 **Closer:** {', '.join(productos_closer) if productos_closer else 'Ninguno'}")
                st.markdown(f"🔵 **Supercloser:** {', '.join(productos_super) if productos_super else 'Ninguno'}")
                st.info("🖨️ Usa Ctrl+P para imprimir o guardar como PDF desde tu navegador.")
                st.markdown("""<script>window.print()</script>""", unsafe_allow_html=True)

    except Exception as e:
        st.error(f"📭 No se pudo cargar el semáforo desde la API: {e}")



elif seccion_direccion == "CLOSERS":
    st.subheader("📌 Asignación de Closers")

    try:
        # 1. Obtener clientes desde la API
        response = requests.post(API_URL, data={"accion": "clientes"})
        response.raise_for_status()
        datos = response.json()
        df = pd.DataFrame(datos)

        df = estandarizar_fechas(df)
        df = actualizar_semaforo(df)

        for p in productos:
            if p not in df.columns:
                df[p] = ""

        if "DIA" not in df.columns or df["DIA"].isna().all():
            st.info("📭 No hay clientes con fechas asignadas en el semáforo todavía.")
            st.stop()


        df["DIAS_HABILES"] = df["FECHA_ENTRADA"].apply(dias_habiles)
        df = df.sort_values("DIA", ascending=False).drop_duplicates("CLIENTE")

        df_closer = df[
            (df["SEMAFORO"] == "ROJO") &
            (df["DIAS_HABILES"] >= 3) &
            (df["ASIGNADO_CLOSER"].astype(str).str.strip() == "") &
            (df["ESTADO_CIERRE"].fillna("").str.upper() != "CERRADO")
        ].sort_values("FECHA_ENTRADA")

        if df_closer.empty:
            st.info("✅ No hay clientes disponibles para asignar a Closers hoy.")
        else:
            for i, row in df_closer.iterrows():
                with st.expander(f"📁 Cliente: {row['CLIENTE']}"):
                    st.write(f"📞 **CAL:** {row['CAL']}")
                    st.write(f"👤 **Comercial:** {row['COMERCIAL']}")
                    st.write(f"🚦 **Semáforo:** {row['SEMAFORO']}")
                    st.write(f"📅 **Fecha de entrada:** {row['FECHA_ENTRADA']} — Días hábiles: {row['DIAS_HABILES']}")

                    st.markdown("### 🟢 Productos ofrecidos por Coordinación")
                    fila_coord = st.columns(len(productos))
                    for j, p in enumerate(productos):
                        valor = row.get(p, "")
                        fila_coord[j].markdown(f"**{p}**")
                        fila_coord[j].markdown(f"<div style='text-align:center'>{valor}</div>", unsafe_allow_html=True)

                    nuevo_closer = st.text_input(f"👤 Asignar Closer a {row['CLIENTE']}", key=f"closer_input_{i}")
                    if st.button("💾 Asignar Closer", key=f"asignar_closer_btn_{i}"):
                        try:
                            # 2. Enviar actualización a la API
                            payload = {
                                "accion": "asignar_closer",
                                "cliente": row["CLIENTE"],
                                "closer": nuevo_closer.strip().upper(),
                                "fecha": datetime.now().date().isoformat()
                            }
                            resp = requests.post(API_URL, data=payload)
                            resp.raise_for_status()

                            if resp.json().get("status") == "ok":
                                st.success(f"✅ Cliente {row['CLIENTE']} asignado correctamente a {nuevo_closer}")
                                st.rerun()
                            else:
                                st.error(f"❌ Error al asignar desde API: {resp.text}")
                        except Exception as e:
                            st.error(f"❌ Error al conectar con la API: {e}")

    except Exception as e:
        st.error(f"❌ No se pudo cargar la base de datos desde la API: {e}")



elif seccion_direccion == "SUPER CLOSERS":
    st.subheader("⏫ Escalado de clientes a Supercloser")

    try:
        # Leer clientes desde la API
        response = requests.post(API_URL, data={"accion": "clientes"})
        response.raise_for_status()
        datos_clientes = response.json()
        df = pd.DataFrame(datos_clientes)

        df = estandarizar_fechas(df)
        df["DIAS_HABILES"] = df["FECHA_ENTRADA"].apply(dias_habiles)
        df = actualizar_semaforo(df)

        for p in productos:
            if p not in df.columns:
                df[p] = ""

        # Leer usuarios desde API
        response_usuarios = requests.post(API_URL, data={"accion": "usuarios"})
        response_usuarios.raise_for_status()
        datos_usuarios = response_usuarios.json()
        df_usuarios = pd.DataFrame(datos_usuarios)

        superclosers_disponibles = df_usuarios[df_usuarios["rol"].str.upper() == "SUPER"]["usuario"].dropna().unique().tolist()

        df_super = df[
            (df["SEMAFORO"] == "ROJO") &
            (df["DIAS_HABILES"] >= 5) &
            (df["ASIGNADO_CLOSER"].fillna("").astype(str).str.strip() != "") &
            (df["ASIGNADO_SUPERCLOSER"].fillna("").astype(str).str.strip() == "") &
            (df["ESTADO_CIERRE"].fillna("").str.upper() != "CERRADO")
        ].sort_values("FECHA_ENTRADA")

        if df_super.empty:
            st.info("✅ No hay clientes disponibles para asignar a Superclosers hoy.")
        else:
            for i, row in df_super.iterrows():
                with st.expander(f"👤 Cliente: {row['CLIENTE']}"):
                    st.write(f"📞 CAL: {row['CAL']}")
                    st.write(f"🧑 Comercial: {row['COMERCIAL']}")
                    st.write(f"📅 Fecha entrada: {row['FECHA_ENTRADA']} — Días hábiles: {row['DIAS_HABILES']}")
                    st.write(f"🔗 Asignado a Closer: {row.get('ASIGNADO_CLOSER', '')}")

                    st.markdown("### 🟢 Productos ofrecidos por Coordinación")
                    fila_coord = st.columns(len(productos))
                    for j, p in enumerate(productos):
                        valor = row.get(p, "")
                        fila_coord[j].markdown(f"**{p}**")
                        fila_coord[j].markdown(f"<div style='text-align:center'>{valor}</div>", unsafe_allow_html=True)

                    supercloser = st.selectbox(
                        "👤 Seleccionar Supercloser",
                        options=superclosers_disponibles,
                        key=f"select_super_{i}"
                    )

                    if st.button("💾 Asignar Supercloser", key=f"btn_asignar_super_{i}"):
                        try:
                            payload = {
                                "accion": "asignar_supercloser",
                                "cliente": row["CLIENTE"],
                                "nombre": supercloser,
                                "fecha": str(datetime.now().date())
                            }
                            r = requests.post(API_URL, json=payload)
                            r.raise_for_status()
                            st.success(f"✅ Cliente {row['CLIENTE']} asignado a {supercloser}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error al guardar a través de la API: {e}")

    except Exception as e:
        st.error(f"❌ No se pudo cargar la información desde la API: {e}")


elif seccion_direccion == "FUERA DE FLUJO":
    st.subheader("📦 Clientes fuera del flujo (día 6+)")

    try:
        # Cargar clientes desde la API
        response = requests.post(API_URL, data={"accion": "clientes"})
        response.raise_for_status()
        datos_clientes = response.json()
        df = pd.DataFrame(datos_clientes)

        df = estandarizar_fechas(df)
        df = actualizar_semaforo(df)
        df["DIAS_HABILES"] = df["FECHA_ENTRADA"].apply(dias_habiles)

        if "DIA" not in df.columns or df["DIA"].isna().all():
            st.info("📭 No hay clientes con fechas asignadas en el semáforo todavía.")
            st.stop()

        df = df.sort_values("DIA", ascending=False).drop_duplicates("CLIENTE")

        # 🔢 Filtrar solo clientes del mes actual
        mes_actual = datetime.now().month
        año_actual = datetime.now().year
        df = df[
            (df["FECHA_ENTRADA"].dt.month == mes_actual) &
            (df["FECHA_ENTRADA"].dt.year == año_actual)
        ]

        df_fuera = df[
            (df["DIAS_HABILES"] >= 5) &
            (df["ESTADO_CIERRE"].fillna("").str.upper() != "CERRADO")
        ].sort_values("FECHA_ENTRADA")

        if df_fuera.empty:
            st.info("✅ No hay clientes fuera del flujo actualmente.")
        else:
            st.write(f"📋 Clientes detectados fuera del flujo operativo: {df_fuera['CLIENTE'].nunique()}")
            columnas_mostrar = [
                "CLIENTE", "CAL", "COMERCIAL", "FECHA_ENTRADA",
                "ASIGNADO_CLOSER", "ASIGNADO_SUPERCLOSER",
                "ESTADO_CIERRE", "SEMAFORO", "DIAS_HABILES"
            ]
            st.dataframe(df_fuera[columnas_mostrar], use_container_width=True)

            # Exportar a Excel
            if st.button("⬇️ Exportar a Excel"):
                nombre_archivo = f"Clientes_Fuera_Flujo_{datetime.now().date()}.xlsx"
                df_fuera[columnas_mostrar].to_excel(nombre_archivo, index=False)
                st.success(f"📅 Archivo exportado: {nombre_archivo}")

            # Mostrar versión imprimible en HTML
            from jinja2 import Template

            html_template = Template("""
            <html><head><meta charset='utf-8'></head><body>
            <h2>Clientes Fuera de Flujo ({{ fecha }})</h2>
            <table border="1" cellspacing="0" cellpadding="5">
            <tr>
            {% for col in columnas %}<th>{{ col }}</th>{% endfor %}
            </tr>
            {% for fila in filas %}
            <tr>
            {% for col in columnas %}<td>{{ fila[col] }}</td>{% endfor %}
            </tr>
            {% endfor %}
            </table></body></html>
            """)

            html_content = html_template.render(
                columnas=columnas_mostrar,
                filas=df_fuera[columnas_mostrar].to_dict(orient="records"),
                fecha=datetime.now().strftime("%d/%m/%Y")
            )

            if st.button("🌐 Imprimir Resumen"):
                st.markdown(html_content, unsafe_allow_html=True)
                st.info("✅ Usa Ctrl+P para imprimir o guardar como PDF desde tu navegador.")

    except Exception as e:
        st.error(f"❌ Error al cargar los datos desde la API: {e}")


elif seccion_direccion == "GESTIÓN DE USUARIOS":
    st.subheader("👥 Gestión de Usuarios")

    try:
        # Obtener usuarios desde la API
        response = requests.post(API_URL, data={"accion": "usuarios"})
        response.raise_for_status()
        datos_usuarios = response.json()
        df_usuarios = pd.DataFrame(datos_usuarios)

        st.markdown("### 📝 Editar usuarios existentes")
        df_usuarios_editado = st.data_editor(
            df_usuarios,
            use_container_width=True,
            key="usuarios_editor",
            num_rows="dynamic"
        )

        if st.button("💾 Guardar todos los cambios"):
            try:
                response = requests.post(API_URL, json={
                    "accion": "guardar_usuarios",
                    "usuarios": df_usuarios_editado.to_dict(orient="records")
                })
                response.raise_for_status()
                st.success("✅ Cambios guardados correctamente.")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error al guardar usuarios: {e}")

        st.markdown("### ➕ Añadir nuevo usuario")
        with st.form("form_nuevo_usuario"):
            col1, col2, col3 = st.columns(3)
            nuevo_usuario = col1.text_input("Usuario")
            nueva_contra = col2.text_input("Contraseña")
            nuevo_rol = col3.selectbox("Rol", ["COORDINADOR", "DIRECCION", "CLOSER", "SUPER"])

            if st.form_submit_button("➕ Añadir"):
                if nuevo_usuario and nueva_contra:
                    try:
                        response = requests.post(API_URL, json={
                            "accion": "nuevo_usuario",
                            "usuario": nuevo_usuario.strip(),
                            "contraseña": nueva_contra.strip(),
                            "rol": nuevo_rol.strip().upper()
                        })
                        response.raise_for_status()
                        st.success(f"✅ Usuario {nuevo_usuario} añadido correctamente.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error al insertar usuario: {e}")
                else:
                    st.warning("⚠️ Usuario y contraseña no pueden estar vacíos.")

        st.markdown("### 🗑️ Borrar usuario")
        usuario_a_borrar = st.selectbox("Selecciona un usuario para borrar", df_usuarios["usuario"].tolist())
        if st.button("🗑️ Eliminar usuario seleccionado"):
            try:
                response = requests.post(API_URL, json={
                    "accion": "borrar_usuario",
                    "usuario": usuario_a_borrar
                })
                response.raise_for_status()
                st.success(f"✅ Usuario {usuario_a_borrar} eliminado correctamente.")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error al eliminar usuario: {e}")

    except Exception as e:
        st.error(f"❌ No se pudo cargar la tabla de usuarios: {e}")

    try:
        response = requests.post(API_URL, data={"accion": "clientes"})
        response.raise_for_status()
        datos = response.json()
        df = pd.DataFrame(datos)

        # Solo continuamos si hay columnas mínimas
        if df.empty:
            df = pd.DataFrame(columns=["CAL", "COMERCIAL", "CLIENTE", "FECHA_ENTRADA", "DIA"])  # estructura mínima

        df = estandarizar_fechas(df)

        if "DIAS_HABILES" not in df.columns and "FECHA_ENTRADA" in df.columns:
            df["DIAS_HABILES"] = df["FECHA_ENTRADA"].apply(dias_habiles)
        
        df = actualizar_semaforo(df)

    except Exception as e:
        st.error(f"❌ Error al cargar los datos de clientes: {e}")
        # Crear un DataFrame vacío con columnas mínimas para que la app siga funcionando
        df = pd.DataFrame(columns=["CAL", "COMERCIAL", "CLIENTE", "FECHA_ENTRADA", "DIA", "SEMAFORO"])

    # --- Inicializar filtros si no existen ---
    if "filtros" not in st.session_state:
        st.session_state.filtros = {
            "CAL": st.session_state.usuario,
            "COMERCIAL": "",
            "CLIENTE": "",
            "SEMAFORO": ""
        }


    # --- Expander de filtros ---
    with st.expander("🔍 Filtros de búsqueda", expanded=False):
        with st.form("form_filtros_aplicar"):
            c1, c2, c3, c4 = st.columns(4)
            CAL = c1.text_input("CAL", value=st.session_state.filtros.get("CAL", st.session_state.usuario))
            comercial = c2.text_input("COMERCIAL", value=st.session_state.filtros.get("COMERCIAL", ""))
            cliente = c3.text_input("CLIENTE", value=st.session_state.filtros.get("CLIENTE", ""))
            semaforo = c4.selectbox("SEMAFORO", options=[""] + list(colores_semaforo.keys()), index=0)

            if st.form_submit_button("✅ Aplicar filtros"):
                st.session_state.filtros = {
                    "CAL": CAL,
                    "COMERCIAL": comercial,
                    "CLIENTE": cliente,
                    "SEMAFORO": semaforo
                }
                st.rerun()

        with st.form("form_filtros_borrar"):
            if st.form_submit_button("🩹 Mostrar todos"):
                st.session_state.filtros = {
                    "CAL": "",
                    "COMERCIAL": "",
                    "CLIENTE": "",
                    "SEMAFORO": ""
                }
                st.rerun()

    # --- Aplicar filtros al dataframe ---
    f = st.session_state.filtros
    df_filtrado = df.copy()

    if f["CAL"]:
        df_filtrado = df_filtrado[df_filtrado["CAL"].str.contains(f["CAL"], case=False, na=False)]
    if f["COMERCIAL"]:
        df_filtrado = df_filtrado[df_filtrado["COMERCIAL"].str.contains(f["COMERCIAL"], case=False, na=False)]
    if f["CLIENTE"]:
        df_filtrado = df_filtrado[df_filtrado["CLIENTE"].str.contains(f["CLIENTE"], case=False, na=False)]
    if f["SEMAFORO"]:
        df_filtrado = df_filtrado[df_filtrado["SEMAFORO"] == f["SEMAFORO"]]

    # --- Insertar cliente ---
    with st.form("insertar_cliente", clear_on_submit=True):
        col1, col2 = st.columns(2)
        comercial = col1.text_input("Nombre del COMERCIAL", key="comercial_input")
        cliente = col2.text_input("Nombre del CLIENTE", key="cliente_input")

        if st.form_submit_button("➕ Añadir Cliente"):
            cliente_normalizado = cliente.strip().upper()
            if cliente_normalizado in df["CLIENTE"].str.strip().str.upper().tolist():
                st.warning("⚠️ Ese cliente ya existe en el semáforo.")
            else:
                nuevo = insertar_cliente(st.session_state.usuario, comercial, cliente)
                df = pd.concat([df, nuevo], ignore_index=True)
                df = actualizar_semaforo(df)

                # ✅ Enviar cada fila por POST a la API PHP
                errores_api = []
                for _, fila in nuevo.iterrows():
                    datos = {
                        "accion": "insertar_cliente",
                        "CAL": fila["CAL"],
                        "COMERCIAL": fila["COMERCIAL"],
                        "CLIENTE": fila["CLIENTE"],
                        "DIA": fila["DIA"].strftime("%Y-%m-%d"),
                        "FECHA_ENTRADA": fila["FECHA_ENTRADA"].strftime("%Y-%m-%d")
                    }
                    try:
                        r = requests.post(API_URL, json=datos)
                        r.raise_for_status()
                    except Exception as e:
                        errores_api.append(str(e))

                if errores_api:
                    st.error(f"❌ Fallo al guardar en la API: {errores_api}")
                else:
                    st.success("✅ Cliente añadido correctamente.")

                st.session_state.filtros = {
                    "CAL": "",
                    "COMERCIAL": "",
                    "CLIENTE": "",
                    "SEMAFORO": ""
                }
                st.rerun()

    # --- Visualización del semáforo ---
    if "CLIENTE" in df_filtrado.columns:
        hoy = datetime.now().date()
        clientes_advertidos = set()
        df_visible = df_filtrado.copy()

        df_visible = df_visible[
            (df_visible["DIAS_HABILES"] < 3) &
            (df_visible["ASIGNADO_CLOSER"].fillna("").astype(str).str.strip() == "") &
            (df_visible["ASIGNADO_SUPERCLOSER"].fillna("").astype(str).str.strip() == "")
        ]

        if df_visible.empty:
            st.info("📭 No hay clientes asignados a este usuario en este momento.")
        else:
            cols = st.columns([1.2, 1.2, 1.5, 1.1] + [0.7]*len(productos) + [1.5])
            cols[0].markdown("**CAL**")
            cols[1].markdown("**COMERCIAL**")
            cols[2].markdown("**CLIENTE**")
            cols[3].markdown("**DÍA**")
            for j, p in enumerate(productos):
                cols[4 + j].markdown(f"**{p}**")
            cols[-1].markdown("**SEMAFORO**")

            for cliente in df_visible["CLIENTE"].unique():
                bloque = df_visible[df_visible["CLIENTE"] == cliente]
                st.markdown("<div class='bloque-cliente-wrap'><div class='bloque-cliente-inner'>", unsafe_allow_html=True)
                advertir = False

                for i, fila in bloque.iterrows():
                    cols = st.columns([1.2, 1.2, 1.5, 1.1] + [0.7]*len(productos) + [1.5])
                    cols[0].markdown(fila["CAL"])
                    cols[1].markdown(fila["COMERCIAL"])
                    cols[2].markdown(fila["CLIENTE"])
                    cols[3].markdown(fila["DIA"].strftime("%d/%m"))

                    for j, p in enumerate(productos):
                        if fila["DIA"] == hoy:
                            if cols[4 + j].button(fila[p], key=f"{i}_{p}"):
                                df.at[i, p] = "✔" if fila[p] == "❌" else "❌"
                                df = actualizar_semaforo(df)
                                try:
                                    datos = {
                                        "accion": "actualizar_producto",
                                        "producto": p,
                                        "valor": df.at[i, p],
                                        "semaforo": df.at[i, "SEMAFORO"],
                                        "cliente": fila["CLIENTE"],
                                        "dia": fila["DIA"].strftime("%Y-%m-%d")
                                    }
                                    r = requests.post(API_URL, json=datos)
                                    r.raise_for_status()
                                except Exception as e:
                                    st.error(f"❌ Error al actualizar en la API: {e}")
                                st.rerun()
                        else:
                            if cols[4 + j].button(fila[p], key=f"{i}_{p}"):
                                advertir = True

                    sem = fila["SEMAFORO"]
                    if sem in colores_semaforo:
                        bg, fg = colores_semaforo[sem]
                        cols[-1].markdown(
                            f"<div style='background-color:{bg}; color:{fg}; padding:5px; text-align:center; border-radius:4px;'>"
                            f"<b>{sem}</b></div>",
                            unsafe_allow_html=True
                        )

                if advertir and cliente not in clientes_advertidos:
                    st.warning(f"⚠️ Solo puedes editar los datos del día actual para **{cliente}**.")
                    clientes_advertidos.add(cliente)

                st.markdown("</div></div>", unsafe_allow_html=True)

    else:
        st.info("📭 No hay datos de clientes disponibles.")

if es_coordinador:
    st.subheader(f"👩‍💼 Coordinación — {st.session_state.usuario}")

    try:
        response = requests.post(API_URL, data={"accion": "clientes"})
        response.raise_for_status()
        datos = response.json()
        df = pd.DataFrame(datos)

        # 🔒 Normalizar nombres de columnas y asegurar columnas mínimas
        df.columns = [col.upper().strip() for col in df.columns]
        for col in columnas_base:
            if col not in df.columns:
                df[col] = ""

        df = estandarizar_fechas(df)

        if "FECHA_ENTRADA" in df.columns:
            df["DIAS_HABILES"] = df["FECHA_ENTRADA"].apply(dias_habiles)

        df = actualizar_semaforo(df)

    except Exception as e:
        st.error(f"❌ Error al cargar los datos de clientes: {e}")
        df = pd.DataFrame(columns=["CAL", "COMERCIAL", "CLIENTE", "FECHA_ENTRADA", "DIA", "SEMAFORO"])

    if "filtros" not in st.session_state:
        st.session_state.filtros = {
            "CAL": st.session_state.usuario,
            "COMERCIAL": "",
            "CLIENTE": "",
            "SEMAFORO": ""
        }

    with st.expander("🔍 Filtros de búsqueda", expanded=False):
        with st.form("form_filtros_aplicar"):
            c1, c2, c3, c4 = st.columns(4)
            CAL = c1.text_input("CAL", value=st.session_state.filtros.get("CAL", st.session_state.usuario))
            comercial = c2.text_input("COMERCIAL", value=st.session_state.filtros.get("COMERCIAL", ""))
            cliente = c3.text_input("CLIENTE", value=st.session_state.filtros.get("CLIENTE", ""))
            semaforo = c4.selectbox("SEMAFORO", options=[""] + list(colores_semaforo.keys()), index=0)

            if st.form_submit_button("✅ Aplicar filtros"):
                st.session_state.filtros = {
                    "CAL": CAL,
                    "COMERCIAL": comercial,
                    "CLIENTE": cliente,
                    "SEMAFORO": semaforo
                }
                st.rerun()

        with st.form("form_filtros_borrar"):
            if st.form_submit_button("🩹 Mostrar todos"):
                st.session_state.filtros = {
                    "CAL": "",
                    "COMERCIAL": "",
                    "CLIENTE": "",
                    "SEMAFORO": ""
                }
                st.rerun()

    f = st.session_state.filtros
    df_filtrado = df.copy()

    if f["CAL"]:
        df_filtrado = df_filtrado[df_filtrado["CAL"].str.contains(f["CAL"], case=False, na=False)]
    if f["COMERCIAL"]:
        df_filtrado = df_filtrado[df_filtrado["COMERCIAL"].str.contains(f["COMERCIAL"], case=False, na=False)]
    if f["CLIENTE"]:
        df_filtrado = df_filtrado[df_filtrado["CLIENTE"].str.contains(f["CLIENTE"], case=False, na=False)]
    if f["SEMAFORO"]:
        df_filtrado = df_filtrado[df_filtrado["SEMAFORO"] == f["SEMAFORO"]]

    with st.form("insertar_cliente", clear_on_submit=True):
        col1, col2 = st.columns(2)
        comercial = col1.text_input("Nombre del COMERCIAL", key="comercial_input")
        cliente = col2.text_input("Nombre del CLIENTE", key="cliente_input")

        if st.form_submit_button("➕ Añadir Cliente"):
            cliente_normalizado = cliente.strip().upper()
            if cliente_normalizado in df["CLIENTE"].str.strip().str.upper().tolist():
                st.warning("⚠️ Ese cliente ya existe en el semáforo.")
            else:
                nuevo = insertar_cliente(st.session_state.usuario, comercial, cliente)
                df = pd.concat([df, nuevo], ignore_index=True)
                df = actualizar_semaforo(df)

                errores_api = []
                for _, fila in nuevo.iterrows():
                    datos = {
                        "accion": "insertar_cliente",
                        "CAL": fila["CAL"],
                        "COMERCIAL": fila["COMERCIAL"],
                        "CLIENTE": fila["CLIENTE"],
                        "DIA": fila["DIA"].strftime("%Y-%m-%d"),
                        "FECHA_ENTRADA": fila["FECHA_ENTRADA"].strftime("%Y-%m-%d")
                    }
                    try:
                        r = requests.post(API_URL, json=datos)
                        r.raise_for_status()
                    except Exception as e:
                        errores_api.append(str(e))

                if errores_api:
                    st.error(f"❌ Fallo al guardar en la API: {errores_api}")
                else:
                    st.success("✅ Cliente añadido correctamente.")

                st.session_state.filtros = {
                    "CAL": "",
                    "COMERCIAL": "",
                    "CLIENTE": "",
                    "SEMAFORO": ""
                }
                st.rerun()

    if "CLIENTE" in df_filtrado.columns and not df_filtrado.empty:
        hoy = datetime.now().date()
        clientes_advertidos = set()
        df_visible = df_filtrado.copy()

        df_visible = df_visible[
            (df_visible["DIAS_HABILES"] < 3) &
            (df_visible["ASIGNADO_CLOSER"].fillna("").astype(str).str.strip() == "") &
            (df_visible["ASIGNADO_SUPERCLOSER"].fillna("").astype(str).str.strip() == "")
        ]

        if df_visible.empty:
            st.info("📭 No hay clientes asignados a este usuario en este momento.")
        else:
            cols = st.columns([1.2, 1.2, 1.5, 1.1] + [0.7]*len(productos) + [1.5])
            cols[0].markdown("**CAL**")
            cols[1].markdown("**COMERCIAL**")
            cols[2].markdown("**CLIENTE**")
            cols[3].markdown("**DÍA**")
            for j, p in enumerate(productos):
                cols[4 + j].markdown(f"**{p}**")
            cols[-1].markdown("**SEMAFORO**")

            for cliente in df_visible["CLIENTE"].unique():
                bloque = df_visible[df_visible["CLIENTE"] == cliente]
                st.markdown("<div class='bloque-cliente-wrap'><div class='bloque-cliente-inner'>", unsafe_allow_html=True)
                advertir = False

                for i, fila in bloque.iterrows():
                    cols = st.columns([1.2, 1.2, 1.5, 1.1] + [0.7]*len(productos) + [1.5])
                    cols[0].markdown(fila["CAL"])
                    cols[1].markdown(fila["COMERCIAL"])
                    cols[2].markdown(fila["CLIENTE"])
                    cols[3].markdown(fila["DIA"].strftime("%d/%m"))

                    for j, p in enumerate(productos):
                        label = str(fila.get(p, "❌"))
                        if fila["DIA"] == hoy:
                            if cols[4 + j].button(label, key=f"{i}_{p}"):
                                df.at[i, p] = "✔" if fila[p] == "❌" else "❌"
                                df = actualizar_semaforo(df)
                                try:
                                    datos = {
                                        "accion": "actualizar_producto",
                                        "producto": p,
                                        "valor": df.at[i, p],
                                        "semaforo": df.at[i, "SEMAFORO"],
                                        "cliente": fila["CLIENTE"],
                                        "dia": fila["DIA"].strftime("%Y-%m-%d")
                                    }
                                    r = requests.post(API_URL, json=datos)
                                    r.raise_for_status()
                                except Exception as e:
                                    st.error(f"❌ Error al actualizar en la API: {e}")
                                st.rerun()
                        else:
                            if cols[4 + j].button(fila[p], key=f"{i}_{p}"):
                                advertir = True

                    sem = fila["SEMAFORO"]
                    if sem in colores_semaforo:
                        bg, fg = colores_semaforo[sem]
                        cols[-1].markdown(
                            f"<div style='background-color:{bg}; color:{fg}; padding:5px; text-align:center; border-radius:4px;'>"
                            f"<b>{sem}</b></div>",
                            unsafe_allow_html=True
                        )

                if advertir and cliente not in clientes_advertidos:
                    st.warning(f"⚠️ Solo puedes editar los datos del día actual para **{cliente}**.")
                    clientes_advertidos.add(cliente)

                st.markdown("</div></div>", unsafe_allow_html=True)
    else:
        st.info("📭 No hay datos de clientes disponibles.")




elif es_closer:
    st.subheader("📋 Seguimiento de Clientes Asignados (Closer)")
    try:
        respuesta = requests.post(API_URL, data={"accion": "clientes"})
        respuesta.raise_for_status()
        datos = respuesta.json()
        df = pd.DataFrame(datos)

        df = estandarizar_fechas(df)
        df["DIAS_HABILES"] = df["FECHA_ENTRADA"].apply(dias_habiles)

        productos_closer = [f"CLOSER_{p}" for p in productos]
        for p in productos_closer:
            if p not in df.columns:
                df[p] = ""

        if "GESTIONADO_CLOSER" not in df.columns:
            df["GESTIONADO_CLOSER"] = False


        df_closer = df[
            (df["ASIGNADO_CLOSER"].astype(str).str.upper() == usuario_actual) &
            (df["GESTIONADO_CLOSER"] != True)
        ].sort_values("FECHA_ENTRADA")

        if df_closer.empty:
            st.info("🔕 No tienes clientes asignados actualmente.")
        else:
            for i, row in df_closer.iterrows():
                # Copiar ✔ de Coordinación si CLOSER_* vacío
                for p in productos:
                    col_closer = f"CLOSER_{p}"
                    if row.get(p) == "✔" and row.get(col_closer, "") not in ["✔", "❌"]:
                        row[col_closer] = "✔"

                with st.expander(f"👤 Cliente: {row['CLIENTE']} — Semáforo: {row['SEMAFORO']}"):
                    st.write(f"📞 CAL: {row['CAL']}")
                    st.write(f"🧑 Comercial: {row['COMERCIAL']}")
                    st.write(f"📅 Fecha asignación: {row.get('FECHA_ASIGNACION_CLOSER', 'Sin fecha')}")

                    st.markdown("### 🟢 Productos ofrecidos por Coordinación")
                    fila_coord = st.columns(len(productos))
                    for j, p in enumerate(productos):
                        fila_coord[j].markdown(f"**{p}**")
                    fila_valores = st.columns(len(productos))
                    for j, p in enumerate(productos):
                        valor = row.get(p, "")
                        fila_valores[j].markdown(f"<div style='text-align:center'>{valor}</div>", unsafe_allow_html=True)

                    st.markdown("### 📝 Productos ofrecidos por Closer")
                    valores_closer_actualizados = {}
                    fila_closer = st.columns(len(productos))
                    for j, p in enumerate(productos):
                        col_name = f"CLOSER_{p}"
                        valor_actual = row.get(col_name, "❌")
                        nuevo_valor = fila_closer[j].selectbox(
                            f"{p}",
                            ["❌", "✔"],
                            index=0 if valor_actual != "✔" else 1,
                            key=f"{col_name}_{i}"
                        )
                        valores_closer_actualizados[col_name] = nuevo_valor

                    seguimiento = st.text_area(
                        f"📝 Seguimiento para {row['CLIENTE']}",
                        value=row.get("SEGUIMIENTO_CLOSER", ""),
                        key=f"seguimiento_closer_{i}"
                    )

                    estado = st.radio(
                        "📌 Estado del cliente",
                        options=["ESCALAR A SUPER"],
                        index=0,
                        key=f"estado_closer_{i}"
                    )

                    if st.button("💾 Guardar cambios", key=f"guardar_closer_{i}"):
                        try:
                            payload = {
                                "accion": "seguimiento_closer",
                                "cliente": row["CLIENTE"],
                                "seguimiento": seguimiento,
                                "estado": estado,
                                "gestionado": True,
                                "productos": valores_closer_actualizados
                            }
                            response = requests.post(API_URL, json=payload)
                            response.raise_for_status()

                            st.success(f"✅ Seguimiento de {row['CLIENTE']} actualizado.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error al guardar mediante API: {e}")

    except Exception as e:
        st.error(f"❌ Error al cargar datos desde MySQL: {e}")


elif es_super:
    st.subheader("📋 Seguimiento de Clientes Escalados (Supercloser)")

    try:
        response = requests.post(API_URL, data={"accion": "clientes"})
        response.raise_for_status()
        data = response.json()
        df = pd.DataFrame(data)

        df = estandarizar_fechas(df)
        df["DIAS_HABILES"] = df["FECHA_ENTRADA"].apply(dias_habiles)

        productos_super = [f"SUPERCLOSER_{p}" for p in productos]
        for p in productos_super:
            if p not in df.columns:
                df[p] = ""

        if "GESTIONADO_SUPER" not in df.columns:
            df["GESTIONADO_SUPER"] = False


        df_super = df[
            (df["ASIGNADO_SUPERCLOSER"].astype(str).str.upper() == usuario_actual) &
            (df["DIAS_HABILES"] >= 5) &
            (df["GESTIONADO_SUPER"] != True)
        ].sort_values("FECHA_ENTRADA")

        if df_super.empty:
            st.info("🔕 No tienes clientes escalados actualmente.")
        else:
            for i, row in df_super.iterrows():
                for p in productos:
                    col_super = f"SUPERCLOSER_{p}"
                    if row.get(col_super, "") not in ["✔", "❌"]:
                        if row.get(p) == "✔" or row.get(f"CLOSER_{p}", "") == "✔":
                            row[col_super] = "✔"

                with st.expander(f"👤 Cliente: {row['CLIENTE']} — Semáforo: {row['SEMAFORO']}"):
                    st.write(f"📞 CAL: {row['CAL']}")
                    st.write(f"🧑 Comercial: {row['COMERCIAL']}")
                    st.write(f"📅 Fecha asignación: {row.get('FECHA_ASIGNACION_SUPERCLOSER', 'Sin fecha')}")

                    st.markdown("### 🟢 Productos vendidos por Coordinación")
                    fila_coord = st.columns(len(productos))
                    for j, p in enumerate(productos):
                        fila_coord[j].markdown(f"**{p}**")
                    fila_valores_coord = st.columns(len(productos))
                    for j, p in enumerate(productos):
                        fila_valores_coord[j].markdown(f"<div style='text-align:center'>{row.get(p, '')}</div>", unsafe_allow_html=True)

                    st.markdown("### 🔄 Productos vendidos por Closer")
                    fila_closer = st.columns(len(productos))
                    for j, p in enumerate(productos):
                        fila_closer[j].markdown(f"<div style='text-align:center'>{row.get(f'CLOSER_{p}', '')}</div>", unsafe_allow_html=True)

                    st.markdown("### ✍️ Productos ofrecidos por Supercloser")
                    valores_super_actualizados = {}
                    fila_super = st.columns(len(productos))
                    for j, p in enumerate(productos):
                        col_name = f"SUPERCLOSER_{p}"
                        valor_actual = row.get(col_name, "❌")
                        nuevo_valor = fila_super[j].selectbox(
                            f"{p}",
                            ["❌", "✔"],
                            index=0 if valor_actual != "✔" else 1,
                            key=f"{col_name}_{i}"
                        )
                        valores_super_actualizados[col_name] = nuevo_valor

                    seguimiento = st.text_area(
                        f"📝 Seguimiento Supercloser para {row['CLIENTE']}",
                        value=row.get("SEGUIMIENTO_SUPERCLOSER", ""),
                        key=f"seguimiento_super_{i}"
                    )

                    estado_actual = str(row.get("ESTADO_CIERRE", "")).upper()
                    opciones_estado = ["FINALIZADO", "ESCALAR A CENTRAL"]
                    if estado_actual not in opciones_estado:
                        estado_actual = "FINALIZADO"

                    estado = st.radio(
                        "📌 Estado del cliente",
                        options=opciones_estado,
                        index=opciones_estado.index(estado_actual),
                        key=f"estado_super_{i}"
                    )

                    if st.button("💾 Guardar cambios", key=f"guardar_super_{i}"):
                        try:
                            payload = {
                                "accion": "seguimiento_super",
                                "cliente": row["CLIENTE"],
                                "datos": {
                                    **valores_super_actualizados,
                                    "SEGUIMIENTO_SUPERCLOSER": seguimiento,
                                    "ESTADO_CIERRE": estado,
                                    "GESTIONADO_SUPER": True
                                }
                            }

                            response = requests.post(API_URL, json=payload)
                            response.raise_for_status()
                            st.success(f"✅ Seguimiento de {row['CLIENTE']} actualizado.")
                            st.rerun()

                        except Exception as e:
                            st.error(f"❌ Error al guardar vía API: {e}")

    except Exception as e:
        st.error(f"📭 No se pudo cargar la información de clientes desde la base de datos: {e}")
