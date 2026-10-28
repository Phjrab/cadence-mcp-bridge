using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;

[assembly: AssemblyTitle("Cadence MCP Bridge")]
[assembly: AssemblyVersion("2.2.0.1")]
[assembly: AssemblyInformationalVersion("2.2.0a1")]

internal static class Launcher
{
    // Windows command-line quoting, including trailing slashes and embedded quotes.
    internal static string Quote(string value)
    {
        var output = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in value) {
            if (c == '\\') { slashes++; continue; }
            output.Append('\\', c == '"' ? slashes * 2 + 1 : slashes);
            output.Append(c); slashes = 0;
        }
        output.Append('\\', slashes * 2); output.Append('"');
        return output.ToString();
    }

    public static int Main(string[] args)
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        try { PayloadGuard.Verify(root); }
        catch { Console.Error.WriteLine("HOST_PAYLOAD_REJECTED"); return 2; }
        if (args.Length == 1 && args[0] == "--host-verify") {
            Console.WriteLine("HOST_PAYLOAD_VERIFIED"); return 0;
        }
        string python = Path.Combine(root, "runtime", "python.exe");
        if (!File.Exists(python)) { Console.Error.WriteLine("HOST_RUNTIME_MISSING"); return 2; }
        var command = new StringBuilder("-I -B -X utf8 -m cadence_mcp_bridge");
        if (args.Length == 1 && args[0] == "--host-uninstall") {
            command = new StringBuilder("-I -B -X utf8 -m cadence_mcp_bridge.windows_host.uninstall");
            args = new string[0];
        }
        foreach (string arg in args) { command.Append(' '); command.Append(Quote(arg)); }
        var start = new ProcessStartInfo(python, command.ToString());
        start.UseShellExecute = false;
        // Inherited protocol handles: no GUI, shell, progress or stdout relay.
        start.WorkingDirectory = root;
        try { using (var child = Process.Start(start)) { child.WaitForExit(); return child.ExitCode; } }
        catch { Console.Error.WriteLine("HOST_START_FAILED"); return 2; }
    }
}
