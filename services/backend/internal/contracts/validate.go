package contracts

import (
	"bytes"
	_ "embed"
	"encoding/json"
	"fmt"
	"github.com/santhosh-tekuri/jsonschema/v5"
	"io"
	"sync"
)

//go:embed schema.json
var source []byte
var compiler = func() *jsonschema.Compiler {
	c := jsonschema.NewCompiler()
	c.AssertFormat = true
	if err := c.AddResource("contracts.json", bytes.NewReader(source)); err != nil {
		panic(err)
	}
	return c
}()
var loginSchema = compiler.MustCompile("contracts.json#/$defs/Login")

func DecodeLogin(r io.Reader) (Login, error) {
	var result Login
	raw, err := io.ReadAll(io.LimitReader(r, 8193))
	if err != nil || len(raw) > 8192 {
		return result, fmt.Errorf("invalid body")
	}
	var value any
	if err = json.Unmarshal(raw, &value); err != nil {
		return result, err
	}
	if err = loginSchema.Validate(value); err != nil {
		return result, err
	}
	err = json.Unmarshal(raw, &result)
	return result, err
}

var schemaMu sync.Mutex
var schemaCache = map[string]*jsonschema.Schema{}

func Validate(name string, value any) error {
	schemaMu.Lock()
	schema := schemaCache[name]
	if schema == nil {
		var err error
		schema, err = compiler.Compile("contracts.json#/$defs/" + name)
		if err != nil {
			schemaMu.Unlock()
			return err
		}
		schemaCache[name] = schema
	}
	schemaMu.Unlock()
	return schema.Validate(value)
}
func Decode(name string, r io.Reader) (map[string]any, error) {
	limit := int64(262144)
	if name == "DocumentResult" || name == "ParsedDocument" {
		limit = 2200000
	}
	raw, err := io.ReadAll(io.LimitReader(r, limit+1))
	if err != nil || int64(len(raw)) > limit {
		return nil, fmt.Errorf("invalid body")
	}
	var value map[string]any
	if err = json.Unmarshal(raw, &value); err != nil {
		return nil, err
	}
	return value, Validate(name, value)
}
