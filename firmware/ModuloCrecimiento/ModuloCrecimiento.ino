// ======================================================
// CAMARA DE CRECIMIENTO - ESP32 INTEGRADO
// Sensores + Actuadores + Modbus 7en1 x6 + JSON Raspberry
// ======================================================

// ======================================================
// LIBRERIAS
// ======================================================

#include <DHT.h>
#include <Wire.h>
#include <DFRobot_LTR390UV.h>
#include <ModbusRTU.h>
#include <ArduinoJson.h>

// ======================================================
// PINES
// ======================================================

// DHT22
#define dhtPin1     4
#define dhtPin2     18

// I2C (UV)
#define SDA_PIN     21
#define SCL_PIN     22

// LDR
#define ldrPin1     32
#define ldrPin2     33

// CO2 (PWM)
#define co2Pin      27

// ULTRASONIDO
#define trigPin     5
#define echoPin     34

// VENTILADORES
#define ventPin1    23
#define ventPin2    26

// BOMBA
#define bombaPin    19

// ALERTA
#define alertaPin   2

// LEDS PWM
#define led1        12
#define led2        13
#define led3        14
#define led4        15

// RESISTENCIA
#define resistenciaPin 25

// RS485 Modbus (Serial2)
#define RXD2        16
#define TXD2        17

// ======================================================
// CONFIGURACION
// ======================================================

#define dhtType         DHT22
#define MODBUS_BAUDRATE 4800
#define REG_INICIO      0x0000
#define NUM_REGISTROS   7
#define NUM_SENSORES    6   // S1..S6 = suelo | S7 = tanque/bomba

// PWM
const int frecuenciaPWM = 5000;
const int resolucionPWM = 8;

// CO2
#define preheatMsThreshold  80.00
#define validMaxMs          998.00
#define ppmMultiplier       5.0
#define msOffset            2.0

// ======================================================
// OBJETOS
// ======================================================

DHT dht1(dhtPin1, dhtType);
DHT dht2(dhtPin2, dhtType);

DFRobot_LTR390UV ltr390(LTR390UV_DEVICE_ADDR, &Wire);

ModbusRTU mb;

JsonDocument inputDoc;
JsonDocument outputDoc;

// ======================================================
// VARIABLES - SENSORES AMBIENTE
// ======================================================

float temp1   = 0;
float hum1    = 0;
float temp2   = 0;
float hum2    = 0;

float luzUV   = 0;
uint32_t uvRaw = 0;

int luz1 = 0;
int luz2 = 0;

float co2 = 0;
volatile unsigned long pwmHighStartTicks = 0;
volatile unsigned long pwmHighEndTicks   = 0;
volatile unsigned long pwmHighVal        = 0;
volatile uint8_t flagCO2                 = 0;

float nivelTanque = 0;
long  tiempoEco   = 0;

// ======================================================
// VARIABLES - SENSORES SUELO (S1..S6) Y TANQUE (S7)
// ======================================================

struct DatosSuelo {
  float humedad;
  float temperatura;
  float conductividad;
  float ph;
  float nitrogeno;
  float fosforo;
  float potasio;
};

DatosSuelo suelo[8];   // suelo[0] sin uso | suelo[1..6] plantas | suelo[7] = tanque

uint16_t modbusBuffer[NUM_REGISTROS];
int sensorActual   = 1;   // sensor Modbus que se está leyendo ahora
bool modbusLeyendo = false;
bool uvDisponible = false;

// ======================================================
// VARIABLES - ACTUADORES
// ======================================================

int estadoVent1       = 0;
int estadoVent2       = 0;
int estadoBomba       = 0;
int estadoResistencia = 0;

// ======================================================
// VARIABLES - SETPOINTS (recibidos desde Raspberry)
// ======================================================

int   ledr          = 0;
int   ledg          = 0;
int   ledb          = 0;
int   leduv         = 0;

float temp_min      = 0;
float temp_max      = 0;

float hum_min       = 0;
float hum_max       = 0;

float hum_suelo_min = 0;
float hum_suelo_max = 0;

float luz_uv_min    = 0;
float luz_uv_max    = 0;

bool sistemaActivo  = false;

// ======================================================
// INTERRUPCION CO2
// ======================================================

void IRAM_ATTR pwmInterrupt() {
  if (digitalRead(co2Pin) == HIGH) {
    pwmHighStartTicks = micros();
  } else {
    pwmHighEndTicks = micros();
    pwmHighVal      = pwmHighEndTicks - pwmHighStartTicks;
    flagCO2         = 1;
  }
}

// ======================================================
// LECTURA SENSORES AMBIENTE
// ======================================================

void leerDHT() {
  temp1 = dht1.readTemperature();
  hum1  = dht1.readHumidity();
  temp2 = dht2.readTemperature();
  hum2  = dht2.readHumidity();

  if (isnan(temp1) || isnan(hum1)) { temp1 = 0; hum1 = 0; }
  if (isnan(temp2) || isnan(hum2)) { temp2 = 0; hum2 = 0; }
}

void leerUV() {

  if (!uvDisponible) {
    luzUV = 0;
    return;
  }

  uint32_t lectura = ltr390.readOriginalData();

  // Lectura inválida/corrupta
  if (lectura > 1000000) {
    return;
  }

  uvRaw = lectura;
  luzUV = (float)uvRaw;
}

void leerLDR() {
  luz1 = analogRead(ldrPin1);
  luz2 = analogRead(ldrPin2);
}

void leerCO2() {
  if (flagCO2 == 1) {
    flagCO2 = 0;
    float pwmMs = pwmHighVal / 1000.0;
    if (pwmMs > preheatMsThreshold && pwmMs < validMaxMs) {
      co2 = (pwmMs - msOffset) * ppmMultiplier;
    }
  }
}

void leerUltrasonido() {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  tiempoEco  = pulseIn(echoPin, HIGH, 30000);
  nivelTanque = tiempoEco * 0.034 / 2.0;
}

// ======================================================
// MODBUS - CALLBACK
// ======================================================

bool onModbusRead(Modbus::ResultCode event, uint16_t transactionId, void* data) {
  modbusLeyendo = false;

  if (event == Modbus::EX_SUCCESS) {
    int idx = sensorActual;               // 1..6 = suelo | 7 = tanque
    suelo[idx].humedad      = modbusBuffer[0] / 10.0;
    suelo[idx].temperatura  = modbusBuffer[1] / 10.0;
    suelo[idx].conductividad = modbusBuffer[2];
    suelo[idx].ph           = modbusBuffer[3] / 10.0;
    suelo[idx].nitrogeno    = modbusBuffer[4];
    suelo[idx].fosforo      = modbusBuffer[5];
    suelo[idx].potasio      = modbusBuffer[6];
  }
  // Si falla, se conservan los últimos valores válidos

  return true;
}

// ======================================================
// MODBUS - CICLO ROUND-ROBIN (no bloqueante)
// Recorre S1..S7 de a uno por ciclo
// ======================================================

void tareaModbus() {
  mb.task();   // Siempre llamar para mantener el bus activo

  if (modbusLeyendo) return;   // Esperar que termine la lectura actual
  if (mb.slave())    return;   // Bus ocupado

  // Iniciar lectura del sensor actual
  bool ok = mb.readHreg(
    sensorActual,
    REG_INICIO,
    modbusBuffer,
    NUM_REGISTROS,
    onModbusRead
  );

  if (ok) {
    modbusLeyendo = true;
  }

  // Avanzar al siguiente sensor (1..7 round-robin)
  sensorActual++;
  if (sensorActual > 7) sensorActual = 1;
}

// ======================================================
// ACTUADORES - FUNCIONES BASE
// ======================================================

void setVent1(bool on) {
  digitalWrite(ventPin1, on ? HIGH : LOW);
  estadoVent1 = on ? 1 : 0;
}

void setVent2(bool on) {
  digitalWrite(ventPin2, on ? HIGH : LOW);
  estadoVent2 = on ? 1 : 0;
}

void setBomba(bool on) {
  // Bomba activa en LOW (relé normalmente cerrado)
  digitalWrite(bombaPin, on ? LOW : HIGH);
  estadoBomba = on ? 1 : 0;
}

void setResistencia(bool on) {
  digitalWrite(resistenciaPin, on ? HIGH : LOW);
  estadoResistencia = on ? 1 : 0;
}

void setLEDs(int r, int g, int b, int uv) {
  ledcWrite(led1, constrain(r,  0, 255));
  ledcWrite(led2, constrain(g,  0, 255));
  ledcWrite(led3, constrain(b,  0, 255));
  ledcWrite(led4, constrain(uv, 0, 255));
}

// ======================================================
// CONTROL AUTOMATICO
// Compara lecturas con setpoints y actúa
// ======================================================

void aplicarControl() {
  if (!sistemaActivo) return;

  // --- Temperatura (promedio de ambos DHT22) ---
  float tempProm = (temp1 + temp2) / 2.0;

  if (tempProm > temp_max) {
    setVent1(true);
    setVent2(true);
    setResistencia(false);
  } else if (tempProm < temp_min) {
    setResistencia(true);
    setVent1(false);
    setVent2(false);
  } else {
    // Temperatura dentro de rango
    // Solo apagar resistencia si estaba encendida
    if (estadoResistencia) setResistencia(false);
  }

  // --- Humedad aire (promedio de ambos DHT22) ---
  float humProm = (hum1 + hum2) / 2.0;

  if (humProm < hum_min || humProm > hum_max) {
    // Ventilar para corregir humedad (fuera de rango en cualquier dirección)
    setVent1(true);
    setVent2(true);
  }
  // Nota: si la temperatura ya encendió los ventiladores, esto no los apaga

  // --- Humedad suelo (promedio de los 6 sensores de planta S1..S6) ---
  float sumHumSuelo = 0;
  for (int i = 1; i <= NUM_SENSORES; i++) {
    sumHumSuelo += suelo[i].humedad;
  }
  float humSueloProm = sumHumSuelo / NUM_SENSORES;

  if (humSueloProm < hum_suelo_min) {
    setBomba(true);
  } else if (humSueloProm >= hum_suelo_max) {
    setBomba(false);
  }

  // --- LEDs: valores fijos enviados por la Raspberry ---
  setLEDs(ledr, ledg, ledb, leduv);
}

// ======================================================
// JSON - CONSTRUIR RESPUESTA CON DATOS REALES
// ======================================================

void construirRespuesta() {
  outputDoc.clear();

  // Ambiente
  outputDoc["temp1"] = temp1;
  outputDoc["hum1"]  = hum1;
  outputDoc["temp2"] = temp2;
  outputDoc["hum2"]  = hum2;
  outputDoc["co2"]   = co2;

  // Luz
  outputDoc["luz_uv"] = luzUV;
  outputDoc["luz1"]   = luz1;
  outputDoc["luz2"]   = luz2;

  // Suelo S1..S6 (plantas)
  for (int i = 1; i <= NUM_SENSORES; i++) {
    String base = "suelo" + String(i);
    outputDoc["hum_"  + base] = suelo[i].humedad;
    outputDoc["temp_" + base] = suelo[i].temperatura;
    outputDoc["ec_"   + base] = suelo[i].conductividad;
    outputDoc["ph_"   + base] = suelo[i].ph;
    outputDoc["n_"    + base] = suelo[i].nitrogeno;
    outputDoc["p_"    + base] = suelo[i].fosforo;
    outputDoc["k_"    + base] = suelo[i].potasio;
  }

  // Tanque / bomba (S7) — sin humedad, siempre 100%
  outputDoc["ph_tanque"] = suelo[7].ph;
  outputDoc["ec_tanque"] = suelo[7].conductividad;
  outputDoc["n_tanque"]  = suelo[7].nitrogeno;
  outputDoc["p_tanque"]  = suelo[7].fosforo;
  outputDoc["k_tanque"]  = suelo[7].potasio;

  // Nivel tanque (ultrasonido)
  outputDoc["nivel_tanque"] = nivelTanque;

  // Estado actuadores (refleja estado real de los pines)
  outputDoc["vent1"]      = estadoVent1;
  outputDoc["vent2"]      = estadoVent2;
  outputDoc["bomba"]      = estadoBomba;
  outputDoc["calor"]      = estadoResistencia;

  serializeJson(outputDoc, Serial);
  Serial.println();
}

// ======================================================
// JSON - PROCESAR MENSAJE ENTRANTE DESDE RASPBERRY
// ======================================================

void procesarMensaje() {

  if (!Serial.available()) {
    return;
  }

  String raw = Serial.readStringUntil('\n');

  raw.trim();

  // Ignorar basura serial
  if (!raw.startsWith("{")) {
    return;
  }

  inputDoc.clear();

  DeserializationError error =
    deserializeJson(inputDoc, raw);

  if (error) {
    return;
  }

  uint8_t cmd = (uint8_t)inputDoc["cmd"];

  switch (cmd) {

    // =========================
    // CMD 1
    // =========================
    case 1:

      sistemaActivo = true;

      if (inputDoc["ledr"].is<int>())
        ledr = inputDoc["ledr"];

      if (inputDoc["ledg"].is<int>())
        ledg = inputDoc["ledg"];

      if (inputDoc["ledb"].is<int>())
        ledb = inputDoc["ledb"];

      if (inputDoc["leduv"].is<int>())
        leduv = inputDoc["leduv"];

      if (inputDoc["temp_min"].is<float>() || inputDoc["temp_min"].is<int>())
        temp_min = inputDoc["temp_min"];

      if (inputDoc["temp_max"].is<float>() || inputDoc["temp_max"].is<int>())
        temp_max = inputDoc["temp_max"];

      if (inputDoc["hum_min"].is<float>() || inputDoc["hum_min"].is<int>())
        hum_min = inputDoc["hum_min"];

      if (inputDoc["hum_max"].is<float>() || inputDoc["hum_max"].is<int>())
        hum_max = inputDoc["hum_max"];

      if (inputDoc["hum_suelo_min"].is<float>() || inputDoc["hum_suelo_min"].is<int>())
        hum_suelo_min = inputDoc["hum_suelo_min"];

      if (inputDoc["hum_suelo_max"].is<float>() || inputDoc["hum_suelo_max"].is<int>())
        hum_suelo_max = inputDoc["hum_suelo_max"];

      if (inputDoc["luz_uv_min"].is<float>() || inputDoc["luz_uv_min"].is<int>())
        luz_uv_min = inputDoc["luz_uv_min"];

      if (inputDoc["luz_uv_max"].is<float>() || inputDoc["luz_uv_max"].is<int>())
        luz_uv_max = inputDoc["luz_uv_max"];

      leerDHT();
      leerUV();
      leerLDR();
      leerCO2();
      leerUltrasonido();

      aplicarControl();

      construirRespuesta();

      break;

    // =========================
    // CMD 2
    // =========================
    case 2:

      sistemaActivo = false;

      setVent1(false);
      setVent2(false);
      setBomba(false);
      setResistencia(false);

      setLEDs(0, 0, 0, 0);

      outputDoc.clear();

      outputDoc["ok"] = 1;

      serializeJson(outputDoc, Serial);

      Serial.println();

      break;

    // =========================
    // DEFAULT
    // =========================
    default:

      outputDoc.clear();

      outputDoc["ok"] = 0;

      serializeJson(outputDoc, Serial);

      Serial.println();

      break;
  }

  inputDoc.clear();
  outputDoc.clear();
}

// ======================================================
// SETUP
// ======================================================

void setup() {

  // Serial principal (Raspberry)
  Serial.begin(115200);

  // DHT
  dht1.begin();
  dht2.begin();

  // I2C + UV
Wire.begin(SDA_PIN, SCL_PIN);
Wire.setTimeOut(50);

if (ltr390.begin()) {

  uvDisponible = true;

  ltr390.setALSOrUVSMeasRate(
    ltr390.e18bit,
    ltr390.e100ms
  );

  ltr390.setALSOrUVSGain(
    ltr390.eGain3
  );

  ltr390.setMode(
    ltr390.eUVSMode
  );
}
  // Si el UV falla, continúa sin bloquearse (luzUV quedará en 0)

  // Modbus RS485
  Serial2.begin(MODBUS_BAUDRATE, SERIAL_8N1, RXD2, TXD2);
  mb.begin(&Serial2);
  mb.master();

  // Pines digitales
  pinMode(ventPin1,      OUTPUT);
  pinMode(ventPin2,      OUTPUT);
  pinMode(bombaPin,      OUTPUT);
  pinMode(alertaPin,     OUTPUT);
  pinMode(resistenciaPin,OUTPUT);
  pinMode(trigPin,       OUTPUT);
  pinMode(echoPin,       INPUT);
  pinMode(co2Pin,        INPUT);

  // Estado inicial seguro
  setVent1(false);
  setVent2(false);
  setBomba(false);
  setResistencia(false);

  // PWM LEDs
  ledcAttach(led1, frecuenciaPWM, resolucionPWM);
  ledcAttach(led2, frecuenciaPWM, resolucionPWM);
  ledcAttach(led3, frecuenciaPWM, resolucionPWM);
  ledcAttach(led4, frecuenciaPWM, resolucionPWM);
  setLEDs(0, 0, 0, 0);

  // Interrupción CO2
  attachInterrupt(digitalPinToInterrupt(co2Pin), pwmInterrupt, CHANGE);

  // Inicializar struct suelo en cero
  for (int i = 0; i <= 7; i++) {
    suelo[i] = {0, 0, 0, 0, 0, 0, 0};
  }
}

// ======================================================
// LOOP
// ======================================================

void loop() {
  // Mantener Modbus corriendo (round-robin no bloqueante)
  tareaModbus();

  // LED de estado del sistema
  digitalWrite(alertaPin, sistemaActivo ? HIGH : LOW);

  // Procesar mensajes JSON desde Raspberry
  procesarMensaje();
}