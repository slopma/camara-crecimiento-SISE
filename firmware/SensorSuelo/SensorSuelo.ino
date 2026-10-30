// Librerías
#include <ModbusRTU.h>

// Pines RS485 ESP32
#define RXD2 16
#define TXD2 17

// Configuración
#define BAUDRATE 4800
#define REG_SOIL_HUMIDITY 0x0000

// Variables
ModbusRTU mb;

uint16_t sensorData[7];

float humidity = 0;
float temperature = 0;
float conductivity = 0;
float ph = 0;
float nitrogen = 0;
float phosphorus = 0;
float potassium = 0;

// Sensor solicitado desde Serial
int currentSensor = 0;

// --------------------------------------------------
// Callback Modbus
// --------------------------------------------------
bool cbRead(Modbus::ResultCode event, uint16_t transactionId, void* data) {

  if (event == Modbus::EX_SUCCESS) {

    humidity     = sensorData[0] / 10.0;
    temperature  = sensorData[1] / 10.0;
    conductivity = sensorData[2];
    ph           = sensorData[3] / 10.0;
    nitrogen     = sensorData[4];
    phosphorus   = sensorData[5];
    potassium    = sensorData[6];

    Serial.println();
    Serial.println("==============================");
    Serial.printf("DATOS SENSOR S%d\n", currentSensor);
    Serial.println("==============================");

    Serial.printf("Humedad:      %.1f %%\n", humidity);
    Serial.printf("Temperatura:  %.1f °C\n", temperature);
    Serial.printf("Conductividad %.0f uS/cm\n", conductivity);
    Serial.printf("pH:           %.1f\n", ph);
    Serial.printf("Nitrogeno:    %.0f mg/kg\n", nitrogen);
    Serial.printf("Fosforo:      %.0f mg/kg\n", phosphorus);
    Serial.printf("Potasio:      %.0f mg/kg\n", potassium);

    Serial.println("==============================");
    Serial.println();

  } else {

    Serial.printf("Error leyendo S%d -> Codigo: 0x%02X\n",
                  currentSensor,
                  event);
  }

  return true;
}

// --------------------------------------------------
// Setup
// --------------------------------------------------
void setup() {

  Serial.begin(115200);

  Serial2.begin(BAUDRATE, SERIAL_8N1, RXD2, TXD2);

  mb.begin(&Serial2);
  mb.master();

  Serial.println("Sistema iniciado");
  Serial.println("Escribe S1, S2 ... S7");
}

// --------------------------------------------------
// Loop
// --------------------------------------------------
void loop() {

  // Mantener Modbus funcionando
  mb.task();

  // Leer comandos serial
  if (Serial.available()) {

    String cmd = Serial.readStringUntil('\n');

    cmd.trim();
    cmd.toUpperCase();

    // Verificar formato S1..S7
    if (cmd.startsWith("S")) {

      int sensorID = cmd.substring(1).toInt();

      if (sensorID >= 1 && sensorID <= 7) {

        // Verificar que no haya otra transacción activa
        if (!mb.slave()) {

          currentSensor = sensorID;

          bool started = mb.readHreg(
            sensorID,              // ID del sensor
            REG_SOIL_HUMIDITY,    // Registro inicial
            sensorData,           // Buffer
            7,                    // Número de registros
            cbRead                // Callback
          );

          if (started) {
            Serial.printf("Leyendo sensor S%d...\n", sensorID);
          } else {
            Serial.println("No se pudo iniciar lectura");
          }

        } else {

          Serial.println("Bus Modbus ocupado...");
        }

      } else {

        Serial.println("Sensor invalido. Usa S1..S7");
      }

    } else {

      Serial.println("Comando invalido");
    }
  }
}