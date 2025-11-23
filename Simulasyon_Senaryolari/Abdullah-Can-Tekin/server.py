import asyncio
import logging
from websockets.server import serve
from datetime import datetime, timezone

from ocpp.v16 import ChargePoint as cp, call, call_result 
from ocpp.v16.enums import RegistrationStatus, RemoteStartStopStatus
from ocpp.routing import on

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [SUNUCU] - %(message)s')

class SablonChargePoint(cp):
    
    @on('BootNotification')
    async def on_boot_notification(self, charge_point_model, charge_point_vendor, **kwargs):
        logging.info(f"BAĞLANTI İSTEĞİ: {charge_point_model} ({charge_point_vendor})")
        return call_result.BootNotification(
            current_time=datetime.now(timezone.utc).isoformat(),
            interval=10,
            status=RegistrationStatus.accepted
        )

    @on('Heartbeat')
    async def on_heartbeat(self, **kwargs):
        logging.info("Heartbeat (Yaşam Sinyali) alındı.")
        return call_result.Heartbeat(
            current_time=datetime.now(timezone.utc).isoformat()
        )

    # --- ANOMALİ İÇİN EKLENEN KISIM BAŞLANGIÇ ---
    @on('Authorize')
    async def on_authorize(self, id_tag, **kwargs):
        logging.info(f"YETKİLENDİRME İSTEĞİ GELDİ: Kart ID = {id_tag}")

        # ZAFİYET SİMÜLASYONU:
        # Eğer gelen ID, bizim SQL Injection payload'umuzu içeriyorsa, 
        # sunucu veritabanı kandırılmış gibi davranıp KABUL EDECEK.
        
        if "' OR '1'='1'" in id_tag:
            logging.warning(f"⚠️  KRİTİK GÜVENLİK UYARISI: SQL Injection Payload'u Tespit Edildi! -> {id_tag}")
            logging.warning("-> SİSTEM ZAFİYETİ TETİKLENDİ: Veritabanı manipüle edildi, Admin girişi ONAYLANDI.")
            
            # Normalde reddetmesi gerekirken, zafiyet yüzünden kabul ediyor:
            return call_result.Authorize(
                id_tag_info={'status': RegistrationStatus.accepted}
            )
        else:
            # Normal (saldırı olmayan) geçersiz kartlar reddedilir
            logging.info("Bilinmeyen kart, reddediliyor.")
            return call_result.Authorize(
                id_tag_info={'status': RegistrationStatus.invalid}
            )
    # --- ANOMALİ İÇİN EKLENEN KISIM BİTİŞ ---

    @on('MeterValues')
    async def on_meter_values(self, connector_id, meter_value, **kwargs):
        try:
            value = meter_value[0]['sampled_value'][0]['value']
            logging.info(f"ENERJİ RAPORU: {value} Wh (Konnektör: {connector_id})")
        except Exception as e:
            logging.error(f"Veri okuma hatası: {e}")
        return call_result.MeterValues()

async def on_connect(websocket, path):
    try:
        charge_point_id = path.strip('/')
        logging.info(f"Cihaz Bağlandı: {charge_point_id}")
        cp_instance = SablonChargePoint(charge_point_id, websocket)
        await cp_instance.start()
    except Exception as e:
        logging.error(f"Bağlantı hatası: {e}")

async def main():
    async with serve(on_connect, '0.0.0.0', 9000):
        logging.info("--- CSMS SUNUCUSU BAŞLATILDI (Port: 9000) ---")
        await asyncio.Future()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
     
