using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text;
using System.Threading.Tasks;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using System.Reflection;

[assembly: AssemblyTitle("Cadence MCP Bridge Setup")]
[assembly: AssemblyVersion("2.2.0.1")]
[assembly: AssemblyInformationalVersion("2.2.0a1")]

internal sealed class SetupWindow : Form
{
    readonly JavaScriptSerializer json = new JavaScriptSerializer();
    readonly TabControl tabs = new TabControl();
    readonly TextBox output = new TextBox();
    readonly Label stage = new Label();
    readonly TextBox alias = new TextBox(), host = new TextBox(), user = new TextBox();
    readonly TextBox identity = new TextBox(), settings = new TextBox(), context = new TextBox();
    readonly TextBox server = new TextBox(), project = new TextBox();
    readonly CheckBox replace = new CheckBox();
    string pendingHash = null, receipt = null;
    bool busy;

    internal SetupWindow()
    {
        Text = "Cadence MCP Bridge — 최초 설정 (2.2.0a1 시험판)";
        ClientSize = new Size(990, 760); MinimumSize = new Size(850, 650);
        Font = new Font("Malgun Gothic", 10); StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.FromArgb(246, 248, 251);
        var title = new Label { Text = "내 VM에 연결하는 Cadence MCP Bridge", Dock = DockStyle.Top,
            Height = 62, Padding = new Padding(22, 18, 0, 0), Font = new Font(Font.FontFamily, 18, FontStyle.Bold) };
        stage.Text = "프로그램 설치됨 · VM / 회로 / 실행 권한은 아직 확인하지 않았습니다";
        stage.Dock = DockStyle.Top; stage.Height = 44; stage.Padding = new Padding(24, 8, 0, 0);
        stage.ForeColor = Color.FromArgb(26, 77, 120);
        tabs.Dock = DockStyle.Fill; tabs.Padding = new Point(16, 7);
        output.Multiline = true; output.ReadOnly = true; output.ScrollBars = ScrollBars.Both;
        output.WordWrap = true; output.Dock = DockStyle.Bottom; output.Height = 220;
        output.BackColor = Color.White; output.Font = new Font("Malgun Gothic", 10);
        Controls.Add(tabs); Controls.Add(output); Controls.Add(stage); Controls.Add(title);
        BuildStart(); BuildVM(); BuildRuntime(); BuildCodex(); BuildStatus();
        foreach (var field in new TextBox[] { settings, context, server, project })
            field.TextChanged += (s, e) => { pendingHash = null; };
        replace.CheckedChanged += (s, e) => { pendingHash = null; };
        Shown += async (s, e) => { await Run(new Dictionary<string, object> { { "action", "status" } }, true); };
        FormClosing += (s, e) => { if (busy) { e.Cancel = true; MessageBox.Show(this,
            "진행 중인 확인이 끝난 뒤 닫아 주세요. 실행 중 작업을 강제 종료하지 않습니다."); } };
    }

    FlowLayoutPanel Page(string text)
    {
        var page = new TabPage(text) { BackColor = Color.White };
        var flow = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown,
            WrapContents = false, AutoScroll = true, Padding = new Padding(22) };
        page.Controls.Add(flow); tabs.TabPages.Add(page); return flow;
    }
    void Note(FlowLayoutPanel page, string text)
    { page.Controls.Add(new Label { Text = text, AutoSize = false, Width = 890, Height = 64, Margin = new Padding(0, 5, 0, 10) }); }
    void Field(FlowLayoutPanel page, string label, TextBox field, bool file)
    {
        var row = new FlowLayoutPanel { Width = 900, Height = 40, WrapContents = false };
        row.Controls.Add(new Label { Text = label, Width = 165, Height = 32, Padding = new Padding(0, 5, 0, 0) });
        field.Width = 570; row.Controls.Add(field);
        if (file) { var browse = new Button { Text = "찾아보기", Width = 100 }; browse.Click += (s, e) => {
            using (var dialog = new OpenFileDialog()) { if (dialog.ShowDialog(this) == DialogResult.OK) field.Text = dialog.FileName; }
        }; row.Controls.Add(browse); }
        page.Controls.Add(row);
    }
    void Button(FlowLayoutPanel page, string text, Func<Task> action)
    {
        var button = new Button { Text = text, AutoSize = true, MinimumSize = new Size(210, 38), Margin = new Padding(0, 7, 10, 7) };
        button.Click += async (s, e) => { if (!busy) await action(); }; page.Controls.Add(button);
    }
    void BuildStart()
    {
        var page = Page("1 시작");
        Note(page, "전용 Python과 브리지가 설치되었습니다. 시스템 Python이나 PATH를 바꾸지 않습니다.\n설정·journal·승인·결과는 프로그램과 분리해 보존합니다. 설치로 시뮬레이션을 시작하지 않습니다.");
        Button(page, "새 연결 안내 시작", async () => { await Run(Req("guide", "mode", "fresh")); tabs.SelectedIndex = 1; });
        Button(page, "기존 runtime 가져오기", async () => { await Run(Req("guide", "mode", "existing")); tabs.SelectedIndex = 2; });
        Button(page, "프로그램만 설치 — 연결은 나중에", async () => { await Run(Req("guide", "mode", "program-only")); });
        Note(page, "새 PC에서 기존 VM에 연결하는 경우에도 기존 장부를 유지해야 합니다.\n새 설정 선택은 fresh domain 생성이나 관리자 조치·실행 승인이 아닙니다.");
    }
    Dictionary<string, object> Connection(string action)
    { return new Dictionary<string, object> { { "action", action }, { "alias", alias.Text.Trim() },
        { "host", host.Text.Trim() }, { "user", user.Text.Trim() }, { "identity", identity.Text.Trim() } }; }
    void BuildVM()
    {
        var page = Page("2 VM 연결");
        Note(page, "본인의 VM 정보만 입력하세요. 비밀번호를 받거나 저장하지 않습니다. 기존 SSH 키/agent를 사용합니다.\nWindows OpenSSH Client와 신뢰를 확인한 known_hosts가 필요합니다. 연결 확인은 EDA를 실행하지 않습니다.");
        Field(page, "SSH 별칭", alias, false); Field(page, "VM 주소 / 호스트", host, false);
        Field(page, "일반 사용자", user, false); Field(page, "기존 키 파일 (선택)", identity, true);
        Button(page, "연결 정보 저장 (접속 없음)", async () => { await Run(Connection("save-connection")); });
        Button(page, "한 번 연결 확인", async () => {
            if (MessageBox.Show(this, "입력한 VM에 일반 사용자 SSH로 한 번 접속해 고정 연결 응답만 확인합니다.\n호스트 키 검사를 유지하며 변경·EDA·예약은 없습니다. 진행할까요?", "VM 접속 확인", MessageBoxButtons.OKCancel) != DialogResult.OK) return;
            var request = Connection("connect"); request["consent"] = true; await Run(request);
        });
    }
    void BuildRuntime()
    {
        var page = Page("3 내 실행 환경");
        Note(page, "기존 runtime을 선택하면 연결된 registry·journal·grant 경로를 그대로 검사합니다. 복사하거나 초기화하지 않습니다.\n새 사용자는 아래 안내를 내보내고 본인 환경·회로·PDK를 등록한 뒤 검증된 runtime을 선택하세요.");
        Field(page, "runtime 설정 파일", settings, true); Field(page, "context ID", context, false);
        Button(page, "기존 설정 확인 / context 목록", async () => { await Run(new Dictionary<string, object> {
            { "action", "runtime" }, { "settings", settings.Text.Trim() }, { "context", context.Text.Trim() } }); });
        Button(page, "새 사용자 등록 안내·예제 내보내기", async () => {
            using (var dialog = new FolderBrowserDialog()) {
                dialog.Description = "새 안내 폴더를 만들 상위 폴더 선택 (기존 파일은 덮어쓰지 않습니다)";
                if (dialog.ShowDialog(this) != DialogResult.OK) return;
                string destination = Path.Combine(dialog.SelectedPath, "cadence-operator-starter");
                await Run(Req("starter", "output", destination));
            }
        });
        Note(page, "남은 준비: 실제 환경 검사 → 필요한 관리자 계획 검토 → 기존 장부 연결 / 이력 없는 설치 증명 → 회로 등록\n→ native runtime 확인 → 정확한 실행 승인. 예제 해시·한도·회로를 실제 검증으로 표시하지 않습니다.");
    }
    void BuildCodex()
    {
        var page = Page("4 Codex 연결");
        Note(page, "현재 CODEX_HOME의 사용자 설정에 선택한 MCP 항목만 적용합니다. 기존 주석과 다른 MCP·모델 설정을 보존합니다.\nCodex가 없어도 설치할 수 있습니다. 설정 저장과 실제 앱 연결 성공은 별도입니다.");
        server.Text = "cadence-mcp-bridge"; Field(page, "MCP 이름", server, false);
        Field(page, "작업 폴더 (선택)", project, false);
        replace.Text = "같은 이름의 기존 항목을 업데이트 (아니면 다른 이름을 입력하거나 취소)";
        replace.Width = 850; page.Controls.Add(replace);
        Button(page, "변경 미리보기", async () => {
            await Run(new Dictionary<string, object> { { "action", "preview" },
                { "settings", settings.Text.Trim() }, { "context", context.Text.Trim() },
                { "name", server.Text.Trim() }, { "replace", replace.Checked }, { "project", project.Text.Trim() } });
        });
        Button(page, "확인한 변경 적용", async () => {
            if (pendingHash == null) { output.Text = "먼저 변경 미리보기를 실행하세요."; return; }
            if (MessageBox.Show(this, "아래 미리보기의 MCP 항목을 백업 후 적용합니다.\n동시에 다른 앱에서 설정을 편집하지 마세요. 적용할까요?", "Codex 설정 적용", MessageBoxButtons.OKCancel) != DialogResult.OK) return;
            await Run(new Dictionary<string, object> { { "action", "apply" }, { "consent", true }, { "after", pendingHash } });
        });
        Button(page, "이 설치가 적용한 연결만 제거 / 복구", async () => {
            if (receipt == null) { output.Text = "이 설치의 관리 기록이 없습니다. 기존 설정은 보존합니다."; return; }
            if (MessageBox.Show(this, "기록과 현재 항목이 같을 때만 제거하거나 직전 항목으로 복구합니다.\n다른 사용자 변경과 journal은 보존합니다.", "관리 연결 제거", MessageBoxButtons.OKCancel) != DialogResult.OK) return;
            await Run(new Dictionary<string, object> { { "action", "remove" }, { "consent", true }, { "receipt", receipt } });
        });
    }
    void BuildStatus()
    {
        var page = Page("5 상태·다음 단계");
        Note(page, "프로그램 설치 → 클라이언트 설정 → VM 연결 → preflight → 회로 등록 → 실행 승인\n앞 단계의 성공은 뒤 단계의 성공을 뜻하지 않습니다. 실제 앱에서 도구 호출은 별도로 확인하세요.");
        Button(page, "호스트 상태 확인 (원격 접속 없음)", async () => { await Run(Req("status")); });
        Note(page, "업데이트: 새 버전을 별도 폴더에 설치하고 runtime을 가져온 뒤 Codex 변경을 미리보기 합니다.\n기존 실행은 강제 종료하지 않습니다. 이전 버전과 journal을 지우지 말고 검증된 조합으로만 되돌리세요.");
        Note(page, "제거: 먼저 관리 연결 제거를 확인한 뒤 Windows 앱 목록에서 해당 버전만 제거합니다.\n사용자 데이터와 원격 회로·결과·승인·장부·실패 기록은 보존합니다. 시험판은 코드 서명되지 않았습니다.");
    }
    static Dictionary<string, object> Req(string action, string key = null, object value = null)
    { var r = new Dictionary<string, object> { { "action", action } }; if (key != null) r[key] = value; return r; }
    string Get(IDictionary<string, object> data, string key)
    { object value; return data.TryGetValue(key, out value) && value != null ? Convert.ToString(value) : ""; }
    void Restore(IDictionary<string, object> saved)
    {
        settings.Text = Get(saved, "settings"); context.Text = Get(saved, "context");
        object value;
        if (saved.TryGetValue("connection", out value)) {
            var c = value as IDictionary<string, object>;
            if (c != null) { alias.Text = Get(c, "alias"); host.Text = Get(c, "host"); user.Text = Get(c, "user"); identity.Text = Get(c, "identity"); }
        }
        if (saved.TryGetValue("receipts", out value)) {
            var receipts = value as ArrayList; if (receipts != null && receipts.Count > 0) receipt = Convert.ToString(receipts[0]);
        }
    }
    async Task Run(Dictionary<string, object> request, bool initial = false)
    {
        if (Get(request, "action") == "preview") pendingHash = null;
        busy = true; tabs.Enabled = false; output.Text = "확인 중…";
        try {
            string response = await Task.Run(() => CallBackend(json.Serialize(request)));
            var result = json.Deserialize<Dictionary<string, object>>(response);
            string status = Get(result, "status");
            var lines = new StringBuilder();
            if (status == "BLOCKED") { lines.AppendLine("확인 필요: " + Get(result, "reason")); lines.AppendLine(Get(result, "guidance")); }
            else { lines.AppendLine("상태: " + status); }
            if (result.ContainsKey("diff")) { pendingHash = Get(result, "after"); lines.AppendLine(Get(result, "path")); lines.AppendLine(Get(result, "diff")); lines.AppendLine(Get(result, "precedence_notice")); }
            if (result.ContainsKey("receipt")) receipt = Get(result, "receipt");
            if (status == "CLIENT_CONFIGURED") { pendingHash = null; stage.Text = "Codex 설정 저장됨 · 앱 재연결과 실제 도구 호출은 별도 확인이 필요합니다"; }
            if (status == "VM_CONNECTED") stage.Text = "SSH 연결 확인됨 · preflight / 회로 등록 / 실행 승인은 아직 미확인입니다";
            if (status == "HOST_INSTALLED") { lines.AppendLine("프로그램 설치 완료. VM·회로·실행 권한은 이 검사로 확인하지 않습니다."); }
            if (result.ContainsKey("contexts")) lines.AppendLine("context 목록: " + json.Serialize(result["contexts"]));
            if (result.ContainsKey("next")) lines.AppendLine(Get(result, "next"));
            if (result.ContainsKey("ssh_available")) lines.AppendLine((bool)result["ssh_available"] ? "OpenSSH Client 있음" : Get(result, "ssh_install_help"));
            if (result.ContainsKey("codex_config")) lines.AppendLine("사용자 설정: " + Get(result, "codex_config"));
            if (result.ContainsKey("project_overrides")) lines.AppendLine("프로젝트 설정 후보: " + json.Serialize(result["project_overrides"]));
            if (status == "LOCAL_CONTEXT_VALID") lines.AppendLine("기존 runtime·registry 경로 확인. journal·장부는 변경하지 않았습니다. 실제 VM 적격성과 승인 상태는 미확인입니다.");
            if (status == "CONNECTION_DRAFT_SAVED") lines.AppendLine("연결 정보만 저장했습니다. 기존 OpenSSH 별칭과 known_hosts가 준비돼야 연결할 수 있습니다.");
            lines.AppendLine("이 안내는 시뮬레이션을 자동 제출하지 않습니다.");
            output.Text = lines.ToString();
            if (initial && result.ContainsKey("saved_setup")) Restore((IDictionary<string, object>)result["saved_setup"]);
        } catch { output.Text = "설정 확인 중 오류가 발생했습니다. 원본 설정과 장부를 보존했습니다.\n전용 런타임·파일 접근 권한을 확인하고 상태 검사를 다시 실행하세요."; }
        finally { busy = false; tabs.Enabled = true; }
    }
    static string CallBackend(string request)
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        var start = new ProcessStartInfo(Path.Combine(root, "runtime", "python.exe"),
            "-I -B -X utf8 -m cadence_mcp_bridge.windows_host.backend");
        start.UseShellExecute = false; start.CreateNoWindow = true; start.WorkingDirectory = root;
        start.RedirectStandardInput = true; start.RedirectStandardOutput = true; start.RedirectStandardError = true;
        start.StandardOutputEncoding = Encoding.UTF8; start.StandardErrorEncoding = Encoding.UTF8;
        using (var child = Process.Start(start)) {
            child.StandardInput.Write(request); child.StandardInput.Close();
            var stdout = child.StandardOutput.ReadToEndAsync(); var stderr = child.StandardError.ReadToEndAsync();
            child.WaitForExit(); Task.WaitAll(stdout, stderr);
            if (stdout.Result.Length > 2097152) throw new InvalidDataException();
            return stdout.Result;
        }
    }
    [STAThread]
    static void Main() {
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        bool created;
        using (var mutex = new Mutex(true, "Local\\CadenceMCPBridgeSetup-" + Environment.UserName, out created)) {
        if (!created) { MessageBox.Show("이미 열려 있는 Cadence 설정 도우미를 사용하세요."); return; }
        try { PayloadGuard.Verify(AppDomain.CurrentDomain.BaseDirectory); }
        catch { MessageBox.Show("설치 파일의 무결성 확인에 실패했습니다. Python 실행 전에 중단했습니다.\n원본 설치 파일로 복구하고 사용자 설정과 journal을 보존하세요.", "Cadence MCP Bridge — HOST_PAYLOAD_REJECTED"); return; }
        Application.Run(new SetupWindow());
        }
    }
}
