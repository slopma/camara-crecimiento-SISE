package main

import (
	"strings"
	"time"

	"github.com/beevik/ntp"
	"github.com/rs/zerolog/log"
)

var timeOffset time.Duration
var ntpServers = []string{
	"time.google.com",
	"time.cloudflare.com",
	"pool.ntp.org",
}

func SyncTime() error {
	var t time.Time
	var err error
	for _, server := range ntpServers {
		t, err = ntp.Time(server)
		if err == nil {
			break
		}
	}

	if err != nil {
		return err
	}

	timeOffset = time.Until(t)
	return nil
}

func GetInternetTime() time.Time {
	return time.Now().Add(timeOffset)
}

func GetCurrentTimeProfile() string {
	hour := GetInternetTime().Hour()
	switch {
	case hour >= 6 && hour < 12:
		return "1"
	case hour >= 12 && hour < 18:
		return "2"
	default:
		return "3"
	}
}

func GetActiveSetpoints(store map[string]any) map[string]any {
	profile := GetCurrentTimeProfile()
	out := make(map[string]any)

	for key, value := range store {
		if !strings.HasSuffix(key, profile) {
			continue
		}

		base := strings.TrimSuffix(key, profile)
		out[base] = value
	}

	return out
}

func TimeLoop() {
	ticker := time.NewTicker(10 * time.Minute)
	for range ticker.C {
		err := SyncTime()
		if err != nil {
			log.Error().Err(err).Msg("Time sync failed")
			time.Sleep(2 * time.Second)
		}
	}
}
