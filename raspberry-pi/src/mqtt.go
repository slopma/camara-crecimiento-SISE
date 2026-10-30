package main

import (
	"encoding/json"
	"os"
	"strings"
	"time"

	mqtt "github.com/eclipse/paho.mqtt.golang"
	"github.com/eggseal/camara-crecimiento/raspberry-pi/src/db"
	"github.com/eggseal/camara-crecimiento/raspberry-pi/src/queue"
	"github.com/rs/zerolog/log"
)

func getEnv(key, defaultVal string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultVal
}

func getTopicPrefix() string {
	return getEnv("MQTT_TOPIC_PREFIX", "/sise/camara-crecimiento/m1")
}

func BuildTopic(path string) string {
	return getTopicPrefix() + path
}

func Publish(client mqtt.Client, topic string, payload string) error {
	if client == nil {
		return nil
	}

	token := client.Publish(topic, 0, false, payload)
	token.Wait()

	return token.Error()
}

func HandleSetpointSubscribe(subStore *db.Store) func(mqtt.Client, mqtt.Message) {
	return func(client mqtt.Client, msg mqtt.Message) {
		var incoming map[string]any
		err := json.Unmarshal(msg.Payload(), &incoming)
		if err != nil {
			log.Warn().Err(err).Msg("Failed to unmarshal setpoints payload")
			return
		}

		subStore.Apply(incoming)
	}
}

func HandleExperimentStart(subStore *db.Store) func(mqtt.Client, mqtt.Message) {
	return func(client mqtt.Client, msg mqtt.Message) {
		experimentName := strings.TrimSpace(string(msg.Payload()))
		if experimentName == "" {
			return
		}

		expData := map[string]any{
			"running":         1,
			"experiment_name": experimentName,
		}

		subStore.Apply(expData)
		running.Store(true)
		log.Info().Str("experiment", experimentName).Msg("Experiment started")
	}
}

func StartMqttClient(pubQueue *queue.Queue, subStore *db.Store) error {
	broker := getEnv("MQTT_BROKER", "tcp://mqtt.dis.eafit.edu.co:1883")
	clientID := getEnv("MQTT_CLIENT_ID", "sise-camara-crecimiento-modulo1")
	user := getEnv("MQTT_USER", "admin")
	pass := getEnv("MQTT_PASSWORD", "semillero")

	opt := mqtt.NewClientOptions().
		AddBroker(broker).
		SetClientID(clientID).
		SetUsername(user).
		SetPassword(pass).
		SetConnectTimeout(5 * time.Second).
		SetKeepAlive(10 * time.Second).
		SetPingTimeout(3 * time.Second).
		SetAutoReconnect(false)

	log.Info().Str("broker", broker).Str("clientID", clientID).Msg("Connecting to MQTT broker")
	client := mqtt.NewClient(opt)
	token := client.Connect()
	token.Wait()
	err := token.Error()
	if err != nil {
		return err
	}
	log.Info().Msg("Connected to MQTT broker")

	callback := HandleSetpointSubscribe(subStore)
	token = client.Subscribe(BuildTopic("/sp"), 0, callback)
	token.Wait()
	err = token.Error()
	if err != nil {
		return err
	}

	callback = HandleExperimentStart(subStore)
	token = client.Subscribe(BuildTopic("/start"), 0, callback)
	token.Wait()
	err = token.Error()
	if err != nil {
		return err
	}

	token = client.Subscribe(BuildTopic("/stop"), 0, func(c mqtt.Client, m mqtt.Message) {
		running.Store(false)
		subStore.Apply(map[string]any{"running": 0})
		log.Info().Msg("Experiment stopped")
	})
	token.Wait()
	err = token.Error()
	if err != nil {
		return err
	}

	defer client.Disconnect(250)

	for {
		payload, ok := pubQueue.Peek()
		if !ok {
			time.Sleep(time.Second)
			continue
		}

		log.Info().Str("json", payload).Msg("Uploading telemetry")
		err := Publish(client, BuildTopic("/data"), payload)
		if err != nil {
			return err
		}

		err = pubQueue.Ack()
		if err != nil {
			return err
		}
	}
}

func MqttLoop(pubQueue *queue.Queue, subStore *db.Store) {
	for {
		err := StartMqttClient(pubQueue, subStore)
		if err != nil {
			log.Error().Err(err).Msg("MQTT client failed")
			time.Sleep(2 * time.Second)
		}
	}
}

