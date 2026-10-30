#include <ArduinoJson.h>

JsonDocument input;
JsonDocument data;

// =========================
// Global setpoints
// =========================

int ledr = 0;
int ledg = 0;
int ledb = 0;
int leduv = 0;

float temp_min = 0;
float temp_max = 0;

float hum_min = 0;
float hum_max = 0;

float hum_suelo_min = 0;
float hum_suelo_max = 0;

float luz_uv_min = 0;
float luz_uv_max = 0;

bool start = false;

void setup()
{
    Serial.begin(115200);
    randomSeed(analogRead(0));
    pinMode(2, OUTPUT);
}

void handleMessage()
{
    if (!Serial.available())
        return;

    DeserializationError error =
        deserializeJson(input, Serial.readStringUntil('\n'));

    Serial.flush();

    if (error)
    {
        Serial.println(error.c_str());
        return;
    }

    switch ((uint8_t)input["cmd"])
    {
    case 1:
        start = true;

        // =========================
        // Read incoming setpoints
        // =========================

        if (input["ledr"].is<int>())
            ledr = input["ledr"];

        if (input["ledg"].is<int>())
            ledg = input["ledg"];

        if (input["ledb"].is<int>())
            ledb = input["ledb"];

        if (input["leduv"].is<int>())
            leduv = input["leduv"];

        if (input["temp_min"].is<float>() || input["temp_min"].is<int>())
            temp_min = input["temp_min"];

        if (input["temp_max"].is<float>() || input["temp_max"].is<int>())
            temp_max = input["temp_max"];

        if (input["hum_min"].is<float>() || input["hum_min"].is<int>())
            hum_min = input["hum_min"];

        if (input["hum_max"].is<float>() || input["hum_max"].is<int>())
            hum_max = input["hum_max"];

        if (input["hum_suelo_min"].is<float>() || input["hum_suelo_min"].is<int>())
            hum_suelo_min = input["hum_suelo_min"];

        if (input["hum_suelo_max"].is<float>() || input["hum_suelo_max"].is<int>())
            hum_suelo_max = input["hum_suelo_max"];

        if (input["luz_uv_min"].is<float>() || input["luz_uv_min"].is<int>())
            luz_uv_min = input["luz_uv_min"];

        if (input["luz_uv_max"].is<float>() || input["luz_uv_max"].is<int>())
            luz_uv_max = input["luz_uv_max"];

        // =========================
        // Random sensor data
        // =========================

        data["temp1"] = random(20, 40);
        data["hum1"] = random(20, 80);

        data["temp2"] = random(20, 40);
        data["hum2"] = random(20, 80);

        data["co2"] = random(300, 2000);

        // Soil 1
        data["hum_suelo1"] = random(20, 90);
        data["temp_suelo1"] = random(15, 35);
        data["ec_suelo1"] = random(10, 300) / 10.0;
        data["ph_suelo1"] = random(50, 80) / 10.0;
        data["n_suelo1"] = random(0, 1000);
        data["p_suelo_1"] = random(0, 1000);
        data["k_suelo1"] = random(0, 1000);

        // Soil 2
        data["hum_suelo2"] = random(20, 90);
        data["temp_suelo2"] = random(15, 35);
        data["ec_suelo2"] = random(10, 300) / 10.0;
        data["ph_suelo2"] = random(50, 80) / 10.0;
        data["n_suelo2"] = random(0, 1000);
        data["p_suelo_2"] = random(0, 1000);
        data["k_suelo2"] = random(0, 1000);

        // Soil 3
        data["hum_suelo3"] = random(20, 90);
        data["temp_suelo3"] = random(15, 35);
        data["ec_suelo3"] = random(10, 300) / 10.0;
        data["ph_suelo3"] = random(50, 80) / 10.0;
        data["n_suelo3"] = random(0, 1000);
        data["p_suelo_3"] = random(0, 1000);
        data["k_suelo3"] = random(0, 1000);

        // Soil 4
        data["hum_suelo4"] = random(20, 90);
        data["temp_suelo4"] = random(15, 35);
        data["ec_suelo4"] = random(10, 300) / 10.0;
        data["ph_suelo4"] = random(50, 80) / 10.0;
        data["n_suelo4"] = random(0, 1000);
        data["p_suelo_4"] = random(0, 1000);
        data["k_suelo4"] = random(0, 1000);

        // Soil 5
        data["hum_suelo5"] = random(20, 90);
        data["temp_suelo5"] = random(15, 35);
        data["ec_suelo5"] = random(10, 300) / 10.0;
        data["ph_suelo5"] = random(50, 80) / 10.0;
        data["n_suelo5"] = random(0, 1000);
        data["p_suelo_5"] = random(0, 1000);
        data["k_suelo5"] = random(0, 1000);

        // Soil 6
        data["hum_suelo6"] = random(20, 90);
        data["temp_suelo6"] = random(15, 35);
        data["ec_suelo6"] = random(10, 300) / 10.0;
        data["ph_suelo6"] = random(50, 80) / 10.0;
        data["n_suelo6"] = random(0, 1000);
        data["p_suelo_6"] = random(0, 1000);
        data["k_suelo6"] = random(0, 1000);

        // Light / water
        data["luz_ir"] = random(0, 10000);
        data["luz_uv"] = random(0, 10000);

        data["ph"] = random(50, 80) / 10.0;
        data["ec"] = random(10, 300) / 10.0;

        data["luz1"] = random(0, 10000);
        data["luz2"] = random(0, 10000);

        // Actuators
        data["bomba"] = random(0, 2);
        data["humidificador"] = random(0, 2);
        data["vent1"] = random(0, 2);
        data["vent2"] = random(0, 2);
        data["calor"] = random(0, 2);

        // Tank
        data["nivel_tanque"] = random(0, 101);
        data["estado_tanque"] = random(0, 2);

        serializeJson(data, Serial);
        Serial.println();

        break;
    case 2:
        start = false;

        data["ok"] = 1;
        serializeJson(data, Serial);
        Serial.println();

        break;
    default:
        data["ok"] = 0;
        serializeJson(data, Serial);
        Serial.println();
    }

    input.clear();
    data.clear();
}

void loop()
{
    digitalWrite(2, start);
    handleMessage();
}