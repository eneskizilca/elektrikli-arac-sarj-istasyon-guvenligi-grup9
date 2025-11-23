import asyncio
import logging
import random
import json
from datetime import datetime
from websockets import connect

logging.basicConfig(level=logging.INFO)


# =========================
#  ANOMALİ AYARLARI
# =========================
ANOMALY_ENABLED = True                # Anomali açık/kapalı
NORMAL_INTERVAL = 1                   # Normal örnekleme: 1 saniye
MANIPULATED_INTERVAL = 10             # Anomalide: 10 saniye
JITTER_MAX = 2                        # Ek rastgele gecikme (±2 sn)
CRITICAL_EVENT_DURATION = 5           # Kritik olay süresi (ama gönderilmeyecek)
CRITICAL_EVENT_PROB = 0.15            # %15 ihtimal kritik olay oluşur (gizlenecek)


# =========================
#  TELEMETRİ ÜRETİCİ
# =========================
def generate_normal_telemetry():
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "voltage": round(random.uniform(220, 230), 2),
        "current": round(random.uniform(10, 32), 2),
        "power": round(random.uniform(2, 7), 2),
        "status": "Normal"
    }


def generate_critical_event():
    # Bu olay oluşacak ama anomalide GÖNDERİLMEYECEK
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "voltage": round(random.uniform(260, 310), 2),   # tehlikeli sıçrama
        "current": round(random.uniform(40, 60), 2),
        "power": round(random.uniform(15, 25), 2),
        "status": "CRITICAL_SPIKE"
    }


# =========================
#  TELEMETRİ GÖNDERİCİ
# =========================
async def telemetry_loop(ws):
    logging.info("Telemetry loop started.")

    critical_event_active = False
    critical_event_end_time = None

    while True:

        # --------------------------
        # Kritik olay üretme (client içinde)
        # --------------------------
        if random.random() < CRITICAL_EVENT_PROB and not critical_event_active:
            critical_event_active = True
            critical_event_end_time = datetime.utcnow().timestamp() + CRITICAL_EVENT_DURATION

        # Kritik olay devam ediyorsa ama GÖNDERİLMEYECEK
        if critical_event_active:
            critical_data = generate_critical_event()
            logging.warning(f"[GİZLENEN OLAY] Kritik olay oluştu ancak sunucuya gönderilmiyor: {critical_data}")

            if datetime.utcnow().timestamp() >= critical_event_end_time:
                critical_event_active = False

            # Sunucuya hiçbir şey gönderme → olay gizlenmiş olur
            await asyncio.sleep(0.5)
            continue

        # --------------------------
        # Normal telemetri gönderme
        # --------------------------
        data = generate_normal_telemetry()

        await ws.send(json.dumps(data))
        logging.info(f"Telemetri gönderildi: {data}")

        # --------------------------
        # Adaptive Sampling Manipülasyonu
        # --------------------------
        if ANOMALY_ENABLED:
            interval = MANIPULATED_INTERVAL + random.uniform(0, JITTER_MAX)
        else:
            interval = NORMAL_INTERVAL

        await asyncio.sleep(interval)


# =========================
#  OCPP BAĞLANTISI
# =========================
async def main():
    uri = "ws://localhost:9000"   # Sunucu adresi (şablondaki gibi bırak)
    async with connect(uri) as ws:
        logging.info("Sunucuya bağlanıldı.")

        # Telemetri döngüsünü başlat
        await telemetry_loop(ws)


if __name__ == "__main__":
    asyncio.run(main())
