package agententry

import (
	"agentworkspace/backend/internal/contracts"
	"agentworkspace/backend/internal/control"
	"agentworkspace/backend/internal/workspace"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"time"
)

type RuntimeClient interface {
	Ready(context.Context) error
	Start(context.Context, contracts.Start) (contracts.Run, error)
}
type Entry struct {
	Control   control.Capabilities
	Workspace workspace.Application
	Runtime   RuntimeClient
}

// Independent pools prevent future SSE subscriptions from exhausting ordinary RPCs.
type HTTPClient struct {
	BaseURL, Token      string
	RPC, Stream, Parser *http.Client
}

func NewClient(base, token string) *HTTPClient {
	transport := func() *http.Transport {
		return &http.Transport{DialContext: (&net.Dialer{Timeout: 3 * time.Second}).DialContext, MaxConnsPerHost: 16, MaxIdleConnsPerHost: 8, ResponseHeaderTimeout: 10 * time.Second}
	}
	streamTransport := transport()
	streamTransport.MaxConnsPerHost = 40
	streamTransport.MaxIdleConnsPerHost = 32
	return &HTTPClient{base, token, &http.Client{Timeout: 10 * time.Second, Transport: transport()}, &http.Client{Transport: streamTransport}, &http.Client{Timeout: 40 * time.Second, Transport: transport()}}
}
func (c *HTTPClient) Ready(ctx context.Context) error {
	r, err := http.NewRequestWithContext(ctx, "GET", c.BaseURL+"/internal/ready", nil)
	if err != nil {
		return err
	}
	r.Header.Set("Authorization", "Bearer "+c.Token)
	res, err := c.RPC.Do(r)
	if err != nil {
		return fmt.Errorf("runtime unavailable")
	}
	defer res.Body.Close()
	if res.StatusCode != 200 {
		return fmt.Errorf("runtime not ready")
	}
	return nil
}

func (c *HTTPClient) ExtractDocument(ctx context.Context, metadata contracts.DocumentExtractMetadata, data []byte) (contracts.ParsedDocument, error) {
	var result contracts.ParsedDocument
	raw, _ := json.Marshal(metadata)
	request, err := http.NewRequestWithContext(ctx, "POST", c.BaseURL+"/internal/documents/extract", bytes.NewReader(data))
	if err != nil {
		return result, err
	}
	request.Header.Set("Authorization", "Bearer "+c.Token)
	request.Header.Set("Content-Type", metadata.MediaType)
	request.Header.Set("X-Document-Metadata", string(raw))
	response, err := c.Parser.Do(request)
	if err != nil {
		return result, fmt.Errorf("document parser unavailable")
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, 2*1024*1024+1))
	if err != nil || len(body) > 2*1024*1024 || response.StatusCode != http.StatusOK {
		return result, fmt.Errorf("document extraction failed")
	}
	if err = json.Unmarshal(body, &result); err != nil || contracts.Validate("ParsedDocument", mapValue(body)) != nil {
		return result, fmt.Errorf("invalid document extraction")
	}
	return result, nil
}

func mapValue(raw []byte) map[string]any {
	var value map[string]any
	_ = json.Unmarshal(raw, &value)
	return value
}
