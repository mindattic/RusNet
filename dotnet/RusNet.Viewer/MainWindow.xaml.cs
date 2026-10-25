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

    // Message the viewer's setHostOpen callback posts back to this host. When the
    // user clicks the page's "Open report…" button, we show our native dialog.
    private const string HostBridgeScript = """
        (function () {
          if (window.rusnet && typeof window.rusnet.setHostOpen === 'function') {
            window.rusnet.setHostOpen(function () {
              try { window.chrome.webview.postMessage('rusnet:open'); } catch (e) {}
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
    }

    private async void OpenButton_Click(object sender, RoutedEventArgs e)
    {
        await PromptAndLoadAsync();
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
}
