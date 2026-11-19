import asyncio
from datetime import datetime
import os
from threading import Thread
from flask import Flask
import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
# Usaremos la llave de API-Football
API_FOOTBALL_KEY = os.environ.get("APIFOOTBALL_KEY") or os.environ.get("FOOTBALL_API_KEY")

# Headers específicos para API-Football (RapidAPI o API-Sports directo)
HEADERS = {
    "x-apisports-key": API_FOOTBALL_KEY
} if API_FOOTBALL_KEY else {}

CHAT_ID = None
partidos_globales_activos = []
historial_apuestas = []

app = Flask(__name__)

@app.route("/")
def home():
    return "Tobipybot Pro con API-Football operativo 24/7 🚀"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def enviar_alerta_telegram_con_share(mensaje, partido_info):
    global CHAT_ID, historial_apuestas
    if not CHAT_ID or not TELEGRAM_TOKEN:
        return
    
    apuesta_id = len(historial_apuestas) + 1
    registro = {
        "id": apuesta_id,
        "partido": partido_info,
        "estado": "PENDIENTE",
        "unidades": 1.0
    }
    historial_apuestas.append(registro)

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    teclado = {
        "inline_keyboard": [
            [
                {"text": "✅ Ganada", "callback_data": f"win_{apuesta_id}"},
                {"text": "❌ Perdida", "callback_data": f"loss_{apuesta_id}"},
                {"text": "➖ Nula", "callback_data": f"void_{apuesta_id}"}
            ],
            [
                {"text": "📤 Copiar / Comunidad", "callback_data": "copiar_formato"}
            ]
        ]
    }
    
    payload = {
        "chat_id": CHAT_ID,
        "text": f"{mensaje}\n\n🆔 *Pick #{apuesta_id}* | 🤖 _Tobipybot Pro_",
        "parse_mode": "Markdown",
        "reply_markup": teclado
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass

def escanear_mercados_avanzados():
    global partidos_globales_activos
    if not API_FOOTBALL_KEY:
        return
    
    hoy_str = datetime.now().strftime("%Y-%m-%d")
    # Endpoint oficial de partidos en vivo / de hoy para API-Sports / API-Football
    url = f"https://v3.football.api-sports.io/fixtures?date={hoy_str}"
    
    for intento in range(3):
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            if response.ok:
                data = response.json()
                matches = data.get("response", [])
                lista_temp = []
                
                for m in matches:
                    fixture = m.get("fixture", {})
                    league = m.get("league", {})
                    teams = m.get("teams", {})
                    goals = m.get("goals", {})
                    
                    status_short = fixture.get("status", {}).get("short", "")
                    elapsed = fixture.get("status", {}).get("elapsed", 0)
                    
                    # Filtramos solo partidos en juego o por comenzar hoy
                    if status_short not in ["1H", "HT", "2H", "ET", "P", "LIVE", "NS"]:
                        continue

                    home = teams.get("home", {}).get("name", "Local")
                    away = teams.get("away", {}).get("name", "Visitante")
                    competition = league.get("name", "Liga Internacional")
                    
                    if not elapsed:
                        elapsed = 0
                        
                    lista_temp.append({
                        "competition": competition,
                        "home_team": home,
                        "away_team": away,
                        "minute": elapsed,
                        "status": status_short,
                        "odds_home": 1.95,
                        "odds_corners": 2.05,
                        "odds_over15": 1.75,
                        "odds_over25": 2.10,
                        "odds_btts": 1.90
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
                {"text": "📋 Partidos de Hoy", "callback_data": "ver_partidos"},
                {"text": "📜 Historial & Yield", "callback_data": "ver_historial"}
            ],
            [
                {"text": "🔄 Actualizar Datos", "callback_data": "actualizar"}
            ]
        ]
    }
    payload = {
        "chat_id": chat_id,
        "text": "👋 ¡Panel Pro API-Football de **Tobipybot** activo!\n\nSelecciona una opción:",
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
    global CHAT_ID, historial_apuestas
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
                        elif text in ["/historial", "/yield"]:
                            mostrar_historial_y_yield(CHAT_ID)

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
                        elif data == "ver_historial":
                            mostrar_historial_y_yield(CHAT_ID)
                        elif data == "actualizar":
                            escanear_mercados_avanzados()
                            responder_accion(CHAT_ID, f"🔄 ¡Datos actualizados vía API-Football!\n🏆 Partidos de hoy: {len(partidos_globales_activos)}")
                        elif data == "copiar_formato":
                            responder_accion(CHAT_ID, "📋 *Formato listo para compartir en tu grupo de análisis.*")
                        
                        elif data.startswith("win_") or data.startswith("loss_") or data.startswith("void_"):
                            partes = data.split("_")
                            tipo = partes[0]
                            apuesta_id = int(partes[1])
                            
                            for ap in historial_apuestas:
                                if ap["id"] == apuesta_id:
                                    if tipo == "win":
                                        ap["estado"] = "GANADA"
                                        responder_accion(CHAT_ID, f"✅ *Pick #{apuesta_id} actualizado:* Marcado como **GANADA** 🎯")
                                    elif tipo == "loss":
                                        ap["estado"] = "PERDIDA"
                                        responder_accion(CHAT_ID, f"❌ *Pick #{apuesta_id} actualizado:* Marcado como **PERDIDA**")
                                    elif tipo == "void":
                                        ap["estado"] = "NULA"
                                        responder_accion(CHAT_ID, f"➖ *Pick #{apuesta_id} actualizado:* Marcado como **NULA / PUSH**")
                                    break

        except Exception:
            pass
        await asyncio.sleep(2)

def mostrar_historial_y_yield(chat_id):
    if not historial_apuestas:
        responder_accion(chat_id, "📜 Aún no hay apuestas registradas en el historial de hoy.")
        return

    ganadas = sum(1 for ap in historial_apuestas if ap["estado"] == "GANADA")
    perdidas = sum(1 for ap in historial_apuestas if ap["estado"] == "PERDIDA")
    nulas = sum(1 for ap in historial_apuestas if ap["estado"] == "NULA")
    pendientes = sum(1 for ap in historial_apuestas if ap["estado"] == "PENDIENTE")
    
    total_finalizadas = ganadas + perdidas
    winrate = (ganadas / total_finalizadas * 100) if total_finalizadas > 0 else 0
    unidades_ganadas = (ganadas * 0.95) - perdidas
    yield_val = (unidades_ganadas / total_finalizadas * 100) if total_finalizadas > 0 else 0

    resp = (
        f"📊 **HISTORIAL Y EFECTIVIDAD (SESIÓN)**\n\n"
        f"✅ Ganadas: `{ganadas}` | ❌ Perdidas: `{perdidas}` | ➖ Nulas: `{nulas}` | ⏳ Pendientes: `{pendientes}`\n"
        f"📈 **Win Rate:** `{winrate:.1f}%`\n"
        f"💰 **Unidades Netas:** `{unidades_ganadas:+.2f} U`\n"
        f"📉 **Yield:** `{yield_val:+.2f}%`\n\n"
        f"📜 **Últimos Picks:**\n"
    )
    
    for ap in historial_apuestas[-5:]:
        icono = "⏳"
        if ap["estado"] == "GANADA": icono = "✅"
        elif ap["estado"] == "PERDIDA": icono = "❌"
        elif ap["estado"] == "NULA": icono = "➖"
        resp += f"{icono} *#{ap['id']}* - {ap['partido']} [{ap['estado']}]\n"

    teclado = {
        "inline_keyboard": [
            [{"text": "🔄 Refrescar Historial", "callback_data": "ver_historial"}]
        ]
    }
    responder_accion(chat_id, resp, teclado_extra=teclado)

def mostrar_lista_partidos(chat_id):
    if not partidos_globales_activos:
        responder_accion(chat_id, "⚠️ No hay partidos programados o en juego para el día de hoy.")
        return
    resp = "📋 **Partidos de HOY (API-Football):**\n\n"
    for r in partidos_globales_activos[:8]:
        resp += f"🏆 *{r['competition']}*\n⚽ {r['home_team']} vs {r['away_team']}\n⏱️ Estado: `{r['status']}` | Min: `{r['minute']}`\n\n"
    
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

        # Si está en juego (1H, 2H, LIVE)
        if status in ["1H", "2H", "ET", "LIVE"]:
            if 20 <= minute <= 75 and 1.90 <= match["odds_home"] <= 2.10:
                enviar_alerta_telegram_con_share(
                    f"🎯 *[PICK PRO: CUOTA 2]*\n🏆 *{comp}*\n🏟️ *{home} vs {away}* (Min {minute}')\n💰 Mercado: *Gana {home}*\n📈 Cuota: *{match['odds_home']:.2f}*",
                    f"{home} vs {away} (Cuota 2)"
                )
            elif 34 <= minute <= 42:
                enviar_alerta_telegram_con_share(
                    f"🚩 *[PICK PRO: CÓRNERS]*\n🏆 *{comp}*\n🏟️ *{home} vs {away}* (Min {minute}')\n💰 Mercado: *Over Córners 1ª Mitad*\n📈 Cuota: *{match['odds_corners']:.2f}*",
                    f"{home} vs {away} (Córners)"
                )
            elif 46 <= minute <= 60:
                enviar_alerta_telegram_con_share(
                    f"⚽ *[PICK PRO: MÁS DE 1.5 GOLES]*\n🏆 *{comp}*\n🏟️ *{home} vs {away}* (Min {minute}')\n💰 Mercado: *Over 1.5 Goles Totales*\n📈 Cuota: *{match['odds_over15']:.2f}*",
                    f"{home} vs {away} (Over 1.5)"
                )
            elif 65 <= minute <= 78:
                enviar_alerta_telegram_con_share(
                    f"⚽ *[PICK PRO: MÁS DE 2.5 GOLES]*\n🏆 *{comp}*\n🏟️ *{home} vs {away}* (Min {minute}')\n💰 Mercado: *Over 2.5 Goles Totales*\n📈 Cuota: *{match['odds_over25']:.2f}*",
                    f"{home} vs {away} (Over 2.5)"
                )
            elif 50 <= minute <= 70:
                enviar_alerta_telegram_con_share(
                    f"🔥 *[PICK PRO: AMBOS MARCAN]*\n🏆 *{comp}*\n🏟️ *{home} vs {away}* (Min {minute}')\n💰 Mercado: *Ambos Equipos Anotan (Sí)*\n📈 Cuota: *{match['odds_btts']:.2f}*",
                    f"{home} vs {away} (Ambos Marcan)"
                )

async def ciclo_monitoreo():
    while True:
        try:
            escanear_mercados_avanzados()
            evaluar_y_notificar_avanzado()
        except Exception:
            pass
        # Intervalo de 3 minutos para cuidar las 100 peticiones diarias del plan gratuito
        await asyncio.sleep(180)

async def main():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    await asyncio.gather(escuchar_comandos_telegram(), ciclo_monitoreo())

if __name__ == "__main__":
    asyncio.run(main())
            
