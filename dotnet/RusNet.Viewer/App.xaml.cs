using System.IO;
using System.Windows;

namespace RusNet.Viewer;

/// <summary>
/// Application entry point. Captures a command-line report path (if any) so the
/// main window can load it once the WebView2 runtime is ready.
/// </summary>
public partial class App : Application
{
    /// <summary>Report file passed on the command line, or null.</summary>
    public string? StartupFile { get; private set; }

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        // First non-empty argument that points at an existing file wins.
        foreach (var arg in e.Args)
        {
            if (!string.IsNullOrWhiteSpace(arg) && File.Exists(arg))
            {
                StartupFile = Path.GetFullPath(arg);
                break;
            }
        }
    }
}
