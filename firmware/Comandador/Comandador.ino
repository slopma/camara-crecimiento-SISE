// ======================================================
// SISTEMA INVERNADERO ESP32 COMPLETO CORREGIDO
// ======================================================

// ======================================================
// LIBRERIAS
// ======================================================

#include <DHT.h>
#include <Wire.h>
#include <DFRobot_LTR390UV.h>

// ======================================================
// DEFINICION DE PINES
// ======================================================

// DHT22
#define dhtPin1 4
#define dhtPin2 18

// SENSOR UV
#define SDA_PIN 21
#define SCL_PIN 22

// LDR
#define ldrPin1 32
#define ldrPin2 33

// SENSOR CO2
#define co2Pin 27

// ULTRASONIDO
#define trigPin 5
#define echoPin 34

// VENTILADORES
#define ventPin1 23
#define ventPin2 26

// BOMBA
#define bombaPin 19

// ALERTA
#define alertaPin 2

// LEDS PWM
#define led1 12
#define led2 13
#define led3 14
#define led4 15

// RESISTENCIA
#define resistenciaPin 25

// TIPO DHT
#define dhtType DHT22

// ======================================================
// CONFIGURACION PWM
// ======================================================

const int frecuenciaPWM = 5000;
const int resolucionPWM = 8;

// ======================================================
// CONSTANTES CO2
// ======================================================

#define preheatMsThreshold 80.00
#define validMaxMs 998.00
#define ppmMultiplier 5.0
#define msOffset 2.0

// ======================================================
// OBJETOS
// ======================================================

DFRobot_LTR390UV ltr390(
  LTR390UV_DEVICE_ADDR,
  &Wire
);

DHT dht1(dhtPin1, dhtType);
DHT dht2(dhtPin2, dhtType);

// ======================================================
// VARIABLES DHT22
// ======================================================

float temp1 = 0;
float hum1 = 0;

float temp2 = 0;
float hum2 = 0;

// ======================================================
// VARIABLES UV
// ======================================================

float luzUV = 0;
uint32_t uvRaw = 0;

// ======================================================
// VARIABLES LDR
// ======================================================

int luz1 = 0;
int luz2 = 0;

// ======================================================
// VARIABLES ULTRASONIDO
// ======================================================

long tiempoEco = 0;
float nivelTanque = 0;

// ======================================================
// VARIABLES CO2
// ======================================================

volatile unsigned long pwmHighStartTicks = 0;
volatile unsigned long pwmHighEndTicks = 0;

volatile unsigned long pwmHighVal = 0;

volatile uint8_t flagCO2 = 0;

float co2 = 0;

// ======================================================
// VARIABLES ACTUADORES
// ======================================================

int vent1 = 0;
int vent2 = 0;

int bombaON = 0;

int resistenciaON = 0;

// ======================================================
// FUNCION DHT22
// ======================================================
void leerDHT() {

  temp1 = dht1.readTemperature();
  hum1 = dht1.readHumidity();

  temp2 = dht2.readTemperature();
  hum2 = dht2.readHumidity();

  if (isnan(temp1) || isnan(hum1)) {
    Serial.println("Error DHT22 1");
  }

  if (isnan(temp2) || isnan(hum2)) {
    Serial.println("Error DHT22 2");
  }

  Serial.println("========== DHT22 ==========");

  Serial.print("Temp1: ");
  Serial.print(temp1);
  Serial.println(" C");

  Serial.print("Hum1: ");
  Serial.print(hum1);
  Serial.println(" %");

  Serial.print("Temp2: ");
  Serial.print(temp2);
  Serial.println(" C");

  Serial.print("Hum2: ");
  Serial.print(hum2);
  Serial.println(" %");
}

// ======================================================
// FUNCION UV
// ======================================================

void leerUV() {

  uvRaw = ltr390.readOriginalData();

  luzUV = uvRaw;

  Serial.println("====== UV ======");

  Serial.print("UV RAW: ");
  Serial.println(uvRaw);

  Serial.print("UV Aproximado: ");
  Serial.println(luzUV);
}

// ======================================================
// FUNCION LDR
// ======================================================

void leerLDR() {

  luz1 = analogRead(ldrPin1);
  luz2 = analogRead(ldrPin2);

  Serial.println("====== LDR ======");

  Serial.print("LDR1: ");
  Serial.println(luz1);

  Serial.print("LDR2: ");
  Serial.println(luz2);
}

// ======================================================
// FUNCION ULTRASONIDO
// ======================================================

void leerUltrasonido() {

  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);

  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);

  digitalWrite(trigPin, LOW);

  tiempoEco = pulseIn(echoPin, HIGH, 30000);

  nivelTanque = tiempoEco * 0.034 / 2;

  Serial.println("====== TANQUE ======");

  Serial.print("Nivel tanque: ");
  Serial.println(nivelTanque);
}

// ======================================================
// INTERRUPCION CO2
// ======================================================

void IRAM_ATTR pwmInterrupt() {

  if (digitalRead(co2Pin) == HIGH) {

    pwmHighStartTicks = micros();
  }

  else {

    pwmHighEndTicks = micros();

    pwmHighVal = pwmHighEndTicks - pwmHighStartTicks;

    flagCO2 = 1;
  }
}

// ======================================================
// FUNCION CO2
// ======================================================

void leerCO2() {

  if (flagCO2 == 1) {

    flagCO2 = 0;

    float pwmMs = pwmHighVal / 1000.0;

    if (pwmMs > preheatMsThreshold &&
        pwmMs < validMaxMs) {

      co2 = (pwmMs - msOffset) * ppmMultiplier;

      Serial.println("====== CO2 ======");

      Serial.print("CO2 ppm: ");
      Serial.println(co2);
    }

    else {

      Serial.println("Lectura CO2 invalida");
    }
  }

  else {

    Serial.println("CO2 aun no disponible");
  }
}

// ======================================================
// FUNCIONES LEDS
// ======================================================

void setBrilloLED(int pinLED, int brillo) {

  brillo = constrain(brillo, 0, 255);

  ledcWrite(pinLED, brillo);
}

void apagarTodosLEDs() {

  ledcWrite(led1, 0);
  ledcWrite(led2, 0);
  ledcWrite(led3, 0);
  ledcWrite(led4, 0);

  Serial.println("Todos los LEDs apagados");
}

// ======================================================
// FUNCIONES VENTILADORES
// ======================================================

void encenderVent1() {

  digitalWrite(ventPin1, HIGH);

  vent1 = 1;

  Serial.println("Ventilador 1 encendido");
}

void apagarVent1() {

  digitalWrite(ventPin1, LOW);

  vent1 = 0;

  Serial.println("Ventilador 1 apagado");
}

void encenderVent2() {

  digitalWrite(ventPin2, HIGH);

  vent2 = 1;

  Serial.println("Ventilador 2 encendido");
}

void apagarVent2() {

  digitalWrite(ventPin2, LOW);

  vent2 = 0;

  Serial.println("Ventilador 2 apagado");
}

// ======================================================
// FUNCIONES BOMBA
// ======================================================

void encenderBomba() {

  digitalWrite(bombaPin, LOW);

  bombaON = 1;

  Serial.println("Bomba encendida");
}

void apagarBomba() {

  digitalWrite(bombaPin, HIGH);

  bombaON = 0;

  Serial.println("Bomba apagada");
}

// ======================================================
// FUNCIONES RESISTENCIA
// ======================================================

void encenderResistencia() {

  digitalWrite(resistenciaPin, HIGH);

  resistenciaON = 1;

  Serial.println("Resistencia encendida");
}

void apagarResistencia() {

  digitalWrite(resistenciaPin, LOW);

  resistenciaON = 0;

  Serial.println("Resistencia apagada");
}

// ======================================================
// FUNCION SERIAL
// ======================================================

void procesarSerial() {

  if (!Serial.available()) {
    return;
  }

  String comando = Serial.readStringUntil('\n');

  comando.trim();

  if (comando.length() == 0) {
    return;
  }

  Serial.print("Comando recibido: ");
  Serial.println(comando);

  char datoSerial = comando.charAt(0);

  // DHT22
  if (datoSerial == 'D') {

    leerDHT();
  }

  // UV
  else if (datoSerial == 'U') {

    leerUV();
  }

  // LDR
  else if (datoSerial == 'L') {

    leerLDR();
  }

  // CO2
  else if (datoSerial == 'C') {

    leerCO2();
  }

  // TANQUE
  else if (datoSerial == 'T') {

    leerUltrasonido();
  }

  // LEDS PWM
  else if (datoSerial == 'S') {

    int coma = comando.indexOf(',');

    if (coma > 0) {

      char ledSeleccionado = comando.charAt(1);

      int brillo = comando.substring(coma + 1).toInt();

      brillo = constrain(brillo, 0, 255);

      switch (ledSeleccionado) {

        case '1':

          setBrilloLED(led1, brillo);

          Serial.print("LED 1 brillo: ");
          Serial.println(brillo);

          break;

        case '2':

          setBrilloLED(led2, brillo);

          Serial.print("LED 2 brillo: ");
          Serial.println(brillo);

          break;

        case '3':

          setBrilloLED(led3, brillo);

          Serial.print("LED 3 brillo: ");
          Serial.println(brillo);

          break;

        case '4':

          setBrilloLED(led4, brillo);

          Serial.print("LED 4 brillo: ");
          Serial.println(brillo);

          break;

        case '0':

          apagarTodosLEDs();

          break;
      }
    }
  }

  // VENTILADOR 1
  else if (datoSerial == 'A') {

    encenderVent1();
  }

  else if (datoSerial == 'a') {

    apagarVent1();
  }

  // VENTILADOR 2
  else if (datoSerial == 'B') {

    encenderVent2();
  }

  else if (datoSerial == 'b') {

    apagarVent2();
  }

  // BOMBA
  else if (datoSerial == 'M') {

    encenderBomba();
  }

  else if (datoSerial == 'm') {

    apagarBomba();
  }

  // RESISTENCIA
  else if (datoSerial == 'R') {

    encenderResistencia();
  }

  else if (datoSerial == 'r') {

    apagarResistencia();
  }

  else {

    Serial.println("Comando no reconocido");
  }
}

// ======================================================
// SETUP
// ======================================================

void setup() {

  Serial.begin(115200);

  // DHT
  dht1.begin();
  dht2.begin();

  // I2C
  Wire.begin(SDA_PIN, SCL_PIN);

  // UV
  while (ltr390.begin() != 0) {

    Serial.println("Sensor UV fallo");
    delay(1000);
  }

  Serial.println("Sensor UV iniciado");

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

  // PINES
  pinMode(ventPin1, OUTPUT);
  pinMode(ventPin2, OUTPUT);

  pinMode(bombaPin, OUTPUT);

  pinMode(alertaPin, OUTPUT);

  pinMode(resistenciaPin, OUTPUT);

  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);

  pinMode(co2Pin, INPUT);

  // PWM NUEVO ESP32 CORE 3.X
  ledcAttach(led1, frecuenciaPWM, resolucionPWM);
  ledcAttach(led2, frecuenciaPWM, resolucionPWM);
  ledcAttach(led3, frecuenciaPWM, resolucionPWM);
  ledcAttach(led4, frecuenciaPWM, resolucionPWM);

  apagarTodosLEDs();

  // INTERRUPCION CO2
  attachInterrupt(
    digitalPinToInterrupt(co2Pin),
    pwmInterrupt,
    CHANGE
  );

  Serial.println("Sistema iniciado correctamente");
}

// ======================================================
// LOOP
// ======================================================

void loop() {

  procesarSerial();
}