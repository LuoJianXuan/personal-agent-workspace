package workspace
import("testing";"os";"context";"errors";"agentworkspace/backend/internal/contracts";"agentworkspace/backend/internal/platform";"gorm.io/gorm";"github.com/google/uuid")
func TestOwnedThreadIsolation(t *testing.T){
 dsn:=os.Getenv("ACCEPTANCE_DATABASE_URL");if dsn==""{t.Skip("isolated acceptance DSN required")};db,e:=platform.Open(dsn);if e!=nil{t.Fatal(e)}
 tx:=db.Begin();defer tx.Rollback();var ids []string;if e=tx.Raw("SELECT id FROM backend.users WHERE role='user' ORDER BY username").Scan(&ids).Error;e!=nil||len(ids)!=2{t.Fatal("test users missing")}
 tenant,project,id:=uuid.NewString(),uuid.NewString(),uuid.NewString()
 if e=tx.Exec("INSERT INTO backend.threads(id,owner_id,tenant_id,project_id,title) VALUES(?,?,?,?,?)",id,ids[0],tenant,project,"acceptance").Error;e!=nil{t.Fatal(e)}
 svc:=Service{DB:tx};identity:=contracts.Context{TenantId:tenant,ProjectId:project,UserId:ids[0]}
 if _,e=svc.OwnedThread(context.Background(),identity,id);e!=nil{t.Fatal(e)}
 for _,x:=range []contracts.Context{{TenantId:tenant,ProjectId:project,UserId:ids[1]},{TenantId:uuid.NewString(),ProjectId:project,UserId:ids[0]},{TenantId:tenant,ProjectId:uuid.NewString(),UserId:ids[0]}}{if _,e=svc.OwnedThread(context.Background(),x,id);!errors.Is(e,gorm.ErrRecordNotFound){t.Fatal("foreign resource visible")}}
 if _,e=svc.OwnedThread(context.Background(),identity,uuid.NewString());!errors.Is(e,gorm.ErrRecordNotFound){t.Fatal("missing should be not found")}
}
