import asyncio
import logging
import can
import websockets
from datetime import datetime, timezone

from ocpp.v16 import ChargePoint as cp, call, call_result
from ocpp.v16.enums import RegistrationStatus, RemoteStartStopStatus, ChargePointStatus, ChargePointErrorCode
from ocpp.routing import on

# Log formatı
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [SECVOLT-CLIENT] - %(message)s')

# --- DONANIM (vcan0) AYARI ---
try:
    # timeout=0.01 ekledik ki okuma işlemi sistemi bloklamasın
    can_bus = can.interface.Bus(channel='vcan0', interface='socketcan', receive_own_messages=True)
    logging.info("Donanım (vcan0) bağlantısı BAŞARILI. Fidye saldırısı için dinleniyor...")
except Exception:
    logging.warning("vcan0 bulunamadı! Simülasyon donanım olmadan çalışacak (Saldırı simüle edilemez).")
    can_bus = None

# --- SALDIRI PARAMETRELERİ ---
SALDIRI_CAN_ID = 0x1A0  # Senaryoda belirlediğimiz saldırganın kullandığı ID
FIDYE_NOTU = "SYSTEM HACKED. PAY 1 BTC TO UNLOCK."

def donanima_komut_yolla(can_id, data):
    if can_bus:
        try:
            msg = can.Message(arbitration_id=can_id, data=data, is_extended_id=False)
            can_bus.send(msg)
            logging.info(f"Donanıma İletildi -> ID: {hex(can_id)} Data: {data}")
        except Exception as e:
            logging.error(f"Donanım Hatası: {e}")

class SablonChargePoint(cp):
    def __init__(self, id, connection):
        super().__init__(id, connection)
        self.is_hacked = False  # Sistemin hacklenip hacklenmediğini tutan bayrak

    async def send_boot_notification(self):
        req = call.BootNotification(
            charge_point_vendor="SecVolt",
            charge_point_model="EVSE-X1"
        )
        res = await self.call(req)
        if res.status == RegistrationStatus.accepted:
            logging.info("Boot Notification kabul edildi. Sistem Hazır.")
            # Başlangıçta istasyonun durumu Available (Uygun)
            await self.send_status_notification(ChargePointStatus.available, ChargePointErrorCode.no_error)

    async def send_status_notification(self, status, error_code, info=None):
        """ Durum güncellemesi gönderen yardımcı fonksiyon """
        req = call.StatusNotification(
            connector_id=1,
            error_code=error_code,
            status=status,
            info=info
        )
        await self.call(req)

    async def monitor_can_traffic(self):
        """ 
        ANOMALİ TESPİT MODÜLÜ:
        Sürekli olarak CAN hattını dinler. Eğer saldırganın firmware güncelleme
        komutu (0x1A0) yakalanırsa, fidye senaryosunu başlatır.
        """
        logging.info("CAN Bus Dinleyici Aktif - Saldırı bekleniyor...")
        while True:
            if can_bus:
                # Bloklamadan mesaj oku
                msg = can_bus.recv(timeout=0.01)
                
                if msg and msg.arbitration_id == SALDIRI_CAN_ID:
                    # SALDIRI TESPİT EDİLDİ!
                    logging.critical(f"⚠️ KRİTİK UYARI: Yetkisiz Firmware Yükleme Girişimi Tespit Edildi! (ID: {hex(msg.arbitration_id)})")
                    await self.trigger_ransomware_mode()
            
            await asyncio.sleep(0.01) # CPU'yu yormamak için kısa bekleme

    async def trigger_ransomware_mode(self):
        """ Saldırı anında çalışacak fonksiyon """
        if not self.is_hacked:
            self.is_hacked = True
            logging.critical("🚨 SİSTEM KİLİTLENİYOR... FİDYE EKRANI AKTİF EDİLİYOR.")
            
            # Sunucuya HATA ve FİDYE NOTU gönder
            await self.send_status_notification(
                status=ChargePointStatus.faulted, 
                error_code=ChargePointErrorCode.other_error,
                info=FIDYE_NOTU
            )
            logging.info(f"Sunucuya Fidye Bildirimi Gönderildi: {FIDYE_NOTU}")

    async def send_meter_values(self):
        """ Düzenli enerji raporu """
        sayac = 0
        while True:
            if self.is_hacked:
                # Hacklendiyse veri göndermeyi durdur veya manipüle et
                logging.warning("Sistem kilitli olduğu için sayaç verisi gönderilmiyor.")
                await asyncio.sleep(5)
                continue

            sayac += 10
            payload = [{
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sampled_value": [{"value": str(sayac), "unit": "Wh"}]
            }]
            # Simülasyon için log basalım
            # logging.info(f"Sayaç okunuyor: {sayac} Wh")
            await asyncio.sleep(5)

    @on('RemoteStartTransaction')
    async def on_remote_start(self, id_tag, **kwargs):
        if self.is_hacked:
            logging.error("REDDEDİLDİ: Sistem fidye yazılımı nedeniyle kilitli!")
            return call_result.RemoteStartTransaction(status=RemoteStartStopStatus.rejected)

        logging.info(f"KOMUT ALINDI: Şarj Başlat (Kart: {id_tag})")
        donanima_komut_yolla(0x200, [0x01, 0x01])
        return call_result.RemoteStartTransaction(status=RemoteStartStopStatus.accepted)

    @on('RemoteStopTransaction')
    async def on_remote_stop(self, transaction_id, **kwargs):
        logging.info(f"KOMUT ALINDI: Şarj Durdur (TxID: {transaction_id})")
        donanima_komut_yolla(0x201, [0x00, 0x00])
        return call_result.RemoteStopTransaction(status=RemoteStartStopStatus.accepted)

async def main():
    async with websockets.connect('ws://localhost:9000/CHARGER-001', subprotocols=['ocpp1.6']) as ws:
        logging.info("OCPP Sunucusuna bağlanıldı.")
        client = SablonChargePoint('CHARGER-001', ws)
        
        # Monitor CAN Traffic fonksiyonunu da gather içine ekliyoruz
        await asyncio.gather(
            client.start(),
            client.send_boot_notification(),
            client.send_meter_values(),
            client.monitor_can_traffic()
        )

if __
