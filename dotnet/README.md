# RusNet Viewer (.NET / WPF)

A native Windows desktop host for the self-contained RusNet HTML network-map viewer.
It is a **viewer only**: it renders a RusNet JSON report (schema v1) in a WebView2
control and opens files with a native dialog. There is **no scanning or network code**
on the .NET side — all discovery lives in the Python `rusnet` package.

## Build & run

Requires the .NET 10 SDK and the Microsoft Edge WebView2 Runtime (preinstalled on
current Windows 11; the Evergreen installer covers older machines).

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

## Regenerating viewer.htm

`viewer.htm` is generated from the Python package and vendored MindAttic.Components.
Regenerate it from the repo root after any viewer/component change:

```sh
python -m rusnet viewer -o dotnet/RusNet.Viewer/Assets/viewer.htm
```

## Projects

- `RusNet.Viewer/` — the WPF + WebView2 app (`net10.0-windows`).
- `RusNet.Viewer.Tests/` — NUnit tests for the JS-string-encoding helper.
