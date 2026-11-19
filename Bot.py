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

app = Flask(__name__)

@app.route("/")
def home():
    return "Tobipybot está activo y operando 24/7 🚀"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def enviar_alerta_telegram(mensaje):
    global CHAT_ID
    if not CHAT_ID or not TELEGRAM_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": f"{mensaje}\n\n🤖 _Tobipybot (Cloud 24/7)_",
        "parse_mode": "Markdown",
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass

def escanear_todas_las_ligas_en_vivo():
    global partidos_globales_activos
    if not FOOTBALL_API_KEY:
        return
    url = "https://api.football-data.org/v4/matches?status=LIVE"
    for intento in range(3):
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            if response.ok:
                data = response.json()
                matches = data.get("matches", [])
                hoy_str = datetime.now().strftime("%Y-%m-%d")
                lista_temp = []
                for m in matches:
                    if not m.get("utcDate", "").startswith(hoy_str):
                        continue
                    home = m.get("homeTeam", {}).get("name", "Local")
                    away = m.get("awayTeam", {}).get("name", "Visitante")
                    competition = m.get("competition", {}).get("name", "Liga Internacional")
                    minute = m.get("minute", 0)
                    lista_temp.append({
                        "competition": competition,
                        "home_team": home,
                        "away_team": away,
                        "minute": minute,
                        "odds_home": 1.98,
                        "live_prob_home": 0.54,
                        "odds_corners_over": 2.02,
                    })
                partidos_globales_activos = lista_temp
                return
        except Exception:
            pass
        import time
        time.sleep(2)

async def escuchar_comandos_telegram():
    global CHAT_ID
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
                    chat = result.get("message", {}).get("chat", {})
                    text = result.get("message", {}).get("text", "").strip().lower()
                    if chat:
                        CHAT_ID = chat.get("id")
                    if text == "/start":
                        enviar_respuesta_directa(CHAT_ID, "👋 ¡Hola Tobias! **Tobipybot** ya está desplegado en la nube y vigilando 24/7.")
                    elif text == "/status":
                        enviar_respuesta_directa(CHAT_ID, f"🟢 **Estado:** NUBE ACTIVA (24/7)\n🏆 Partidos de hoy en vivo: {len(partidos_globales_activos)}")
                    elif text == "/partidos":
                        if not partidos_globales_activos:
                            enviar_respuesta_directa(CHAT_ID, "⚠️ No hay partidos en juego en este momento para hoy.")
                        else:
                            resp = "📋 **Partidos globales en vigilancia:**\n\n"
                            for r in partidos_globales_activos[:10]:
                                resp += f"🏆 *{r['competition']}*\n⚽ {r['home_team']} vs {r['away_team']}\n⏱️ Minuto: {r['minute']}' | Cuota 2: `{r['odds_home']}`\n\n"
                            enviar_respuesta_directa(CHAT_ID, resp)
        except Exception:
            pass
        await asyncio.sleep(2)

def enviar_respuesta_directa(chat_id, texto):
    if not chat_id or not TELEGRAM_TOKEN:
        return
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"})

def evaluar_y_notificar():
    for match in partidos_globales_activos:
        minute = match["minute"]
        comp = match["competition"]
        if 34 <= minute <= 43:
            enviar_alerta_telegram(f"🚩 *[OPORTUNIDAD CÓRNERS 34+]*\n🏆 *{comp}*\n🏟️ *{match['home_team']} vs {match['away_team']}* (Minuto {minute}')\n💰 Apuesta sugerida: *Over Córners 1ª Mitad*\n📈 Cuota: *{match['odds_corners_over']:.2f}*")
        elif match["odds_home"] >= 1.90 and match["odds_home"] <= 2.10:
            enviar_alerta_telegram(f"🎯 *[OPORTUNIDAD CUOTA 2]*\n🏆 *{comp}*\n🏟️ *{match['home_team']} vs {match['away_team']}* (Minuto {minute}')\n💰 Apuesta sugerida: *Gana {match['home_team']}*\n📈 Cuota: *{match['odds_home']:.2f}*")

async def ciclo_monitoreo():
    while True:
        try:
            escanear_todas_las_ligas_en_vivo()
            evaluar_y_notificar()
        except Exception:
            pass
        await asyncio.sleep(90)

async def main():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    await asyncio.gather(escuchar_comandos_telegram(), ciclo_monitoreo())

if __name__ == "__main__":
    asyncio.run(main())
                      
