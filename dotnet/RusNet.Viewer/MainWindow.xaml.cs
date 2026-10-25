using System.Diagnostics;
using System.IO;
using System.Windows;
using Microsoft.Web.WebView2.Core;
using Microsoft.Win32;

namespace RusNet.Viewer;

/// <summary>
/// Hosts the self-contained RusNet HTML viewer in a WebView2 control and wires its
/// JS open hook to a native <see cref="OpenFileDialog"/>. No scanning or network
/// logic lives here — this side only renders a JSON report the user picks.
/// </summary>
public partial class MainWindow : Window
{
    private const string OpenMessage = "rusnet:open";
    private const string ScanMessage = "rusnet:scan";

    // Messages the viewer's host hooks post back to this app. Open shows a native dialog; Scan shows
    // the page's scanning overlay and asks us to run the Python scanner. Registering setHostScan is
    // what reveals the page's Scan buttons, so the two desktop apps look identical.
    private const string HostBridgeScript = """
        (function () {
          if (!window.rusnet) return;
          if (typeof window.rusnet.setHostOpen === 'function') {
            window.rusnet.setHostOpen(function () {
              try { window.chrome.webview.postMessage('rusnet:open'); } catch (e) {}
            });
          }
          if (typeof window.rusnet.setHostScan === 'function') {
            window.rusnet.setHostScan(function () {
              try { window.rusnet.setScanning(true); window.chrome.webview.postMessage('rusnet:scan'); } catch (e) {}
            });
          }
        })();
        """;

    private bool _bridgeReady;

    public MainWindow()
    {
        InitializeComponent();
        Loaded += MainWindow_Loaded;
    }

    private async void MainWindow_Loaded(object sender, RoutedEventArgs e)
    {
        try
        {
            // Keep WebView2's cache/user data out of the working directory.
            var userDataFolder = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "MindAttic", "RusNet.Viewer", "WebView2");
            Directory.CreateDirectory(userDataFolder);

            var env = await CoreWebView2Environment.CreateAsync(
                browserExecutableFolder: null,
                userDataFolder: userDataFolder);
            await WebView.EnsureCoreWebView2Async(env);

            var core = WebView.CoreWebView2;
            core.Settings.AreDefaultContextMenusEnabled = true;
            core.Settings.IsStatusBarEnabled = false;
            core.Settings.AreDevToolsEnabled = false;

            core.WebMessageReceived += CoreWebView2_WebMessageReceived;
            core.NavigationCompleted += CoreWebView2_NavigationCompleted;

            // viewer.htm (~55KB) is well under NavigateToString's ~2MB limit.
            var htmlPath = Path.Combine(AppContext.BaseDirectory, "Assets", "viewer.htm");
            var html = await File.ReadAllTextAsync(htmlPath);
            core.NavigateToString(html);
        }
        catch (Exception ex)
        {
            MessageBox.Show(this,
                "Could not start the WebView2 runtime.\n\n" + ex.Message +
                "\n\nInstall the Microsoft Edge WebView2 Runtime and try again.",
                "RusNet", MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }

    private async void CoreWebView2_NavigationCompleted(object? sender, CoreWebView2NavigationCompletedEventArgs e)
    {
        if (!e.IsSuccess || _bridgeReady)
            return;

        // Register the native open hook once the viewer's JS API exists.
        await WebView.CoreWebView2.ExecuteScriptAsync(HostBridgeScript);
        _bridgeReady = true;

        // Load a report passed on the command line, if any.
        if (Application.Current is App app && app.StartupFile is { } startup)
        {
            await LoadReportAsync(startup);
        }
    }

    private async void CoreWebView2_WebMessageReceived(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        string message;
        try
        {
            message = e.TryGetWebMessageAsString();
        }
        catch
        {
            return;
        }

        if (message == OpenMessage)
        {
            await PromptAndLoadAsync();
        }
        else if (message == ScanMessage)
        {
            await RunScanAsync();
        }
    }

    private async Task PromptAndLoadAsync()
    {
        var dialog = new OpenFileDialog
        {
            Title = "Open RusNet report",
            Filter = "RusNet report (*.json)|*.json|All files (*.*)|*.*",
            CheckFileExists = true
        };

        if (dialog.ShowDialog(this) == true)
        {
            await LoadReportAsync(dialog.FileName);
        }
    }

    private async Task LoadReportAsync(string path)
    {
        if (WebView.CoreWebView2 is null)
            return;

        try
        {
            var text = await File.ReadAllTextAsync(path);
            await WebView.CoreWebView2.ExecuteScriptAsync(ViewerScript.BuildLoadCall(text));
        }
        catch (Exception ex)
        {
            MessageBox.Show(this,
                "Could not read the report file.\n\n" + ex.Message,
                "RusNet", MessageBoxButton.OK, MessageBoxImage.Warning);
        }
    }

    // The .NET viewer has no scanner of its own (by design); a Scan runs the RusNet Python package
    // as a subprocess and loads the JSON it writes. The page's overlay is already showing by now.
    private async Task RunScanAsync()
    {
        string tempBase = Path.Combine(Path.GetTempPath(), "rusnet-scan-" + Guid.NewGuid().ToString("N"));
        try
        {
            var repoRoot = FindRepoRoot();
            if (repoRoot is null)
            {
                await SetScanningAsync(false);
                MessageBox.Show(this,
                    "Scanning from the desktop app needs the RusNet Python package.\n\n" +
                    "Run this app from its repo, or set the RUSNET_HOME environment variable to the " +
                    "RusNet checkout. You can always run `python -m rusnet scan` yourself and use Open.",
                    "RusNet", MessageBoxButton.OK, MessageBoxImage.Information);
                return;
            }

            var (exe, argPrefix) = ResolvePython();
            var psi = new ProcessStartInfo
            {
                FileName = exe,
                Arguments = argPrefix + "-m rusnet scan -o \"" + tempBase + "\"",
                WorkingDirectory = repoRoot,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardError = true,
                RedirectStandardOutput = true,
            };

            using var proc = new Process { StartInfo = psi };
            try
            {
                proc.Start();
            }
            catch (Exception)
            {
                await SetScanningAsync(false);
                MessageBox.Show(this,
                    "Could not launch Python. Install Python 3.9+ and make sure `python` is on PATH.",
                    "RusNet", MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }

            string stderr = await proc.StandardError.ReadToEndAsync();
            await proc.WaitForExitAsync();

            var jsonPath = tempBase + ".json";
            if (proc.ExitCode != 0 || !File.Exists(jsonPath))
            {
                await SetScanningAsync(false);
                MessageBox.Show(this,
                    "The scan did not complete.\n\n" + Trim(stderr),
                    "RusNet", MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }

            var text = await File.ReadAllTextAsync(jsonPath);
            await WebView.CoreWebView2.ExecuteScriptAsync(ViewerScript.BuildLoadCall(text));
            await SetScanningAsync(false);
        }
        catch (Exception ex)
        {
            await SetScanningAsync(false);
            MessageBox.Show(this, "Scan failed.\n\n" + ex.Message,
                "RusNet", MessageBoxButton.OK, MessageBoxImage.Warning);
        }
        finally
        {
            foreach (var f in new[] { tempBase + ".json", tempBase + ".htm" })
                try { if (File.Exists(f)) File.Delete(f); } catch { /* best effort */ }
        }
    }

    private async Task SetScanningAsync(bool on)
    {
        if (WebView.CoreWebView2 is not null)
            await WebView.CoreWebView2.ExecuteScriptAsync(
                "window.rusnet && window.rusnet.setScanning(" + (on ? "true" : "false") + ");");
    }

    // Walk up from the app's base directory (and from RUSNET_HOME / cwd) for a folder that holds the
    // rusnet package, so the subprocess can `python -m rusnet`.
    private static string? FindRepoRoot()
    {
        var candidates = new List<string?>
        {
            Environment.GetEnvironmentVariable("RUSNET_HOME"),
            AppContext.BaseDirectory,
            Directory.GetCurrentDirectory(),
        };
        foreach (var start in candidates)
        {
            if (string.IsNullOrWhiteSpace(start))
                continue;
            var dir = new DirectoryInfo(start);
            for (int i = 0; dir is not null && i < 8; i++, dir = dir.Parent)
            {
                if (File.Exists(Path.Combine(dir.FullName, "rusnet", "__main__.py")))
                    return dir.FullName;
            }
        }
        return null;
    }

    // Prefer `python`; fall back to the Windows launcher `py -3`.
    private static (string exe, string argPrefix) ResolvePython()
    {
        if (OperatingSystem.IsWindows() && ExistsOnPath("py"))
            return ("py", "-3 ");
        return ("python", "");
    }

    private static bool ExistsOnPath(string exe)
    {
        var paths = (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator);
        foreach (var p in paths)
        {
            try
            {
                if (File.Exists(Path.Combine(p, exe + ".exe")) || File.Exists(Path.Combine(p, exe)))
                    return true;
            }
            catch { /* malformed PATH entry */ }
        }
        return false;
    }

    private static string Trim(string s)
    {
        s = (s ?? "").Trim();
        return s.Length > 1200 ? s[^1200..] : s;
    }
}
