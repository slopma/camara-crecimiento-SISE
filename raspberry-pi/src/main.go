package main

import (
	"encoding/json"
	"maps"
	"os"
	"sync/atomic"
	"time"

	"github.com/eggseal/camara-crecimiento/raspberry-pi/src/db"
	"github.com/eggseal/camara-crecimiento/raspberry-pi/src/queue"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
)

var running atomic.Bool

func main() {
	log.Logger = log.Output(zerolog.ConsoleWriter{Out: os.Stdout})
	log.Info().Msg("Program started.")

	data := make(chan string, 0x1F)

	subStore, err := db.New("/data/substore.json")
	if err != nil {
		log.Fatal().Err(err).Msg("DB init failed")
	} else {
		log.Info().Msg("Loaded subscription store.")
	}

	pubQueue, err := queue.New("/data/pubstore.json")
	if err != nil {
		log.Fatal().Err(err).Msg("DB init failed")
	} else {
		log.Info().Msg("Loaded publish queue.")
	}

	go func() {
		db.PeriodicSave(subStore, 10*time.Second)
	}()

	go func() {
		SerialLoop(data, subStore)
	}()

	go func() {
		MqttLoop(pubQueue, subStore)
	}()

	go func() {
		TimeLoop()
	}()

	for line := range data {
		var tmp map[string]any
		if err := json.Unmarshal([]byte(line), &tmp); err != nil {
			continue
		}

		timeNow := GetInternetTime()
		tmp["timestamp"] = timeNow.UnixMilli()
		if running.Load() {
			tmp["running"] = 1
		} else {
			tmp["running"] = 0
		}
		maps.Copy(tmp, subStore.Snapshot())

		timedLine, err := json.Marshal(tmp)
		if err != nil {
			continue
		}

		err = pubQueue.Push(string(timedLine))
		if err != nil {
			log.Error().Err(err).Msg("Failed to queue payload")
		}
	}
}

