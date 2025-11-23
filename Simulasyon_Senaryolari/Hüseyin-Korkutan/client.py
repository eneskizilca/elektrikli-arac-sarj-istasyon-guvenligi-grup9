
import asyncio
import logging
import can
import websockets
from datetime import datetime, timezone
import random

from ocpp.v16 import ChargePoint as cp, call, call_result
from ocpp.v16.enums import RegistrationStatus, RemoteStartStopStatus, ReadingContext
from ocpp.routing import on

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [İSTEMCİ] - %(message)s')

# --- DONANIM (vcan0) AYARI ---
try:
    can_bus = can.interface.Bus(channel='vcan0', interface='socketcan')
    logging.info("Donanım (vcan0) bağlantısı BAŞARILI.")
except Exception:
    # Hata vermemesi için pass geçiyoruz, donanım yoksa simülasyon devam eder
    can_bus = None

def donanima_komut_yolla(can_id, data):
    if can_bus:
        try:
            msg = can.Message(arbitration_id=can_id, data=data, is_extended_id=False)
            can_bus.send(msg)
            logging.info(f"Donanıma İletildi -> ID: {hex(can_id)} Data: {data}")
        except Exception as e:
            logging.error(f"Donanım Hatası: {e}")

# --- ANOMALİ SENARYOSU EKLEME ---

class AnomaliChargePoint(cp):
    """
    Bu sınıf, normal OCPP 1.6 işlevselliğine ek olarak
    Kimlik Sahtekarlığı ve Yanlış Veri Enjeksiyonu
    saldırılarını simüle eden metodlar içerir.
    """
    
    def __init__(self, charge_point_id, websocket):
        super().__init__(charge_point_id, websocket)
        self.transaction_id = 0
        self.anomali_tetiklendi = False

    async def send_call(self, call):
        """
        OCPP mesaj gönderimini MitM (Ortadaki Adam) saldırısını simüle etmek için geçersiz kılıyoruz.
        Özellikle kritik StartTransaction.req komutuna yanlış veri enjekte edebiliriz.
        """
        
        # MitM: StartTransaction.req mesajına anormal bir sayaç değeri enjekte etme 
        # Gerçek bir MitM saldırganı trafiği yakalar ve mesajı değiştirir.
        if isinstance(call.payload, dict) and call.action == 'StartTransaction' and not self.anomali_tetiklendi:
            if random.random() < 0.3: # %30 ihtimalle MitM denemesi
                anormal_sayac_degeri = 9999999 
                call.payload['meterValue'] = anormal_sayac_degeri
                logging.warning(f"⚠️ ANOMALİ (MitM/YVE): StartTransaction.req'e ANORMAL Sayaç Değeri ({anormal_sayac_degeri}) ENJEKTE EDİLDİ! [cite: 8, 29]")
                self.anomali_tetiklendi = True # Tekrar tekrar tetiklenmesini önlemek için
        
        return await super().send_call(call)


    async def anomali_baslat_yetkisiz_islem(self, connector_id: int, unauthorized_id_tag: str):
        """
        ANOMALİ 1: Kimlik Sahtekarlığı ile Yetkisiz Şarj İşlemi Başlatma.
        
        Saldırgan, başka bir meşru kullanıcının ID'sini (unauthorized_id_tag) 
        kullanarak yetkisiz şarj işlemleri başlatır. 
        """
        self.transaction_id += 1
        
        logging.warning(f"🚨 ANOMALİ (KİMLİK SAHTEKARLIĞI): Bağlayıcı {connector_id} için Yetkisiz ID ({unauthorized_id_tag}) ile İşlem Başlatılıyor! ")
        
        request = call.StartTransaction(
            connector_id=connector_id,
            id_tag=unauthorized_id_tag,
            meter_start=150000, # Normalde yetkisiz bir başlangıç değeri
            timestamp=datetime.now(timezone.utc).isoformat(),
            reservation_id=None
        )

        response = await self.call(request)
        
        if response.id_tag_info['status'] == 'Accepted':
            logging.error(f"❌ KİMLİK SAHTEKARLIĞI BAŞARILI: Yetkisiz İşlem {response.transaction_id} BAŞLATILDI! (Finansal Kayıp Potansiyeli) [cite: 17]")
            # Başarılı olursa StopTransaction'ı simüle edebiliriz
            await self.anomali_gonder_yanlis_sayac_degeri(connector_id, response.transaction_id)
            await self.call(call.StopTransaction(
                transaction_id=response.transaction_id,
                meter_stop=150010,
                timestamp=datetime.now(timezone.utc).isoformat(),
                id_tag=unauthorized_id_tag
            ))
            logging.warning("Anormal İşlem Başlatıldı ve Durduruldu.")
        else:
            logging.info(f"✅ ANOMALİ ENGELLENDİ: Yetkisiz İşlem Başlatma Reddedildi. Durum: {response.id_tag_info['status']}")


    async def anomali_gonder_yanlis_sayac_degeri(self, connector_id: int, transaction_id: int):
        """
        ANOMALİ 2: Yanlış Veri Enjeksiyonu (YVE) Simülasyonu.
        
        Saldırgan, şarj işlemi sırasında sayaç okumalarını manipüle ederek 
        yanlış faturalandırma kayıtlarına yol açar. [cite: 16, 29]
        """
        yanlis_deger = 100000000 # Gerçekçi olmayan yüksek bir sayaç değeri
        
        logging.warning(f"⚠️ ANOMALİ (YVE): İşlem {transaction_id} için anormal sayaç değeri ({yanlis_deger} Wh) gönderiliyor! ")
        
        request = call.MeterValues(
            connector_id=connector_id,
            transaction_id=transaction_id,
            meter_value=[
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "sampledValue": [
                        {
                            "value": yanlis_deger,
                            "context": ReadingContext.Sampling_Periodic,
                            "unit": "Wh"
                        }
                    ]
                }
            ]
        )
        
        response = await self.call(request)
        logging.info(f"Yanlış MeterValues.req yanıtı alındı: {response}")


    # --- NORMAL OCPP 1.6 İŞLEVSELLİĞİ (DEĞİŞİKLİK YOK) ---
    @on('BootNotification')
    async def on_boot_notification(self, charge_point_vendor, charge_point_model, **kwargs):
        logging.info("BootNotification alındı.")
        return call_result.BootNotification(
            status=RegistrationStatus.Accepted,
            interval=300,
            current_time=datetime.now(timezone.utc).isoformat()
        )

    @on('RemoteStartTransaction')
    async def on_remote_start_transaction(self, id_tag, connector_id=1, **kwargs):
        logging.info(f"CSMS'den Uzaktan Başlatma Komutu alındı. ID: {id_tag}")
        
        # Gerçek bir şarj noktasında, burası bir CAN mesajı göndererek
        # donanımı (şarjı) başlatırdı.
        donanima_komut_yolla(0x100, [0x01, 0x01])
        
        # İşlemi başlattıktan sonra StartTransaction göndermeyi simüle ediyoruz
        # (Normalde donanım cevabına bağlıdır)
        await self.call(call.StartTransaction(
            connector_id=connector_id,
            id_tag=id_tag,
            meter_start=150000,
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))
        
        return call_result.RemoteStartTransaction(
            status=RemoteStartStopStatus.Accepted
        )

    # ... Diğer OCPP metodları buraya eklenebilir

async def main():
    csms_url = 'ws://127.0.0.1:9000/CPTest'
    charge_point_id = 'CPT-2024-001'
    
    try:
        # OCPP 1.6'nın güvenlik açıkları TLS 1.2'de bile oturum meta verilerini açığa çıkarır. [cite: 86]
        # Bu kod güvensiz websocket kullanıyor (ws://) ve MitM'e (ARP Sahtekarlığı) [cite: 4, 5] karşı savunmasız kalıyor.
        # Bu, uygulamanın MitM saldırılarına karşı korunmasız olduğunu simüle eder.
        async with websockets.connect(csms_url, subprotocols=['ocpp1.6']) as websocket:
            
            charge_point = AnomaliChargePoint(charge_point_id, websocket)
            logging.info(f"CSMS'ye bağlanıldı: {csms_url}. ID: {charge_point_id}")
            
            # BootNotification'ı gönder
            await charge_point.call(call.BootNotification(
                charge_point_model='AnomaliSim',
                charge_point_vendor='AnomalyTech'
            ))
            
            # --- ANOMALİ VURGUSU ---
            # Birkaç saniye sonra Kimlik Sahtekarlığı saldırısını tetikle
            await asyncio.sleep(5)
            # Yetkisiz bir ID kullanarak şarj işlemi başlatmaya çalış
            await charge_point.anomali_baslat_yetkisiz_islem(
                connector_id=1, 
                unauthorized_id_tag="ANOMALY-TAG-999"
            )
            
            # CSMS'den gelen komutları dinle
            await charge_point.start()

    except ConnectionRefusedError:
        logging.error(f"Bağlantı Reddedildi: CSMS ({csms_url}) çalışmıyor veya erişilebilir değil.")
    except websockets.exceptions.ConnectionClosed:
        logging.error("Bağlantı beklenmedik şekilde kapandı.")
    except Exception as e:
        logging.error(f"Genel Hata: {e}")

if __name__ == '__main__':
    # Kodun başlatılması
    asyncio.run(main())
