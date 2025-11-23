import asyncio
import logging
from websockets.server import serve
from datetime import datetime, timezone

from ocpp.v16 import ChargePoint as cp, call, call_result
from ocpp.v16.enums import RegistrationStatus, RemoteStartStopStatus
from ocpp.routing import on

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [CSMS-SUNUCU] - %(message)s')

class SablonChargePoint(cp):
    
    def __init__(self, id, connection):
        super().__init__(id, connection)
        self.covert_bits = "" # Gizli bitleri biriktireceğimiz havuz
        self.decoded_message = "" # Çözülen mesaj

    @on('BootNotification')
    async def on_boot_notification(self, charge_point_model, charge_point_vendor, **kwargs):
        logging.info(f"YENİ CİHAZ BAĞLANDI: {charge_point_model} ({charge_point_vendor})")
        return call_result.BootNotification(
            current_time=datetime.now(timezone.utc).isoformat(),
            interval=10,
            status=RegistrationStatus.accepted
        )

    @on('Heartbeat')
    async def on_heartbeat(self, **kwargs):
        logging.info("Heartbeat alındı (Cihaz aktif).")
        return call_result.Heartbeat(
            current_time=datetime.now(timezone.utc).isoformat()
        )

    def bits_to_string(self, binary_string):
        """Toplanan 8 bitlik grupları ASCII karaktere çevirir."""
        message = ""
        # 8'erli gruplara böl
        for i in range(0, len(binary_string), 8):
            byte = binary_string[i:i+8]
            if len(byte) == 8:
                try:
                    char_code = int(byte, 2)
                    message += chr(char_code)
                except ValueError:
                    pass
        return message

    @on('MeterValues')
    async def on_meter_values(self, connector_id, meter_value, **kwargs):
        try:
            # Gelen verilerin listesi (Energy ve Voltage)
            samples = meter_value[0]['sampled_value']
            
            energy_val = None
            voltage_val = None

            # Listeyi tara ve ilgili değerleri çek
            for s in samples:
                # Birim (Unit) veya Measurand üzerinden ayırt edebiliriz
                if s.get('unit') == 'Wh' or s.get('measurand') == 'Energy.Active.Import.Register':
                    energy_val = s['value']
                elif s.get('unit') == 'V' or s.get('measurand') == 'Voltage':
                    voltage_val = s['value']

            # 1. Normal Operatör Ekranı (Sadece enerjiyi görür)
            if energy_val:
                logging.info(f"[NORMAL LOG] Enerji Tüketimi: {energy_val} Wh")

            # 2. SECVOLT ANOMALİ TESPİT SİSTEMİ (Arka planda çalışır)
            if voltage_val:
                voltage = float(voltage_val)
                
                # EŞİK DEĞER ANALİZİ (Threshold Analysis)
                # İstemci: 0 = 220.0V, 1 = 220.5V gönderiyor.
                # Biz eşik değerini tam ortası olan 220.25V belirleyelim.
                
                detected_bit = '?'
                if voltage > 220.25:
                    detected_bit = '1'
                    status = "YÜKSEK (Anomali)"
                else:
                    detected_bit = '0'
                    status = "NORMAL"

                self.covert_bits += detected_bit
                
                # Anlık Anomali Logu
                logging.warning(f"!!! ANOMALİ ANALİZİ !!! Voltaj: {voltage}V -> Tespit Edilen Bit: {detected_bit} ({status})")

                # Mesaj Çözme (Her 8 bit toplandığında bir harf oluşur)
                current_decoded = self.bits_to_string(self.covert_bits)
                if current_decoded != self.decoded_message:
                    self.decoded_message = current_decoded
                    logging.critical(f" >>> GİZLİ MESAJ ÇÖZÜLDÜ: {self.decoded_message} <<<")

        except Exception as e:
            logging.error(f"Veri işleme hatası: {e}")
        
        return call_result.MeterValues()

async def on_connect(websocket, path):
    try:
        charge_point_id = path.strip('/')
        logging.info(f"--- Bağlantı Kabul Edildi: {charge_point_id} ---")
        cp_instance = SablonChargePoint(charge_point_id, websocket)
        await cp_instance.start()
    except Exception as e:
        logging.error(f"Bağlantı hatası: {e}")

async def main():
    async with serve(on_connect, '0.0.0.0', 9000):
        logging.info("--- SECVOLT CSMS SUNUCUSU AKTİF (Port: 9000) ---")
        logging.info("--- Enerji Hattı Dinleniyor... ---")
        await asyncio.Future()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
