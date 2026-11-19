package credentials

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"errors"
	"os"
)

var ErrUnavailable = errors.New("connection secret unavailable")

type Keyring struct {
	active string
	keys   map[string]string
}

func Configured() (*Keyring, error) {
	ring := &Keyring{active: os.Getenv("CONNECTION_SECRET_ACTIVE_KEY_ID")}
	if json.Unmarshal([]byte(os.Getenv("CONNECTION_SECRET_KEYS")), &ring.keys) != nil {
		return nil, ErrUnavailable
	}
	if _, err := ring.aead(ring.active); err != nil {
		return nil, err
	}
	return ring, nil
}

func (r *Keyring) aead(id string) (cipher.AEAD, error) {
	key, err := base64.StdEncoding.DecodeString(r.keys[id])
	if err != nil || len(key) != 32 || id == "" {
		return nil, ErrUnavailable
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, ErrUnavailable
	}
	return cipher.NewGCM(block)
}

func (r *Keyring) Seal(secret string, aad []byte) (string, []byte, error) {
	aead, err := r.aead(r.active)
	if err != nil {
		return "", nil, err
	}
	nonce := make([]byte, aead.NonceSize())
	if _, err := rand.Read(nonce); err != nil {
		return "", nil, ErrUnavailable
	}
	return r.active, aead.Seal(nonce, nonce, []byte(secret), aad), nil
}

func (r *Keyring) Open(keyID string, encrypted, aad []byte) (string, error) {
	aead, err := r.aead(keyID)
	if err != nil || len(encrypted) < aead.NonceSize()+aead.Overhead() {
		return "", ErrUnavailable
	}
	n := aead.NonceSize()
	plain, err := aead.Open(nil, encrypted[:n], encrypted[n:], aad)
	if err != nil {
		return "", ErrUnavailable
	}
	defer clear(plain)
	return string(plain), nil
}
