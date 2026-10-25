using System.Text.Json;

namespace RusNet.Viewer;

/// <summary>
/// Pure helpers for talking to the viewer page's JS API. Kept free of WebView2
/// types so the string-encoding logic is unit-testable on its own.
/// </summary>
public static class ViewerScript
{
    /// <summary>
    /// Encodes an arbitrary string as a safe JavaScript string literal (including
    /// the surrounding quotes), using System.Text.Json so every control character,
    /// quote and backslash is escaped correctly.
    /// </summary>
    public static string EncodeJsString(string value)
    {
        // JsonSerializer.Serialize(string) produces a double-quoted JSON string,
        // which is also a valid JS string literal. It escapes ", \, newlines, etc.
        return JsonSerializer.Serialize(value);
    }

    /// <summary>
    /// Builds the <c>window.rusnet.load(...)</c> call that renders the given raw
    /// report text. The viewer's load() accepts a JSON string and parses it itself.
    /// </summary>
    public static string BuildLoadCall(string reportText)
    {
        return "window.rusnet.load(" + EncodeJsString(reportText) + ");";
    }
}
