import asyncio
from datetime import datetime
import html
import json
import os
from threading import Thread
import time
from flask import Flask
import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
API_KEY = os.environ.get("APIFOOTBALL_KEY") or os.environ.get("FOOTBALL_API_KEY")
ARCHIVO_ESTADO = "datos_bot.json"

HEADERS = {"X-Auth-Token": API_KEY} if API_KEY else {}
SESSION = requests.Session()

REGLAS_MERCADOS = {
    "home": {
        "min_inicio": 20,
        "min_fin": 75,
        "cuota_min": 1.90,
        "cuota_max": 2.10,
    },
    "over15": {
        "min_inicio": 20,
        "min_fin": 58,
        "max_goles_totales": 1,
        "cuota_default": 1.75,
    },
    "over25": {
        "min_inicio": 30,
        "min_fin": 72,
        "goles_totales_exactos": 2,
        "cuota_default": 2.05,
    },
    "btts": {
        "min_inicio": 25,
        "min_fin": 68,
        "cuota_default": 1.90,
    },
}

estado = {
    "chat_id": None,
    "historial_apuestas": [],
    "fecha_alertas": datetime.now().strftime("%Y-%m-%d"),
    "alertas_enviadas": [],
}
partidos_globales_activos = []

app = Flask(__name__)


def log_diag(msg: str):
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ahora}] [Tobipybot] {msg}", flush=True)


def verificar_rotacion_diaria_alertas():
    hoy_str = datetime.now().strftime("%Y-%m-%d")
    if estado.get("fecha_alertas") != hoy_str:
        estado["fecha_alertas"] = hoy_str
        estado["alertas_enviadas"] = []


def cargar_estado():
    global estado
    if os.path.exists(ARCHIVO_ESTADO):
        try:
            with open(ARCHIVO_ESTADO, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    estado.update(data)
        except Exception as e:
            log_diag(f"Error al cargar estado: {e}")
    verificar_rotacion_diaria_alertas()


def guardar_estado():
    verificar_rotacion_diaria_alertas()
    tmp_path = f"{ARCHIVO_ESTADO}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(estado, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, ARCHIVO_ESTADO)
    except Exception as e:
        log_diag(f"Error al guardar estado: {e}")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


@app.route("/")
def home():
    return "Tobipybot Pro con Football-Data operativo 24/7 🚀"


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, use_reloader=False)


def tg_post(method: str, payload: dict, timeout: int = 10):
    if not TELEGRAM_TOKEN:
        return None
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"
    try:
        return SESSION.post(url, json=payload, timeout=timeout)
    except Exception as e:
        log_diag(f"Error en Telegram ({method}): {e}")
        return None


def enviar_alerta_telegram_con_share(mensaje_html, partido_info, clave_alerta=None, cuota=1.95, stake=1.0):
    chat_id = estado.get("chat_id")
    if not chat_id or not TELEGRAM_TOKEN:
        log_diag("Alerta omitida: falta chat_id o TELEGRAM_TOKEN.")
        return

    verificar_rotacion_diaria_alertas()
    if clave_alerta and clave_alerta in estado["alertas_enviadas"]:
        return

    apuesta_id = len(estado["historial_apuestas"]) + 1
    registro = {
        "id": apuesta_id,
        "partido": partido_info,
        "cuota": cuota,
        "stake": stake,
        "estado": "PENDIENTE",
    }
    estado["historial_apuestas"].append(registro)
    if clave_alerta:
        estado["alertas_enviadas"].append(clave_alerta)
    guardar_estado()

    teclado = {
        "inline_keyboard": [
            [
                {"text": "✅ Ganada", "callback_data": f"win_{apuesta_id}"},
                {"text": "❌ Perdida", "callback_data": f"loss_{apuesta_id}"},
                {"text": "➖ Nula", "callback_data": f"void_{apuesta_id}"},
            ],
            [
                {"text": "📤 Copiar / Comunidad", "callback_data": f"share_{apuesta_id}"},
            ],
        ]
    }

    texto_final = f"{mensaje_html}\n\n🆔 <b>Pick #{apuesta_id}</b> | 🤖 <i>Tobipybot Pro</i>"
    resp = tg_post("sendMessage", {
        "chat_id": chat_id,
        "text": texto_final,
        "parse_mode": "HTML",
        "reply_markup": teclado,
    })
    if resp and resp.ok:
        log_diag(f"Alerta enviada -> Pick #{apuesta_id}: {partido_info}")

def escanear_mercados_avanzados():
    global partidos_globales_activos
    if not API_KEY:
        log_diag("Sin API Key configurada para football-data.org.")
        return

    url = "https://api.football-data.org/v4/matches"

    for intento in range(1, 4):
        try:
            response = SESSION.get(url, headers=HEADERS, timeout=15)
            status_code = response.status_code

            if status_code == 429:
                log_diag("football-data.org devolvió HTTP 429 (límite de peticiones alcanzado).")
                time.sleep(5)
                return

            if not response.ok:
                log_diag(f"football-data.org HTTP {status_code} en intento {intento}.")
                time.sleep(2)
                continue

            payload_json = response.json()
            matches = payload_json.get("matches", [])
            lista_temp = []
            en_vivo = 0
            
            hoy_str = datetime.now().strftime("%Y-%m-%d")

            for m in matches:
                utc_date = m.get("utcDate", "")
                if not utc_date.startswith(hoy_str):
                    continue

                match_id = m.get("id")
                competition = m.get("competition", {}).get("name", "Liga Internacional")
                home_team = m.get("homeTeam", {}).get("name", "Local")
                away_team = m.get("awayTeam", {}).get("name", "Visitante")
                
                status_short = m.get("status", "")
                if status_short in ["IN_PLAY", "PAUSED", "LIVE", "1H", "2H"]:
                    en_vivo += 1

                score_info = m.get("score", {}).get("fullTime", {})
                home_goals = score_info.get("home") if score_info.get("home") is not None else 0
                
                # CORREGIDO: Apunta directo a score_info
                away_goals = score_info.get("away") if score_info.get("away") is not None else 0
                
                # Intentar capturar el minuto si la API lo provee, o dejarlo en 0 de forma segura
                elapsed = m.get("minute") if m.get("minute") is not None else 0
                
                lista_temp.append({
                    "fixture_id": match_id,
                    "competition": competition,
                    "home_team": home_team,
                    "away_team": away_team,
                    "minute": elapsed,
                    "status": status_short,
                    "home_goals": home_goals,
                    "away_goals": away_goals,
                    "score": f"{home_goals}-{away_goals}",
                    "odds_home": None,
                    "odds_corners": None,
                    "odds_over15": None,
                    "odds_over25": None,
                    "odds_btts": None,
                })

            partidos_globales_activos = lista_temp
            log_diag(
                f"Total partidos recuperados (hoy): {len(lista_temp)} | En juego: {en_vivo}"
            )
            return
        except Exception as e:
            log_diag(f"Excepción al consultar football-data.org (intento {intento}): {e}")
            time.sleep(2)
            


def enviar_menu_principal(chat_id):
    if not chat_id or not TELEGRAM_TOKEN:
        return
    teclado = {
        "inline_keyboard": [
            [
                {"text": "📋 Partidos de Hoy", "callback_data": "ver_partidos"},
                {"text": "📜 Historial & Yield", "callback_data": "ver_historial"},
            ],
            [
                {"text": "🔄 Actualizar Datos", "callback_data": "actualizar"},
            ],
        ]
    }
    tg_post("sendMessage", {
        "chat_id": chat_id,
        "text": "👋 ¡Panel Pro Football-Data de <b>Tobipybot</b> activo!\n\nSelecciona una opción:",
        "parse_mode": "HTML",
        "reply_markup": teclado,
    })


def responder_accion(chat_id, texto_html, teclado_extra=None):
    if not chat_id or not TELEGRAM_TOKEN:
        return
    payload = {
        "chat_id": chat_id,
        "text": texto_html,
        "parse_mode": "HTML",
    }
    if teclado_extra:
        payload["reply_markup"] = teclado_extra
    tg_post("sendMessage", payload)


def mostrar_historial_y_yield(chat_id):
    historial = estado["historial_apuestas"]
    if not historial:
        responder_accion(chat_id, "📜 Aún no hay apuestas registradas en el historial.")
        return

    ganadas = sum(1 for ap in historial if ap["estado"] == "GANADA")
    perdidas = sum(1 for ap in historial if ap["estado"] == "PERDIDA")
    nulas = sum(1 for ap in historial if ap["estado"] == "NULA")
    pendientes = sum(1 for ap in historial if ap["estado"] == "PENDIENTE")

    unidades_netas = 0.0
    unidades_jugadas = 0.0
    for ap in historial:
        stake = ap.get("stake", 1.0)
        cuota = ap.get("cuota", 1.95)
        if ap["estado"] == "GANADA":
            unidades_netas += stake * (cuota - 1.0)
            unidades_jugadas += stake
        elif ap["estado"] == "PERDIDA":
            unidades_netas -= stake
            unidades_jugadas += stake

    total_finalizadas = ganadas + perdidas
    winrate = (ganadas / total_finalizadas * 100) if total_finalizadas > 0 else 0.0
    yield_val = (unidades_netas / unidades_jugadas * 100) if unidades_jugadas > 0 else 0.0

    resp = (
        f"📊 <b>HISTORIAL Y EFECTIVIDAD</b>\n\n"
        f"✅ Ganadas: <code>{ganadas}</code> | ❌ Perdidas: <code>{perdidas}</code> | "
        f"➖ Nulas: <code>{nulas}</code> | ⏳ Pendientes: <code>{pendientes}</code>\n"
        f"📈 <b>Win Rate:</b> <code>{winrate:.1f}%</code>\n"
        f"💰 <b>Unidades Netas:</b> <code>{unidades_netas:+.2f} U</code>\n"
        f"📉 <b>Yield:</b> <code>{yield_val:+.2f}%</code>\n\n"
        f"📜 <b>Últimos Picks:</b>\n"
    )

    for ap in historial[-5:]:
        icono = {"GANADA": "✅", "PERDIDA": "❌", "NULA": "➖"}.get(ap["estado"], "⏳")
        partido_esc = html.escape(str(ap["partido"]))
        estado_esc = html.escape(str(ap["estado"]))
        resp += f"{icono} <b>#{ap['id']}</b> - {partido_esc} @{ap.get('cuota', 1.95):.2f} [{estado_esc}]\n"

    teclado = {"inline_keyboard": [[{"text": "🔄 Refrescar Historial", "callback_data": "ver_historial"}]]}
    responder_accion(chat_id, resp, teclado_extra=teclado)

def mostrar_lista_partidos(chat_id):
    if not partidos_globales_activos:
        responder_accion(chat_id, "⚠️ No hay partidos programados o en juego para el día de hoy.")
        return

    partidos_activos_hoy = [
        r for r in partidos_globales_activos 
        if r["status"] not in ["FINISHED", "POSTPONED", "CANCELLED", "SUSPENDED"]
    ]

    if not partidos_activos_hoy:
        responder_accion(chat_id, "⚠️ No hay partidos en juego o por arrancar en este momento.")
        return

    resp = f"📋 <b>Partidos en vivo / por arrancar (Hoy):</b>\n\n"
    for r in partidos_activos_hoy[:8]:
        comp_esc = html.escape(str(r["competition"]))
        home_esc = html.escape(str(r["home_team"]))
        away_esc = html.escape(str(r["away_team"]))
        score_esc = html.escape(str(r["score"]))
        status_esc = html.escape(str(r["status"]))
        resp += (
            f"🏆 <b>{comp_esc}</b>\n"
            f"⚽ {home_esc} vs {away_esc} (<code>{score_esc}</code>)\n"
            f"⏱️ Estado: <code>{status_esc}</code> | Min: <code>{r['minute']}</code>\n\n"
        )

    teclado = {"inline_keyboard": [[{"text": "🔄 Refrescar", "callback_data": "ver_partidos"}]]}
    responder_accion(chat_id, resp, teclado_extra=teclado)

def construir_texto_alerta(liga_nombre, equipo_local, equipo_visita, goles_local, goles_visita, minuto, estado_partido, mercado_recomendado):
    liga_esc = html.escape(str(liga_nombre))
    local_esc = html.escape(str(equipo_local))
    visitante_esc = html.escape(str(equipo_visita))
    estado_esc = html.escape(str(estado_partido))
    mercado_esc = html.escape(str(mercado_recomendado))

    return (
        f"🚨 <b>¡Oportunidad Detectada!</b> 🔔\n\n"
        f"🏆 <b>{liga_esc}</b>\n"
        f"⚽ <b>{local_esc}</b> vs <b>{visitante_esc}</b>\n"
        f"⏱️ <b>Marcador Actual:</b> <code>{goles_local} - {goles_visita}</code>\n"
        f"⏳ <b>Minuto:</b> <code>{minuto}</code> ({estado_esc})\n\n"
        f"💡 <b>Mercado sugerido:</b> <code>{mercado_esc}</code>"
    )
    
# Conjunto para llevar registro de partidos ya alertados hoy por cada mercado específico
partidos_alertados_hoy = set()

def evaluar_y_notificar_avanzado():
    global partidos_globales_activos, partidos_alertados_hoy
    
    if not partidos_globales_activos:
        return

    nuevas_alertas = 0

    for p in partidos_globales_activos:
        fixture_id = p.get("fixture_id")
        status = p.get("status")
        home_team = p.get("home_team")
        away_team = p.get("away_team")
        competition = p.get("competition")
        home_goals = p.get("home_goals", 0)
        away_goals = p.get("away_goals", 0)
        total_goles = home_goals + away_goals
        
        # Evaluamos solo partidos que estén realmente en juego
        if status in ["IN_PLAY", "LIVE", "1H", "2H"]:
            
            # --- MERCADO 1: AMBOS MARCAN (BTTS) ---
            cuota_btts = p.get("odds_btts")
            condicion_btts = (home_goals >= 1 and away_goals >= 1)
            condicion_cuota_btts = (cuota_btts is not None and cuota_btts >= 2.0)
            
            if condicion_btts and condicion_cuota_btts and f"{fixture_id}_btts" not in partidos_alertados_hoy:
                texto_alerta = (
                    f"🚨 **¡ALERTA: AMBOS MARCAN (BTTS)!** 🚨\n\n"
                    f"🏆 **{competition}**\n"
                    f"⚽ {home_team} **{home_goals} - {away_goals}** {away_team}\n"
                    f"📈 **Cuota:** {cuota_btts}\n\n"
                    f"💡 *Mercado:* Ambos equipos ya convirtieron en directo."
                )
                enviar_mensaje_telegram(texto_alerta)
                partidos_alertados_hoy.add(f"{fixture_id}_btts")
                nuevas_alertas += 1

            # --- MERCADO 2: OVER 1.5 GOLES ---
            cuota_over15 = p.get("odds_over15")
            condicion_cuota_over15 = (cuota_over15 is not None and cuota_over15 >= 2.0)
            
            if total_goles >= 2 and condicion_cuota_over15 and f"{fixture_id}_ov15" not in partidos_alertados_hoy:
                texto_alerta = (
                    f"🚨 **¡ALERTA: OVER 1.5 GOLES!** 🚨\n\n"
                    f"🏆 **{competition}**\n"
                    f"⚽ {home_team} **{home_goals} - {away_goals}** {away_team} (Total: {total_goles})\n"
                    f"📈 **Cuota:** {cuota_over15}\n\n"
                    f"💡 *Mercado:* Límite de 1.5 superado en directo."
                )
                enviar_mensaje_telegram(texto_alerta)
                partidos_alertados_hoy.add(f"{fixture_id}_ov15")
                nuevas_alertas += 1

            # --- MERCADO 3: OVER 2.5 GOLES ---
            cuota_over25 = p.get("odds_over25")
            condicion_cuota_over25 = (cuota_over25 is not None and cuota_over25 >= 2.0)
            
            if total_goles >= 3 and condicion_cuota_over25 and f"{fixture_id}_ov25" not in partidos_alertados_hoy:
                texto_alerta = (
                    f"🚨 **¡ALERTA: OVER 2.5 GOLES!** 🚨\n\n"
                    f"🏆 **{competition}**\n"
                    f"⚽ {home_team} **{home_goals} - {away_goals}** {away_team} (Total: {total_goles})\n"
                    f"📈 **Cuota:** {cuota_over25}\n\n"
                    f"💡 *Mercado:* Límite de 2.5 superado en directo."
                )
                enviar_mensaje_telegram(texto_alerta)
                partidos_alertados_hoy.add(f"{fixture_id}_ov25")
                nuevas_alertas += 1

    log_diag(f"Evaluación completada. Nuevas alertas en este ciclo: {nuevas_alertas}")

async def escuchar_comandos_telegram():
    if not TELEGRAM_TOKEN:
        log_diag("TELEGRAM_TOKEN no configurado; polling desactivado.")
        return
    offset = 0
    while True:
        try:
            response = await asyncio.to_thread(_poll_updates, offset)
            if response and response.ok:
                for result in response.json().get("result", []):
                    offset = result["update_id"] + 1

                    message = result.get("message")
                    if message:
                        chat = message.get("chat", {})
                        text = (message.get("text") or "").strip().lower()
                        if chat.get("id"):
                            estado["chat_id"] = chat["id"]
                            guardar_estado()
                        if text in ["/start", "/menu"]:
                            enviar_menu_principal(estado["chat_id"])
                        elif text in ["/historial", "/yield"]:
                            mostrar_historial_y_yield(estado["chat_id"])

                    callback_query = result.get("callback_query")
                    if callback_query:
                        chat = callback_query.get("message", {}).get("chat", {})
                        if chat.get("id"):
                            estado["chat_id"] = chat["id"]
                            guardar_estado()
                        data = callback_query.get("data", "")
                        query_id = callback_query.get("id")

                        tg_post("answerCallbackQuery", {"callback_query_id": query_id})

                        if data == "ver_partidos":
                            mostrar_lista_partidos(estado["chat_id"])
                        elif data == "ver_historial":
                            mostrar_historial_y_yield(estado["chat_id"])
                        elif data == "actualizar":
                            await asyncio.to_thread(escanear_mercados_avanzados)
                            responder_accion(
                                estado["chat_id"],
                                f"🔄 ¡Datos actualizados vía Football-Data!\n🏆 Partidos de hoy: {len(partidos_globales_activos)}",
                            )
                        elif data.startswith("share_"):
                            id_str = data.split("_", 1)[1]
                            if id_str.isdigit():
                                ap_id = int(id_str)
                                ap = next((x for x in estado["historial_apuestas"] if x["id"] == ap_id), None)
                                if ap:
                                    partido_esc = html.escape(str(ap["partido"]))
                                    responder_accion(
                                        estado["chat_id"],
                                        f"📤 <b>Pick #{ap['id']}</b>: {partido_esc} @ <code>{ap.get('cuota', 1.95):.2f}</code> | Stake: <code>1U</code>",
                                    )
                        elif data.startswith(("win_", "loss_", "void_")):
                            tipo, id_str = data.split("_", 1)
                            if id_str.isdigit():
                                apuesta_id = int(id_str)
                                for ap in estado["historial_apuestas"]:
                                    if ap["id"] == apuesta_id:
                                        if tipo == "win":
                                            ap["estado"] = "GANADA"
                                        elif tipo == "loss":
                                            ap["estado"] = "PERDIDA"
                                        elif tipo == "void":
                                            ap["estado"] = "NULA"
                                        guardar_estado()
                                        responder_accion(
                                            estado["chat_id"],
                                            f"📌 <b>Pick #{apuesta_id}</b> actualizado a: <b>{ap['estado']}</b>",
                                        )
                                        break
        except Exception as e:
            log_diag(f"Error en bucle de Telegram: {e}")
            await asyncio.sleep(5)


async def bucle_principal_analisis():
    while True:
        try:
            escanear_mercados_avanzados()
            evaluar_y_notificar_avanzado()
        except Exception as e:
            log_diag(f"Error en bucle de análisis: {e}")
        await asyncio.sleep(180)


def main():
    cargar_estado()
    log_diag("Iniciando servidor web Flask en hilo separado...")
    t = Thread(target=run_flask, daemon=True)
    t.start()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def iniciar_todo():
        await asyncio.gather(
            escuchar_comandos_telegram(),
            bucle_principal_analisis(),
        )

    try:
        loop.run_until_complete(iniciar_todo())
    except KeyboardInterrupt:
        log_diag("Bot detenido manualmente.")


if __name__ == "__main__":
    main()
    
