using System.Text.Json;
using NUnit.Framework;
using RusNet.Viewer;

namespace RusNet.Viewer.Tests;

[TestFixture]
public class ViewerScriptTests
{
    [Test]
    public void EncodeJsString_WrapsInDoubleQuotes()
    {
        var result = ViewerScript.EncodeJsString("hello");
        Assert.That(result, Is.EqualTo("\"hello\""));
    }

    [Test]
    public void EncodeJsString_EscapesQuotesAndBackslashes()
    {
        var result = ViewerScript.EncodeJsString("a\"b\\c");
        // Round-trips back to the original string via JSON parse.
        Assert.That(JsonSerializer.Deserialize<string>(result), Is.EqualTo("a\"b\\c"));
    }

    [Test]
    public void EncodeJsString_EscapesNewlinesSoLiteralStaysOneToken()
    {
        var result = ViewerScript.EncodeJsString("line1\nline2\r\ntab\there");
        Assert.That(result, Does.Not.Contain("\n"));
        Assert.That(result, Does.Not.Contain("\r"));
        Assert.That(JsonSerializer.Deserialize<string>(result), Is.EqualTo("line1\nline2\r\ntab\there"));
    }

    [Test]
    public void BuildLoadCall_WrapsEncodedTextInLoadCall()
    {
        var json = "{\"hosts\":[]}";
        var call = ViewerScript.BuildLoadCall(json);

        Assert.That(call, Does.StartWith("window.rusnet.load("));
        Assert.That(call, Does.EndWith(");"));

        // The argument inside the parentheses must be a valid JS/JSON string literal
        // that parses back to the exact original report text.
        var inner = call["window.rusnet.load(".Length..^");".Length];
        Assert.That(JsonSerializer.Deserialize<string>(inner), Is.EqualTo(json));
    }

    [Test]
    public void BuildLoadCall_HandlesScriptInjectionAttemptSafely()
    {
        // Malicious-looking content must not break out of the string literal.
        var evil = "\");alert('x');//";
        var call = ViewerScript.BuildLoadCall(evil);
        var inner = call["window.rusnet.load(".Length..^");".Length];
        Assert.That(JsonSerializer.Deserialize<string>(inner), Is.EqualTo(evil));
    }
}
