package blobstore

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"mime"
	"net"
	"net/http"
	"net/url"
	"os"
	"path"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

const MaxBytes = 5 * 1024 * 1024

var ErrUnavailable = errors.New("STORAGE_UNAVAILABLE")
var ErrIntegrity = errors.New("FILE_INTEGRITY_ERROR")
var ErrMissing = errors.New("FILE_MISSING")

type Metadata struct {
	Size              int64
	SHA256, MediaType string
}
type Store interface {
	Put(context.Context, string, []byte, Metadata) error
	Get(context.Context, string, Metadata) ([]byte, error)
	Head(context.Context, string, Metadata) error
	Delete(context.Context, string) error
	PresignGet(context.Context, string, string, string) (string, time.Time, error)
}
type Registry struct {
	Default string
	Stores  map[string]Store
}

func (r *Registry) For(provider string) (Store, error) {
	if provider == "" {
		provider = "local"
	}
	s := r.Stores[provider]
	if s == nil {
		return nil, ErrUnavailable
	}
	return s, nil
}
func NewFromEnv() (*Registry, error) {
	local := &Local{Root: os.Getenv("FILE_ROOT")}
	provider := os.Getenv("BLOB_STORE_PROVIDER")
	if provider == "" {
		provider = "local"
	}
	r := &Registry{Default: provider, Stores: map[string]Store{"local": local}}
	if provider != "local" && provider != "s3" {
		return nil, ErrUnavailable
	}
	if provider == "s3" || os.Getenv("S3_ACCESS_KEY_ID") != "" || os.Getenv("S3_SECRET_ACCESS_KEY") != "" {
		s, err := newS3()
		if err != nil {
			return nil, err
		}
		r.Stores["s3"] = s
	}
	return r, nil
}
func validKey(key string) bool {
	return key != "" && key != "." && !strings.ContainsAny(key, "\\:\x00") && !strings.HasPrefix(key, "/") && path.Clean(key) == key && key != ".." && !strings.HasPrefix(key, "../")
}
func validate(data []byte, m Metadata) error {
	h := sha256.Sum256(data)
	if len(data) > MaxBytes || int64(len(data)) != m.Size || hex.EncodeToString(h[:]) != m.SHA256 {
		return ErrIntegrity
	}
	return nil
}

type Local struct{ Root string }

func (s *Local) filename(key string) (string, error) {
	if s.Root == "" || !validKey(key) {
		return "", ErrUnavailable
	}
	// Reject symlinks in every existing component, including the storage root.
	target := filepath.Join(s.Root, filepath.FromSlash(key))
	for p := target; ; p = filepath.Dir(p) {
		st, e := os.Lstat(p)
		if e == nil && st.Mode()&os.ModeSymlink != 0 {
			return "", ErrUnavailable
		}
		parent := filepath.Dir(p)
		if parent == p {
			break
		}
	}
	return target, nil
}
func (s *Local) Put(ctx context.Context, key string, data []byte, m Metadata) error {
	if err := validate(data, m); err != nil {
		return err
	}
	p, e := s.filename(key)
	if e != nil {
		return e
	}
	if e = os.MkdirAll(filepath.Dir(p), 0700); e != nil {
		return ErrUnavailable
	}
	if _, e = os.Lstat(p); e == nil {
		return s.Head(ctx, key, m)
	}
	f, e := os.CreateTemp(filepath.Dir(p), "tmp-")
	if e != nil {
		return ErrUnavailable
	}
	defer os.Remove(f.Name())
	if _, e = f.Write(data); e != nil {
		f.Close()
		return ErrUnavailable
	}
	if e = f.Sync(); e != nil {
		f.Close()
		return ErrUnavailable
	}
	if e = f.Close(); e != nil {
		return ErrUnavailable
	}
	if ctx.Err() != nil {
		return ctx.Err()
	}
	// Link provides an atomic create-if-absent; it never overwrites an immutable object.
	if e = os.Link(f.Name(), p); e != nil {
		if errors.Is(e, os.ErrExist) {
			return s.Head(ctx, key, m)
		}
		return ErrUnavailable
	}
	return nil
}
func (s *Local) Get(ctx context.Context, key string, m Metadata) ([]byte, error) {
	p, e := s.filename(key)
	if e != nil {
		return nil, e
	}
	f, e := os.Open(p)
	if e != nil {
		return nil, ErrMissing
	}
	defer f.Close()
	st, e := f.Stat()
	if e != nil || !st.Mode().IsRegular() || st.Size() > MaxBytes {
		return nil, ErrIntegrity
	}
	data, e := io.ReadAll(io.LimitReader(f, MaxBytes+1))
	if e != nil {
		return nil, ErrUnavailable
	}
	if e = validate(data, m); e != nil {
		return nil, e
	}
	return data, nil
}
func (s *Local) Head(ctx context.Context, key string, m Metadata) error {
	_, e := s.Get(ctx, key, m)
	return e
}
func (s *Local) Delete(ctx context.Context, key string) error {
	p, e := s.filename(key)
	if e != nil {
		return e
	}
	e = os.Remove(p)
	if errors.Is(e, os.ErrNotExist) {
		return nil
	}
	return e
}
func (s *Local) PresignGet(context.Context, string, string, string) (string, time.Time, error) {
	return "", time.Time{}, errors.New("PRESIGN_UNSUPPORTED")
}

type S3 struct {
	client, public *minio.Client
	bucket         string
	ttl            time.Duration
}

func newS3() (*S3, error) {
	region := os.Getenv("S3_REGION")
	if region == "" {
		region = "us-east-1"
	}
	key, secret, bucket := os.Getenv("S3_ACCESS_KEY_ID"), os.Getenv("S3_SECRET_ACCESS_KEY"), os.Getenv("S3_BUCKET")
	if key == "" || secret == "" || bucket == "" {
		return nil, ErrUnavailable
	}
	lookup := minio.BucketLookupDNS
	if os.Getenv("S3_FORCE_PATH_STYLE") != "false" {
		lookup = minio.BucketLookupPath
	}
	create := func(raw string) (*minio.Client, error) {
		u, e := url.Parse(raw)
		if e != nil || u.Host == "" || (u.Scheme != "http" && u.Scheme != "https") || u.User != nil || u.RawQuery != "" || (u.Path != "" && u.Path != "/") {
			return nil, ErrUnavailable
		}
		transport := &http.Transport{
			Proxy:                 nil,
			DialContext:           (&net.Dialer{Timeout: 5 * time.Second, KeepAlive: 30 * time.Second}).DialContext,
			TLSHandshakeTimeout:   5 * time.Second,
			ResponseHeaderTimeout: 10 * time.Second,
			ExpectContinueTimeout: time.Second,
		}
		return minio.New(u.Host, &minio.Options{Creds: credentials.NewStaticV4(key, secret, ""), Secure: u.Scheme == "https", Region: region, BucketLookup: lookup, Transport: transport})
	}
	internal, e := create(os.Getenv("S3_INTERNAL_ENDPOINT"))
	if e != nil {
		return nil, ErrUnavailable
	}
	public, e := create(os.Getenv("S3_PUBLIC_ENDPOINT"))
	if e != nil {
		return nil, ErrUnavailable
	}
	ttl := 600
	if v := os.Getenv("S3_PRESIGN_TTL_SECONDS"); v != "" {
		n, e := strconv.Atoi(v)
		if e != nil || n < 300 || n > 900 {
			return nil, ErrUnavailable
		}
		ttl = n
	}
	return &S3{internal, public, bucket, time.Duration(ttl) * time.Second}, nil
}
func (s *S3) Put(ctx context.Context, key string, data []byte, m Metadata) error {
	if !validKey(key) {
		return ErrUnavailable
	}
	if e := validate(data, m); e != nil {
		return e
	}
	if _, e := s.client.StatObject(ctx, s.bucket, key, minio.StatObjectOptions{}); e == nil {
		return s.Head(ctx, key, m)
	} else if code := minio.ToErrorResponse(e).Code; code != "NoSuchKey" && code != "NoSuchObject" {
		return ErrUnavailable
	}
	opts := minio.PutObjectOptions{ContentType: m.MediaType, UserMetadata: map[string]string{"sha256": m.SHA256}, DisableMultipart: true}
	opts.SetMatchETagExcept("*")
	_, e := s.client.PutObject(ctx, s.bucket, key, bytes.NewReader(data), m.Size, opts)
	if e != nil {
		if minio.ToErrorResponse(e).StatusCode == 412 {
			return s.Head(ctx, key, m)
		}
		return ErrUnavailable
	}
	return s.Head(ctx, key, m)
}
func (s *S3) Head(ctx context.Context, key string, m Metadata) error {
	if !validKey(key) {
		return ErrUnavailable
	}
	st, e := s.client.StatObject(ctx, s.bucket, key, minio.StatObjectOptions{})
	if e != nil {
		if minio.ToErrorResponse(e).Code == "NoSuchKey" {
			return ErrMissing
		}
		return ErrUnavailable
	}
	if st.Size != m.Size || st.Metadata.Get("X-Amz-Meta-Sha256") != m.SHA256 {
		return ErrIntegrity
	}
	return nil
}
func (s *S3) Get(ctx context.Context, key string, m Metadata) ([]byte, error) {
	if e := s.Head(ctx, key, m); e != nil {
		return nil, e
	}
	f, e := s.client.GetObject(ctx, s.bucket, key, minio.GetObjectOptions{})
	if e != nil {
		return nil, ErrUnavailable
	}
	defer f.Close()
	b, e := io.ReadAll(io.LimitReader(f, MaxBytes+1))
	if e != nil {
		return nil, ErrUnavailable
	}
	if e = validate(b, m); e != nil {
		return nil, e
	}
	return b, nil
}
func (s *S3) Delete(ctx context.Context, key string) error {
	if !validKey(key) {
		return ErrUnavailable
	}
	return s.client.RemoveObject(ctx, s.bucket, key, minio.RemoveObjectOptions{})
}
func (s *S3) PresignGet(ctx context.Context, key, name, media string) (string, time.Time, error) {
	if !validKey(key) {
		return "", time.Time{}, ErrUnavailable
	}
	q := url.Values{"response-content-type": {media}, "response-content-disposition": {mime.FormatMediaType("attachment", map[string]string{"filename": name})}}
	u, e := s.public.PresignedGetObject(ctx, s.bucket, key, s.ttl, q)
	if e != nil {
		return "", time.Time{}, ErrUnavailable
	}
	return u.String(), time.Now().UTC().Add(s.ttl), nil
}
func (r *Registry) Ready(ctx context.Context) error {
	if r.Default == "s3" {
		s, ok := r.Stores["s3"].(*S3)
		if !ok {
			return ErrUnavailable
		}
		ok, e := s.client.BucketExists(ctx, s.bucket)
		if e != nil || !ok {
			return ErrUnavailable
		}
	}
	return nil
}
