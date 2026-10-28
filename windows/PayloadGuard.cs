using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Web.Script.Serialization;

internal static class PayloadGuard
{
    internal static void Verify(string root)
    {
        root = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        string manifestPath = Path.Combine(root, "INSTALL-MANIFEST.json");
        if (new FileInfo(manifestPath).Length > 8388608) throw new InvalidDataException();
        var serializer = new JavaScriptSerializer { MaxJsonLength = 8388608 };
        var manifest = serializer.Deserialize<Dictionary<string, object>>(File.ReadAllText(manifestPath));
        if ((string)manifest["version"] != "2.2.0a1") throw new InvalidDataException();
        var expected = (Dictionary<string, object>)manifest["files"];
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var item in expected) {
            string path = Path.GetFullPath(Path.Combine(root, item.Key.Replace('/', Path.DirectorySeparatorChar)));
            if (!path.StartsWith(root, StringComparison.OrdinalIgnoreCase) || !seen.Add(path)) throw new InvalidDataException();
            var info = new FileInfo(path);
            if ((info.Attributes & FileAttributes.ReparsePoint) != 0) throw new InvalidDataException();
            var record = (Dictionary<string, object>)item.Value;
            if (info.Length != Convert.ToInt64(record["bytes"])) throw new InvalidDataException();
            using (var sha = SHA256.Create()) using (var stream = File.OpenRead(path)) {
                string hash = BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
                if (hash != (string)record["sha256"]) throw new InvalidDataException();
            }
        }
        var pending = new Stack<string>(); pending.Push(root); int count = 0;
        while (pending.Count > 0) {
            string dir = pending.Pop();
            if ((File.GetAttributes(dir) & FileAttributes.ReparsePoint) != 0) throw new InvalidDataException();
            foreach (string sub in Directory.GetDirectories(dir)) pending.Push(sub);
            foreach (string path in Directory.GetFiles(dir)) {
                if (++count > 20000) throw new InvalidDataException();
                if (seen.Contains(path)) continue;
                string relative = path.Substring(root.Length);
                if (relative != "INSTALL-MANIFEST.json" && relative != "INSTALLATION.json" &&
                    relative != "unins000.exe" && relative != "unins000.dat" && relative != "unins000.msg")
                    throw new InvalidDataException("Unexpected installed file");
            }
        }
    }
}
