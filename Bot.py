import asyncio
from datetime import datetime
import os
from threading import Thread
from flask import Flask
import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
FOOTBALL_API_KEY = os.environ.get("FOOTBALL_API_KEY")

HEADERS = {"X-Auth-Token": FOOTBALL_API_KEY} if FOOTBALL_API_KEY else {}
CHAT_ID = None

partidos_globales_activos = []

estadisticas_sesion = {
    "enviadas": 0,
    "acertadas": 0,
    "unidades_jugadas": 0.0,
    "unidades_ganadas": 0.0
}

app = Flask(__name__)

@app.route("/")
def home():
    return "Tobipybot Pro operativo 24/7 con filtro estricto de fecha 🚀"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def enviar_alerta_telegram_con_share(mensaje):
    global CHAT_ID, estadisticas_sesion
    if not CHAT_ID or not TELEGRAM_TOKEN:
        return
    
    estadisticas_sesion["enviadas"] += 1
    estadisticas_sesion["unidades_jugadas"] += 1.0

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    teclado = {
        "inline_keyboard": [
            [
                {"text": "✅ Registrar Acierto (+1.0U)", "callback_data": "hit_win"},
                {"text": "❌ Registrar Fallo", "callback_data": "hit_loss"}
            ],
            [
                {"text": "📤 Copiar / Formato Comunidad", "callback_data": "copiar_formato"}
            ]
        ]
    }
    
    payload = {
        "chat_id": CHAT_ID,
        "text": f"{mensaje}\n\n🤖 _Tobipybot Pro (Gestión Avanzada)_",
        "parse_mode": "Markdown",
        "reply_markup": teclado
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass

def escanear_mercados_avanzados():
    global partidos_globales_activos
    if not FOOTBALL_API_KEY:
        return
    # Consultamos partidos del día actual directamente en la URL de la API
    hoy_str = datetime.now().strftime("%Y-%m-%d")
    url = f"https://api.football-data.org/v4/matches?dateFrom={hoy_str}&dateTo={hoy_str}"
    
    for intento in range(3):
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            if response.ok:
                data = response.json()
                matches = data.get("matches", [])
                lista_temp = []
                for m in matches:
                    # Filtro de seguridad extra: verificar estado y fecha exacta
                    utc_date = m.get("utcDate", "")
                    status = m.get("status", "")
                    
                    if not utc_date.startswith(hoy_str):
                        continue
                        
                    # Aceptamos en juego (LIVE) o programados para hoy
                    if status not in ["LIVE", "IN_PLAY", "PAUSED", "TIMED"]:
                        continue

                    home = m.get("homeTeam", {}).get("name", "Local")
                    away = m.get("awayTeam", {}).get("name", "Visitante")
                    competition = m.get("competition", {}).get("name", "Liga Internacional")
                    
                    # Si la API no provee minuto exacto, simulamos para pruebas o leemos si existe
                    minute = m.get("minute", 0)
                    if status == "TIMED":
                        minute = 0 # Partido aún no empieza
                        
                    lista_temp.append({
                        "competition": competition,
                        "home_team": home,
                        "away_team": away,
                        "minute": minute,
                        "status": status,
                        "odds_home": 1.95,
                        "odds_corners": 2.05,
                        "odds_cards": 1.88,
                        "odds_shots": 2.15
                    })
                partidos_globales_activos = lista_temp
                return
        except Exception:
            pass
        import time
        time.sleep(2)

def enviar_menu_principal(chat_id):
    if not chat_id or not TELEGRAM_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    teclado = {
        "inline_keyboard": [
            [
                {"text": "📋 Ver Partidos de Hoy", "callback_data": "ver_partidos"},
                {"text": "📊 Yield & Estadísticas", "callback_data": "ver_yield"}
            ],
            [
                {"text": "🔄 Actualizar Datos", "callback_data": "actualizar"}
            ]
        ]
    }
    payload = {
        "chat_id": chat_id,
        "text": "👋 ¡Panel Pro de **Tobipybot** activo!\n\nFiltro de fecha actualizado a HOY:",
        "parse_mode": "Markdown",
        "reply_markup": teclado
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass

def responder_accion(chat_id, texto, teclado_extra=None):
    if not chat_id or not TELEGRAM_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": texto,
        "parse_mode": "Markdown"
    }
    if teclado_extra:
        payload["reply_markup"] = teclado_extra
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass

async def escuchar_comandos_telegram():
    global CHAT_ID, estadisticas_sesion
    if not TELEGRAM_TOKEN:
        return
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}&timeout=30"
            response = requests.get(url, timeout=35)
            if response.ok:
                for result in response.json().get("result", []):
                    offset = result["update_id"] + 1
                    
                    message = result.get("message")
                    if message:
                        chat = message.get("chat", {})
                        text = message.get("text", "").strip().lower()
                        if chat:
                            CHAT_ID = chat.get("id")
                        if text in ["/start", "/menu"]:
                            enviar_menu_principal(CHAT_ID)
                        elif text == "/yield":
                            mostrar_yield(CHAT_ID)

                    callback_query = result.get("callback_query")
                    if callback_query:
                        chat = callback_query.get("message", {}).get("chat", {})
                        if chat:
                            CHAT_ID = chat.get("id")
                        data = callback_query.get("data")
                        query_id = callback_query.get("id")
                        
                        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery", json={"callback_query_id": query_id})
                        
                        if data == "ver_partidos":
                            mostrar_lista_partidos(CHAT_ID)
                        elif data == "ver_yield":
                            mostrar_yield(CHAT_ID)
                        elif data == "actualizar":
                            escanear_mercados_avanzados()
                            responder_accion(CHAT_ID, f"🔄 ¡Datos actualizados!\n🏆 Partidos de hoy vigilados: {len(partidos_globales_activos)}")
                        elif data == "hit_win":
                            estadisticas_sesion["acertadas"] += 1
                            estadisticas_sesion["unidades_ganadas"] += 0.95
                            responder_accion(CHAT_ID, "✅ *¡Apuesta registrada como ACERTADA!*")
                        elif data == "hit_loss":
                            estadisticas_sesion["unidades_ganadas"] -= 1.0
                            responder_accion(CHAT_ID, "❌ *Apuesta registrada como FALLIDA.*")
                        elif data == "copiar_formato":
                            responder_accion(CHAT_ID, "📋 *Formato copiado para tu comunidad.*")

        except Exception:
            pass
        await asyncio.sleep(2)

def mostrar_yield(chat_id):
    enviadas = estadisticas_sesion["enviadas"]
    acertadas = estadisticas_sesion["acertadas"]
    jugadas = estadisticas_sesion["unidades_jugadas"]
    ganadas = estadisticas_sesion["unidades_ganadas"]
    
    winrate = (acertadas / enviadas * 100) if enviadas > 0 else 0
    yield_val = (ganadas / jugadas * 100) if jugadas > 0 else 0

    resp = (
        f"📊 **ESTADÍSTICAS Y YIELD (SESIÓN)**\n\n"
        f"🎯 Alertas enviadas: `{enviadas}`\n"
        f"✅ Acertadas: `{acertadas}`\n"
        f"📈 Win Rate: `{winrate:.1f}%`\n"
        f"💰 Unidades Netas: `{ganadas:+.2f} U`\n"
        f"📉 Yield Estimado: `{yield_val:+.2f}%`"
    )
    responder_accion(chat_id, resp)

def mostrar_lista_partidos(chat_id):
    if not partidos_globales_activos:
        responder_accion(chat_id, "⚠️ No hay partidos programados o en juego para el día de hoy.")
        return
    resp = "📋 **Partidos de HOY bajo vigilancia:**\n\n"
    for r in partidos_globales_activos[:8]:
        resp += f"🏆 *{r['competition']}*\n⚽ {r['home_team']} vs {r['away_team']}\n⏱️ Estado: `{r['status']}`\n\n"
    
    teclado = {
        "inline_keyboard": [
            [{"text": "🔄 Refrescar", "callback_data": "ver_partidos"}]
        ]
    }
    responder_accion(chat_id, resp, teclado_extra=teclado)

def evaluar_y_notificar_avanzado():
    for match in partidos_globales_activos:
        minute = match["minute"]
        status = match["status"]
        comp = match["competition"]
        home = match["home_team"]
        away = match["away_team"]

        # Solo disparamos alertas si el partido está verdaderamente en juego (LIVE)
        if status in ["LIVE", "IN_PLAY", "PAUSED"]:
            if 20 <= minute <= 75 and 1.90 <= match["odds_home"] <= 2.10:
                enviar_alerta_telegram_con_share(
                    f"🎯 *[PICK PRO: CUOTA 2]*\n"
                    f"🏆 *{comp}*\n"
                    f"🏟️ *{home} vs {away}* (Min {minute}')\n"
                    f"💰 Mercado: *Gana {home}*\n"
                    f"📈 Cuota: *{match['odds_home']:.2f}*"
                )
            elif 34 <= minute <= 42:
                enviar_alerta_telegram_con_share(
                    f"🚩 *[PICK PRO: CÓRNERS]*\n"
                    f"🏆 *{comp}*\n"
                    f"🏟️ *{home} vs {away}* (Min {minute}')\n"
                    f"💰 Mercado: *Over Córners 1ª Mitad*\n"
                    f"📈 Cuota: *{match['odds_corners']:.2f}*"
                )

async def ciclo_monitoreo():
    while True:
        try:
            escanear_mercados_avanzados()
            evaluar_y_notificar_avanzado()
        except Exception:
            pass
        await asyncio.sleep(120)

async def main():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    await asyncio.gather(escuchar_comandos_telegram(), ciclo_monitoreo())

if __name__ == "__main__":
    asyncio.run(main())
                            
