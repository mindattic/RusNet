# RusNet Viewer (.NET / WPF)

A native Windows desktop host for the self-contained RusNet HTML network-map viewer.
It renders a RusNet JSON report (schema v1) in a WebView2 control and opens files with a
native dialog. There is **no scanning or network code** on the .NET side — the **Scan**
button runs the Python `rusnet` package as a subprocess; all discovery lives there.

The window has **no native chrome** — it is nothing but the shared web viewer, so it is
visually identical to the Python (pywebview) app. Open, Scan and the sun/moon theme toggle
all live in the page's own toolbar.

## Build & run

Easiest: from the repo root, double-click `install.bat` and choose **Windows** (or run
`install.bat windows`). It auto-installs the .NET SDK and the WebView2 runtime via winget if
missing, then publishes the app to `dist\windows\RusNet.Viewer.exe`.

To work on it directly you need the .NET 10 SDK and the Microsoft Edge WebView2 Runtime
(preinstalled on current Windows 11; the Evergreen installer covers older machines).

```sh
# from this dotnet/ folder
dotnet build                               # build everything (app + tests)
dotnet run --project RusNet.Viewer         # launch the viewer
dotnet run --project RusNet.Viewer -- path\to\network-map.json   # open a report on startup
dotnet test                                # run the NUnit tests
```

You can also open `RusNet.Viewer.slnx` in Visual Studio / Rider.

## How loading works (the viewer.htm JS contract)

`RusNet.Viewer/Assets/viewer.htm` is a single, dataless HTML file with all CSS/JS
inlined. It exposes a global JS API:

- `window.rusnet.load(dataOrJsonString)` — renders a report. Accepts a parsed object
  **or** a JSON string.
- `window.rusnet.setHostOpen(fn)` — registers a callback invoked when the user clicks
  the page's "Open report…" / empty-state "Open a report" button. The native host sets
  this so file-opening goes through the OS dialog, not an in-page `<input type=file>`.
- `window.rusnet.setHostScan(fn)` — registers a callback for the page's **Scan** button.
  Registering it is what *reveals* the Scan buttons (a plain browser can't scan), so both
  desktop apps show the same toolbar.
- `window.rusnet.setScanning(bool)` — shows/hides the page's scanning overlay.
- Drag-and-drop of a `.json` file onto the window works as an in-page fallback.

The WPF host (`MainWindow.xaml.cs`):

1. Reads `Assets/viewer.htm` and shows it with `CoreWebView2.NavigateToString`
   (the file is ~55 KB, well under NavigateToString's ~2 MB limit).
2. On `NavigationCompleted`, injects JS that calls `window.rusnet.setHostOpen(...)` to
   post a `rusnet:open` web message back to .NET.
3. On that message (or the native toolbar "Open report…" button), shows a
   `Microsoft.Win32.OpenFileDialog`
   (`RusNet report (*.json)|*.json|All files (*.*)|*.*`).
4. Reads the chosen file and calls
   `CoreWebView2.ExecuteScriptAsync("window.rusnet.load(" + encoded + ")")`, where
   `encoded` is the file text turned into a safe JS string literal via
   `System.Text.Json.JsonSerializer.Serialize(string)`
   (see `ViewerScript.cs`, which the tests cover).

A report path passed on the command line is loaded automatically once the page is ready.

WebView2's user-data/cache folder is kept out of the working directory, under
`%LOCALAPPDATA%\MindAttic\RusNet.Viewer\WebView2`.

## Scanning from the app

The **Scan** button posts `rusnet:scan` to .NET, which runs `python -m rusnet scan` as a
subprocess and loads the JSON it writes. For the subprocess to find the `rusnet` package,
the app looks for a folder containing `rusnet/__main__.py` starting from `RUSNET_HOME`
(if set), then the app's base directory and the working directory, walking up a few levels.
Running the app from its repo checkout (`dotnet run --project RusNet.Viewer`) works out of
the box; for a copied-out build, set `RUSNET_HOME` to the RusNet checkout. If Python or the
package can't be found, the app says so and you can still `python -m rusnet scan` yourself
and use **Open**. Python is found via `python`, falling back to the Windows `py -3` launcher.

## Regenerating viewer.htm

`viewer.htm` is generated from the Python package and vendored MindAttic.Components.
Regenerate it from the repo root after any viewer/component change:

```sh
python -m rusnet viewer -o dotnet/RusNet.Viewer/Assets/viewer.htm
```

## Projects

- `RusNet.Viewer/` — the WPF + WebView2 app (`net10.0-windows`).
- `RusNet.Viewer.Tests/` — NUnit tests for the JS-string-encoding helper.
