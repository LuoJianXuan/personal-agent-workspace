package blobstore

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"github.com/google/uuid"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/minio/minio-go/v7"
)

func metadata(b []byte) Metadata {
	h := sha256.Sum256(b)
	return Metadata{Size: int64(len(b)), SHA256: hex.EncodeToString(h[:]), MediaType: "text/plain"}
}
func TestLocalImmutabilityAndIntegrity(t *testing.T) {
	s := &Local{Root: t.TempDir()}
	ctx := context.Background()
	key := "users/test/revision/content"
	original := []byte("original")
	m := metadata(original)
	if e := s.Put(ctx, key, original, m); e != nil {
		t.Fatal(e)
	}
	if e := s.Put(ctx, key, []byte("changed"), metadata([]byte("changed"))); !errors.Is(e, ErrIntegrity) {
		t.Fatal("immutable key overwritten", e)
	}
	data, e := s.Get(ctx, key, m)
	if e != nil || string(data) != "original" {
		t.Fatal("round trip", e)
	}
	if e = os.WriteFile(filepath.Join(s.Root, filepath.FromSlash(key)), []byte("corrupt"), 0600); e != nil {
		t.Fatal(e)
	}
	if _, e = s.Get(ctx, key, m); !errors.Is(e, ErrIntegrity) {
		t.Fatal("corruption accepted", e)
	}
}
func TestLocalPathBoundary(t *testing.T) {
	s := &Local{Root: t.TempDir()}
	ctx := context.Background()
	b := []byte("x")
	for _, key := range []string{"../escape", "/absolute", "a/../b", "a\\b"} {
		if e := s.Put(ctx, key, b, metadata(b)); e == nil {
			t.Fatalf("path accepted %q", key)
		}
	}
	outside := t.TempDir()
	if e := os.Symlink(outside, filepath.Join(s.Root, "link")); e != nil {
		t.Skip("symlink capability unavailable")
	}
	if e := s.Put(ctx, "link/content", b, metadata(b)); e == nil {
		t.Fatal("symlink escaped root")
	}
}
func TestMinioRoundTripAndPrivateDownload(t *testing.T) {
	if os.Getenv("WORKSPACE_STORAGE_ACCEPTANCE") != "true" {
		t.Skip("requires explicit storage acceptance environment")
	}
	r, e := NewFromEnv()
	if e != nil {
		t.Fatal(e)
	}
	s, e := r.For("s3")
	if e != nil {
		t.Fatal(e)
	}
	ctx := context.Background()
	// Only the random acceptance prefix is created/deleted by this test.
	key := "acceptance/" + uuid.NewString() + "/content"
	b := []byte("private MinIO acceptance")
	m := metadata(b)
	if e = s.Put(ctx, key, b, m); e != nil {
		t.Fatal(e)
	}
	defer s.Delete(ctx, key)
	data, e := s.Get(ctx, key, m)
	if e != nil || string(data) != string(b) {
		t.Fatal("round trip", e)
	}
	u, _, e := s.PresignGet(ctx, key, "验收.txt", "text/plain")
	if e != nil {
		t.Fatal(e)
	}
	resp, e := http.Get(u)
	if e != nil {
		t.Fatal("public endpoint unreachable")
	}
	resp.Body.Close()
	if resp.StatusCode != 200 {
		t.Fatalf("signed download %d", resp.StatusCode)
	}
	unsigned := strings.SplitN(u, "?", 2)[0]
	resp, e = http.Get(unsigned)
	if e != nil {
		t.Fatal(e)
	}
	resp.Body.Close()
	if resp.StatusCode != 403 {
		t.Fatalf("bucket must be private: unsigned status %d", resp.StatusCode)
	}
	wrong := m
	wrong.SHA256 = strings.Repeat("0", 64)
	if e = s.Head(ctx, key, wrong); !errors.Is(e, ErrIntegrity) {
		t.Fatal("checksum mismatch accepted", e)
	}
}

func TestMinioAcceptanceBucketLifecycle(t *testing.T) {
	action := os.Getenv("WORKSPACE_STORAGE_BUCKET_ACTION")
	if action == "" {
		t.Skip("requires an explicit acceptance bucket action")
	}
	if os.Getenv("WORKSPACE_STORAGE_ACCEPTANCE") != "true" {
		t.Fatal("bucket lifecycle requires explicit storage acceptance")
	}
	bucket := os.Getenv("S3_BUCKET")
	if !strings.HasPrefix(bucket, "personal-agent-accept-") {
		t.Fatalf("refusing to mutate non-acceptance bucket %q", bucket)
	}
	s, e := newS3()
	if e != nil {
		t.Fatal(e)
	}
	ctx := context.Background()
	switch action {
	case "create":
		exists, e := s.client.BucketExists(ctx, bucket)
		if e != nil {
			t.Fatal(e)
		}
		if !exists {
			if e = s.client.MakeBucket(ctx, bucket, minio.MakeBucketOptions{Region: os.Getenv("S3_REGION")}); e != nil {
				t.Fatal(e)
			}
		}
	case "cleanup":
		for object := range s.client.ListObjects(ctx, bucket, minio.ListObjectsOptions{Recursive: true}) {
			if object.Err != nil {
				t.Fatal(object.Err)
			}
			if e = s.client.RemoveObject(ctx, bucket, object.Key, minio.RemoveObjectOptions{}); e != nil {
				t.Fatal(e)
			}
		}
		if e = s.client.RemoveBucket(ctx, bucket); e != nil {
			t.Fatal(e)
		}
	default:
		t.Fatalf("unsupported acceptance bucket action %q", action)
	}
}
