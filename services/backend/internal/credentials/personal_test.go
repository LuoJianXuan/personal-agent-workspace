package credentials

import (
	"bytes"
	"encoding/base64"
	"testing"
)

func TestCredentialsBindOwnerAndSurviveKeyRotation(t *testing.T) {
	// Test-only keys. The key ring normally comes from the ignored local environment.
	old := base64.StdEncoding.EncodeToString(bytes.Repeat([]byte{1}, 32))
	newKey := base64.StdEncoding.EncodeToString(bytes.Repeat([]byte{2}, 32))
	ring := &Keyring{active: "old", keys: map[string]string{"old": old}}
	aad := []byte("connection:owner:version:endpoint")
	token := "fixture-token-never-used-outside-test"
	keyID, first, err := ring.Seal(token, aad)
	if err != nil {
		t.Fatal(err)
	}
	_, second, err := ring.Seal(token, aad)
	if err != nil || bytes.Equal(first, second) || bytes.Contains(first, []byte(token)) {
		t.Fatal("ciphertexts must be randomized and differ from plaintext")
	}
	for _, changed := range []string{"connection:other:version:endpoint", "connection:owner:version:other-endpoint"} {
		if _, err := ring.Open(keyID, first, []byte(changed)); err == nil {
			t.Fatalf("unexpected decryption for modified binding %s", changed)
		}
	}
	ring.active = "new"
	ring.keys["new"] = newKey
	opened, err := ring.Open(keyID, first, aad)
	if err != nil || opened != token {
		t.Fatal("old credentials must decrypt while the old key remains in the ring")
	}
	keyID, rotated, err := ring.Seal(opened, aad)
	if err != nil || keyID != "new" {
		t.Fatal("updated credentials must be sealed with the active key")
	}
	delete(ring.keys, "old")
	if _, err := ring.Open("old", first, aad); err == nil {
		t.Fatal("removed key must not resolve")
	}
	if _, err := ring.Open("new", rotated, aad); err != nil {
		t.Fatal("rotated credential must remain usable")
	}
}
