package contracts

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestSharedExamples(t *testing.T) {
	for file, name := range map[string]string{"model-write": "ModelWrite", "skill-write": "SkillWrite", "mcp-write": "McpWrite", "discover-result": "DiscoverResult", "start": "Start", "snapshot": "Snapshot", "event": "Event", "events": "EventPage", "approval": "Approval", "tool-result": "ToolResult", "file": "File", "chart": "Chart"} {
		raw, err := os.ReadFile(filepath.Join("../../../../schemas/examples", file+".json"))
		if err != nil {
			t.Fatal(err)
		}
		var v map[string]any
		if err = json.Unmarshal(raw, &v); err != nil {
			t.Fatal(err)
		}
		s, err := compiler.Compile("contracts.json#/$defs/" + name)
		if err != nil {
			t.Fatal(err)
		}
		if err = s.Validate(v); err != nil {
			t.Fatalf("%s: %v", name, err)
		}
		v["unknown_field"] = true
		if s.Validate(v) == nil {
			t.Fatalf("%s accepted unknown field", name)
		}
	}
}
