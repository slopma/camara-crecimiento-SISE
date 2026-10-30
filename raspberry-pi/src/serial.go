package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/eggseal/camara-crecimiento/raspberry-pi/src/db"
	"github.com/rs/zerolog/log"
	"go.bug.st/serial"
)

const (
	readTimeout  = 8 * time.Second
	tickInterval = 3 * time.Second
)

func readLine(port serial.Port, timeout time.Duration) (string, error) {

	buf := make([]byte, 0, 512)
	tmp := make([]byte, 1)

	deadline := time.Now().Add(timeout)

	for {

		if time.Now().After(deadline) {
			return "", fmt.Errorf("serial read timeout")
		}

		n, err := port.Read(tmp)

		if err != nil {
			return "", err
		}

		if n == 0 {
			time.Sleep(5 * time.Millisecond)
			continue
		}

		c := tmp[0]

		if c == '\n' {
			return strings.TrimSpace(string(buf)), nil
		}

		buf = append(buf, c)
	}
}

func StartSerialHandler(
	data chan<- string,
	subStore *db.Store,
) error {

	mode := &serial.Mode{
		BaudRate: 115200,
		DataBits: 8,
		Parity:   serial.NoParity,
		StopBits: serial.OneStopBit,
	}

	port, err := serial.Open("/dev/ttyUSB0", mode)

	if err != nil {
		return err
	}

	defer port.Close()

	time.Sleep(2 * time.Second)

	_ = port.ResetInputBuffer()

	ticker := time.NewTicker(tickInterval)

	defer ticker.Stop()

	prevRunning := Running

	for range ticker.C {

		cum := GetActiveSetpoints(subStore.Snapshot())

		if !Running && prevRunning {

			cum["cmd"] = 2

		} else if Running {

			cum["cmd"] = 1

		} else {

			log.Info().Msg("Skipping tick")

			prevRunning = Running

			continue
		}

		prevRunning = Running

		// Limpiar basura serial antes de enviar
		_ = port.ResetInputBuffer()

		msg, err := json.Marshal(cum)

		if err != nil {
			return err
		}

		log.Info().
			Str("msg", string(msg)).
			Msg("Sending command")

		_, err = port.Write(append(msg, '\n'))

		if err != nil {
			return err
		}

		var line string

		for attempts := 0; attempts < 3; attempts++ {

			line, err = readLine(port, readTimeout)

			if err != nil {

				log.Warn().
					Err(err).
					Int("attempt", attempts+1).
					Msg("Read attempt failed")

				_ = port.ResetInputBuffer()

				continue
			}

			line = strings.TrimSpace(line)

			// Línea vacía
			if line == "" {

				log.Warn().
					Msg("Empty line received")

				continue
			}

			// Debe iniciar con JSON
			if !strings.HasPrefix(line, "{") {

				log.Warn().
					Str("raw", line).
					Msg("Non-JSON line received")

				_ = port.ResetInputBuffer()

				line = ""

				continue
			}

			// Validar JSON real
			var js map[string]interface{}

			if err := json.Unmarshal([]byte(line), &js); err != nil {

				log.Warn().
					Err(err).
					Str("raw", line).
					Msg("Invalid JSON received")

				_ = port.ResetInputBuffer()

				line = ""

				continue
			}

			// JSON válido
			break
		}

		// No se recibió nada válido
		if line == "" {

			log.Warn().
				Msg("Skipping tick due to invalid response")

			continue
		}

		data <- line
	}

	return nil
}

func SerialLoop(
	data chan<- string,
	subStore *db.Store,
) {

	for {

		err := StartSerialHandler(data, subStore)

		if err != nil {

			log.Error().
				Err(err).
				Msg("Serial reader failed")

			// Esperar a que vuelva el dispositivo
			for {

				if _, statErr := os.Stat("/dev/ttyUSB0"); statErr == nil {
					break
				}

				log.Warn().
					Msg("Waiting for /dev/ttyUSB0 to reappear...")

				time.Sleep(3 * time.Second)
			}

			// Tiempo extra de estabilización
			time.Sleep(2 * time.Second)
		}
	}
}