using System.IO;
using System.Net.Http;

namespace OBSSceneGenerator.Services;

public static class StingerDownloader
{
    public const string StingerFolder = @"C:\Program Files (x86)\KH Switcher\Stingers";
    public const string StingerFile   = "Stinger120 Quick.mov";

    private const string StingerUrl =
        "https://raw.githubusercontent.com/aaroned/KH-Video-Switcher/master/Support/Stinger%20Files/Stinger120%20Quick.mov";

    /// <summary>
    /// Downloads the stinger file with progress reporting.
    /// Progress values are 0–100 (percent).
    /// </summary>
    public static async Task DownloadAsync(IProgress<int> progress, CancellationToken ct = default)
    {
        Directory.CreateDirectory(StingerFolder);
        var destPath = Path.Combine(StingerFolder, StingerFile);

        using var client = new HttpClient();
        using var response = await client.GetAsync(StingerUrl, HttpCompletionOption.ResponseHeadersRead, ct);
        response.EnsureSuccessStatusCode();

        var totalBytes = response.Content.Headers.ContentLength ?? -1L;
        await using var contentStream = await response.Content.ReadAsStreamAsync(ct);
        await using var fileStream = new FileStream(destPath, FileMode.Create, FileAccess.Write, FileShare.None, bufferSize: 8192, useAsync: true);

        var buffer = new byte[8192];
        long downloadedBytes = 0;
        int bytesRead;

        while ((bytesRead = await contentStream.ReadAsync(buffer, ct)) > 0)
        {
            await fileStream.WriteAsync(buffer.AsMemory(0, bytesRead), ct);
            downloadedBytes += bytesRead;

            if (totalBytes > 0)
                progress.Report((int)(downloadedBytes * 100 / totalBytes));
        }

        progress.Report(100);
    }
}
