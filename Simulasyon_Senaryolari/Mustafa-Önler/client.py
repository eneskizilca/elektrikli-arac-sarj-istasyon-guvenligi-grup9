import asyncio
import logging
import can
import websockets
from datetime import datetime, timezone

from ocpp.v16 import ChargePoint as cp, call, call_result
from ocpp.v16.enums import RegistrationStatus, RemoteStartStopStatus
from ocpp.routing import on

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [MITM-ISTEMCI] - %(message)s')

# --- DONANIM (vcan0) AYARI ---
try:
    can_bus = can.interface.Bus(channel='vcan0', interface='socketcan')
    logging.info("Donanım (vcan0) bağlantısı BAŞARILI.")
except Exception:
    can_bus = None

def donanima_komut_yolla(can_id, data):
    if can_bus:
        try:
            msg = can.Message(arbitration_id=can_id, data=data, is_extended_id=False)
            can_bus.send(msg)
            logging.info(f"Donanıma İletildi -> ID: {hex(can_id)} Data: {data}")
        except Exception as e:
            logging.error(f"Donanım Hatası: {e}")

class MitmSaldiriChargePoint(cp):

    async def send_boot_notification(self):
        request = call.BootNotification(
            charge_point_model="SecVolt-Charger",
            charge_point_vendor="SecVolt-Team"
        )
        response = await self.call(request)
        if response.status == RegistrationStatus.accepted:
            logging.info("BootNotification KABUL EDİLDİ.")

    @on('RemoteStartTransaction')
    async def on_remote_start(self, id_tag, **kwargs):
        """
        ANOMALİ SENARYOSU: MitM (Energy Flow Parameter Tampering)
        Sunucudan 'BAŞLAT' emri gelir, ancak saldırgan bunu 'DURDUR'a çevirir.
        """
        logging.info(f"GELEN PAKET: RemoteStartTransaction (Kart: {id_tag})")
        
        # --- SALDIRI BAŞLANGICI ---
        logging.warning("⚔️  UYARI: MitM Saldırısı Tespit Edildi!")
        logging.warning("🛑  MANİPÜLASYON: 'Start' komutu yolda 'Stop' olarak değiştirildi.")
        
        # NORMALDE OLMASI GEREKEN:
        # donanima_komut_yolla(0x200, [0x01, 0x01]) # Şarjı Başlat
        
        # SALDIRGANIN YAPTIĞI (ANOMALİ):
        donanima_komut_yolla(0x201, [0x00, 0x00]) # Şarjı DURDUR (veya hiç başlatma)
        
        logging.info("❌ SONUÇ: Fiziksel şarj işlemi engellendi (Denial of Service).")
        
        # Sunucuya hala "Accepted" dönüyoruz ki sunucu şarjın başladığını ZANNETSİN (Confusion)
        return call_result.RemoteStartTransaction(status=RemoteStartStopStatus.accepted)

    @on('RemoteStopTransaction')
    async def on_remote_stop(self, transaction_id, **kwargs):
        logging.info(f"KOMUT ALINDI: Şarj Durdur (TxID: {transaction_id})")
        donanima_komut_yolla(0x201, [0x00, 0x00])
        return call_result.RemoteStopTransaction(status=RemoteStartStopStatus.accepted)

async def main():
    async with websockets.connect('ws://localhost:9000/CHARGER-MITM', subprotocols=['ocpp1.6']) as ws:
        logging.info("Sunucuya bağlanıldı.")
        client = MitmSaldiriChargePoint('CHARGER-MITM', ws)
        await asyncio.gather(client.start(), client.send_boot_notification())

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        if can_bus: can_bus.shutdown()
