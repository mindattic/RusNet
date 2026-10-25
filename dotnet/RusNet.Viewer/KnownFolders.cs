using System.Runtime.InteropServices;

namespace RusNet.Viewer;

/// <summary>
/// Resolves Windows known folders that have no <see cref="Environment.SpecialFolder"/> entry.
/// Downloads is one of them - joining <see cref="Environment.SpecialFolder.UserProfile"/> with
/// "Downloads" breaks whenever the user (or OneDrive's Known Folder Move) has relocated it via
/// Explorer's own Properties > Location tab. SHGetKnownFolderPath is the only API that still
/// gets it right.
/// </summary>
internal static class KnownFolders
{
    private static readonly Guid DownloadsFolderId = new("374DE290-123F-4565-9164-39C4925E467B");

    [DllImport("shell32.dll", CharSet = CharSet.Unicode, ExactSpelling = true, PreserveSig = false)]
    private static extern void SHGetKnownFolderPath(
        [MarshalAs(UnmanagedType.LPStruct)] Guid rfid, uint dwFlags, nint hToken, out nint ppszPath);

    public static string? TryGetDownloads()
    {
        nint ptr = 0;
        try
        {
            SHGetKnownFolderPath(DownloadsFolderId, 0, 0, out ptr);
            var path = Marshal.PtrToStringUni(ptr);
            return string.IsNullOrEmpty(path) ? null : path;
        }
        catch
        {
            return null;
        }
        finally
        {
            if (ptr != 0) Marshal.FreeCoTaskMem(ptr);
        }
    }
}
